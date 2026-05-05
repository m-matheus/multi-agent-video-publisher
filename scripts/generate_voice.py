"""
Voice narration generation via ElevenLabs. Generates audio for each scene.

Usage:
    python scripts/generate_voice.py --script-path output/run-001/script/script.json --output-dir output/run-001
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager


def parse_args():
    parser = argparse.ArgumentParser(description="Generate voice narration via ElevenLabs")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--voice-id", default=None, help="Override voice ID")
    parser.add_argument("--timestamps", action="store_true", help="Save word-level alignment JSON alongside each segment")
    return parser.parse_args()


def get_voice_id(content_type: str, config: dict, override: str = None) -> str:
    if override:
        return override
    if content_type == "bedtime-story":
        return config["voice_id_bedtime"]
    return config["voice_id_anime"]


def generate_segment(text: str, voice_id: str, model_id: str, api_key: str) -> bytes:
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=api_key)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            audio = client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                output_format="mp3_44100_128",
            )
            if isinstance(audio, bytes):
                return audio
            chunks = []
            for chunk in audio:
                chunks.append(chunk)
            return b"".join(chunks)
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  Retry {attempt + 1} after {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                raise


def chars_to_words(alignment) -> list[dict]:
    chars = alignment.characters
    starts = alignment.character_start_times_seconds
    ends = alignment.character_end_times_seconds
    words = []
    current_chars = []
    word_start = None
    word_end = None
    for char, start, end in zip(chars, starts, ends):
        if char in (" ", "\n", "\t"):
            if current_chars:
                words.append({"word": "".join(current_chars), "start": word_start, "end": word_end})
                current_chars = []
                word_start = None
        else:
            if not current_chars:
                word_start = start
            current_chars.append(char)
            word_end = end
    if current_chars:
        words.append({"word": "".join(current_chars), "start": word_start, "end": word_end})
    return words


def generate_segment_with_timestamps(text: str, voice_id: str, model_id: str, api_key: str) -> tuple[bytes, list[dict]]:
    import base64
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=api_key)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.text_to_speech.convert_with_timestamps(
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                output_format="mp3_44100_128",
            )
            audio_bytes = base64.b64decode(response.audio_base_64)
            words = chars_to_words(response.alignment)
            return audio_bytes, words
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  Retry {attempt + 1} after {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                raise



def get_audio_duration(file_path: Path) -> float:
    from mutagen.mp3 import MP3
    audio = MP3(str(file_path))
    return audio.info.length


def concatenate_segments(segment_paths: list[Path], output_path: Path, gap_ms: int = 300) -> float:
    import subprocess
    import tempfile
    from scripts.utils.config import get_ffmpeg_path

    gap_sec = gap_ms / 1000.0

    # Generate a silent gap file
    with tempfile.TemporaryDirectory() as tmpdir:
        gap_path = Path(tmpdir) / "gap.mp3"
        subprocess.run(
            [get_ffmpeg_path(), "-y", "-f", "lavfi", "-i",
             f"anullsrc=r=44100:cl=mono", "-t", str(gap_sec),
             "-q:a", "9", "-acodec", "libmp3lame", str(gap_path)],
            capture_output=True, check=True,
        )

        # Build concat list
        concat_list = Path(tmpdir) / "concat.txt"
        lines = []
        for i, path in enumerate(segment_paths):
            lines.append(f"file '{path.resolve()}'\n")
            if i < len(segment_paths) - 1:
                lines.append(f"file '{gap_path.resolve()}'\n")
        concat_list.write_text("".join(lines), encoding="utf-8")

        subprocess.run(
            [get_ffmpeg_path(), "-y", "-f", "concat", "-safe", "0",
             "-i", str(concat_list), "-c", "copy", str(output_path)],
            capture_output=True, check=True,
        )

    return get_audio_duration(output_path)


def main():
    args = parse_args()
    config = load_config()

    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    audio_dir = ensure_dir(output_dir / "audio")
    segments_dir = ensure_dir(audio_dir / "narration_segments")

    content_type = script.get("content_type", "anime")
    voice_id = get_voice_id(content_type, config, args.voice_id)
    model_id = config["elevenlabs_model"]
    scenes = script["scenes"]

    state = StateManager()
    state.update_step("step-04-voice-narration", "running")

    print(f"Generating narration for {len(scenes)} scenes (voice: {voice_id})...")
    start_time = time.time()

    segment_paths = []
    segment_durations = []

    for i, scene in enumerate(scenes):
        text = scene.get("narration_text", "").strip()
        segment_path = segments_dir / f"segment_{i+1:02d}.mp3"

        if not text:
            print(f"  Segment {i+1}: silent (no narration_text)")
            segment_paths.append(None)
            segment_durations.append(0)
            continue

        try:
            if args.timestamps:
                audio_bytes, words = generate_segment_with_timestamps(text, voice_id, model_id, config["elevenlabs_api_key"])
                alignment_path = segments_dir / f"segment_{i+1:02d}_alignment.json"
                alignment_path.write_text(json.dumps({"words": words}, ensure_ascii=False), encoding="utf-8")
            else:
                audio_bytes = generate_segment(text, voice_id, model_id, config["elevenlabs_api_key"])
            segment_path.write_bytes(audio_bytes)
            duration = get_audio_duration(segment_path)
            segment_paths.append(segment_path)
            segment_durations.append(duration)
            print(f"  Segment {i+1}: {duration:.1f}s - saved")
        except Exception as e:
            print(f"  Segment {i+1}: FAILED - {e}")
            segment_paths.append(None)
            segment_durations.append(0)

    valid_segments = [p for p in segment_paths if p]
    if valid_segments:
        full_narration_path = audio_dir / "narration_full.mp3"
        total_duration = concatenate_segments(valid_segments, full_narration_path)
        print(f"\nFull narration: {total_duration:.1f}s saved to {full_narration_path.name}")
    else:
        print("\nERROR: No audio segments generated successfully")
        state.update_step("step-04-voice-narration", "failed")
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.1f}s")

    state.update_step("step-04-voice-narration", "completed", {
        "narration_path": str(full_narration_path),
        "segment_durations": segment_durations,
        "total_duration": total_duration,
    })


if __name__ == "__main__":
    main()
