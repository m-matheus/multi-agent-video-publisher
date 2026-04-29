"""
SRT subtitle generation from script.json + narration segment audio files.
Timestamps are derived from actual segment durations with 300ms gaps between segments,
matching exactly what generate_voice.py produces in narration_full.mp3.

Usage:
    python scripts/generate_subtitles.py --script-path output/run-001/script/script.json --audio-dir output/run-001/audio --output-dir output/run-001
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager

GAP_SECONDS = 0.3  # Must match generate_voice.py concatenate_segments gap_ms=300


def get_mp3_duration(path: Path) -> float:
    try:
        from mutagen.mp3 import MP3
        return MP3(str(path)).info.length
    except Exception:
        pass
    # Fallback: ffprobe/ffmpeg
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


def seconds_to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def wrap_lines(text: str, max_chars: int = 42) -> str:
    words = text.split()
    lines = []
    current = []
    length = 0
    for word in words:
        if length + len(word) + (1 if current else 0) > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += len(word) + (1 if len(current) > 1 else 0)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:2])  # SRT: max 2 lines


def parse_args():
    parser = argparse.ArgumentParser(description="Generate SRT subtitles from script + audio segments")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--audio-dir", required=True, help="Path to audio directory")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    return parser.parse_args()


def main():
    args = parse_args()
    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    audio_dir = Path(args.audio_dir)
    segments_dir = audio_dir / "narration_segments"
    output_dir = Path(args.output_dir)

    scenes = script["scenes"]
    state = StateManager()
    state.update_step("step-04b-subtitles", "running")

    entries = []
    current_time = 0.0

    for i, scene in enumerate(scenes):
        seg_path = segments_dir / f"segment_{i+1:02d}.mp3"
        if not seg_path.exists():
            print(f"  WARNING: {seg_path.name} not found — skipping scene {i+1}")
            current_time += GAP_SECONDS
            continue

        duration = get_mp3_duration(seg_path)
        start = current_time
        end = current_time + duration

        text = scene["narration_text"].strip()
        entries.append((i + 1, start, end, wrap_lines(text)))

        current_time = end + GAP_SECONDS
        print(f"  Scene {i+1}: {seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}")

    srt_lines = []
    for idx, (n, start, end, text) in enumerate(entries):
        srt_lines.append(str(idx + 1))
        srt_lines.append(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}")
        srt_lines.append(text)
        srt_lines.append("")

    srt_content = "\n".join(srt_lines)
    srt_path = audio_dir / "subtitles.srt"
    srt_path.write_text(srt_content, encoding="utf-8")

    print(f"\nSubtitles saved: {srt_path} ({len(entries)} entries)")
    state.update_step("step-04b-subtitles", "completed", {"srt_path": str(srt_path)})


if __name__ == "__main__":
    main()
