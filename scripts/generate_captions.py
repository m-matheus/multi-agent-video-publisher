"""
Kinetic caption generation for YouTube Shorts.
Reads word-level alignment JSONs (produced by generate_voice.py --timestamps)
and generates a burned-in ASS subtitle file with 2-3 words per block.

Usage:
    python scripts/generate_captions.py \
        --script-path output/run-001/script/script_short.json \
        --audio-dir output/run-001/short/audio \
        --output-dir output/run-001/short \
        --shorts
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.file_helpers import ensure_dir

GAP_SECONDS = 0.3  # Must match generate_voice.py concatenate_segments gap_ms=300


def get_mp3_duration(path: Path) -> float:
    try:
        from mutagen.mp3 import MP3
        return MP3(str(path)).info.length
    except Exception:
        pass
    import subprocess
    import re
    from scripts.utils.config import get_ffmpeg_path
    result = subprocess.run(
        [get_ffmpeg_path(), "-i", str(path)],
        capture_output=True, text=True,
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
    if m:
        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mn * 60 + s
    raise RuntimeError(f"Could not determine duration of {path}")


def seconds_to_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = round((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def chunk_words(words: list[dict], n: int) -> list[list[dict]]:
    return [words[i:i + n] for i in range(0, len(words), n)]


def build_ass(events: list[dict], shorts: bool) -> str:
    play_res_y = 1920 if shorts else 1080
    play_res_x = 1080 if shorts else 1920
    font_size = 90 if shorts else 72

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kinetic,Impact,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,30,30,130,0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    lines = [header]
    for ev in events:
        start = seconds_to_ass_time(ev["start"])
        end = seconds_to_ass_time(ev["end"])
        text = ev["text"].upper()
        lines.append(f"Dialogue: 0,{start},{end},Kinetic,,0,0,0,, {{\\fad(60,0)}}{text}")

    return "\n".join(lines) + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate kinetic ASS captions for Shorts")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--audio-dir", required=True, help="Path to audio directory (contains narration_segments/)")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--words-per-chunk", type=int, default=2, help="Words per caption block (default: 2)")
    parser.add_argument("--shorts", action="store_true", help="Use 1080x1920 vertical dimensions")
    return parser.parse_args()


def main():
    args = parse_args()
    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    audio_dir = Path(args.audio_dir)
    segments_dir = audio_dir / "narration_segments"
    output_dir = Path(args.output_dir)

    scenes = script["scenes"]
    events = []
    current_time = 0.0

    for i, scene in enumerate(scenes):
        seg_path = segments_dir / f"segment_{i+1:02d}.mp3"
        alignment_path = segments_dir / f"segment_{i+1:02d}_alignment.json"

        if not seg_path.exists():
            current_time += GAP_SECONDS
            continue

        duration = get_mp3_duration(seg_path)
        scene_start = current_time
        scene_end = current_time + duration

        if alignment_path.exists():
            data = json.loads(alignment_path.read_text(encoding="utf-8"))
            words = data.get("words", [])
            if words:
                chunks = chunk_words(words, args.words_per_chunk)
                for j, chunk in enumerate(chunks):
                    chunk_start = scene_start + chunk[0]["start"]
                    if j + 1 < len(chunks):
                        chunk_end = scene_start + chunks[j + 1][0]["start"]
                    else:
                        chunk_end = scene_end
                    chunk_text = " ".join(w["word"] for w in chunk)
                    events.append({"start": chunk_start, "end": chunk_end, "text": chunk_text})
        else:
            # Fallback: split narration_text evenly across scene duration when no alignment data
            text = scene.get("narration_text", "").strip()
            if text:
                words_list = text.split()
                n = args.words_per_chunk
                chunks = [words_list[k:k + n] for k in range(0, len(words_list), n)]
                chunk_dur = duration / len(chunks) if chunks else duration
                for j, chunk in enumerate(chunks):
                    chunk_start = scene_start + j * chunk_dur
                    chunk_end = scene_start + (j + 1) * chunk_dur
                    events.append({"start": chunk_start, "end": chunk_end, "text": " ".join(chunk)})

        current_time = scene_end + GAP_SECONDS

    ensure_dir(audio_dir)
    ass_path = audio_dir / "captions.ass"
    ass_path.write_text(build_ass(events, args.shorts), encoding="utf-8")
    print(f"Captions saved: {ass_path} ({len(events)} blocks)")


if __name__ == "__main__":
    main()
