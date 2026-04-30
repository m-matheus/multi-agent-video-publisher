"""
Analyze a downloaded AMV: detect scene cuts via ffmpeg, extract keyframes,
describe each segment using Claude Vision, and split the AMV into per-scene
MP4 clips ready for compose_video.py.

Usage:
    python scripts/analyze_amv.py --amv-path output/my-amv/amv/amv_source.mp4 --output-dir output/my-amv
    python scripts/analyze_amv.py --amv-path ... --output-dir ... --max-scenes 10 --min-scene-duration 4.0
"""
import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, get_ffmpeg_path
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager

# Resolve ffmpeg from imageio-ffmpeg if not in PATH (ffprobe not required)
FFMPEG = get_ffmpeg_path()


def get_duration(video_path: str) -> float:
    result = subprocess.run(
        [FFMPEG, "-i", video_path],
        capture_output=True, text=True,
    )
    # ffmpeg prints duration to stderr: "  Duration: HH:MM:SS.ss"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise ValueError(f"Could not determine duration of {video_path}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def detect_scene_cuts(video_path: str, threshold: float = 0.35) -> list[float]:
    """Return sorted list of scene-change timestamps (seconds) using ffmpeg showinfo."""
    result = subprocess.run(
        [
            FFMPEG, "-i", video_path,
            "-vf", f"select=gt(scene\\,{threshold}),showinfo",
            "-vsync", "vfr", "-an", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    # showinfo lines contain: pts_time:12.345
    timestamps = []
    for match in re.finditer(r"pts_time:([\d.]+)", result.stderr):
        timestamps.append(float(match.group(1)))
    return sorted(set(timestamps))


def build_segments(
    cut_timestamps: list[float],
    total_duration: float,
    min_duration: float,
    max_scenes: int,
) -> list[tuple[float, float]]:
    """Convert cut points into (start, end) pairs, merging short/excess segments."""
    boundaries = [0.0] + cut_timestamps + [total_duration]
    segments = []
    pending_start = 0.0

    for boundary in boundaries[1:]:
        if boundary - pending_start >= min_duration:
            segments.append((pending_start, boundary))
            pending_start = boundary

    # Absorb any remaining tail into the last segment
    if segments and pending_start < total_duration - 0.01:
        segments[-1] = (segments[-1][0], total_duration)

    # Fallback: video had no cuts long enough — treat whole video as one segment
    if not segments:
        segments = [(0.0, total_duration)]

    # Merge shortest neighbours until we reach max_scenes
    while len(segments) > max_scenes:
        durations = [e - s for s, e in segments]
        idx = durations.index(min(durations))
        if idx == 0:
            merged = (segments[0][0], segments[1][1])
            segments = [merged] + segments[2:]
        elif idx == len(segments) - 1:
            merged = (segments[-2][0], segments[-1][1])
            segments = segments[:-2] + [merged]
        else:
            left_dur = segments[idx - 1][1] - segments[idx - 1][0]
            right_dur = segments[idx + 1][1] - segments[idx + 1][0]
            if left_dur <= right_dur:
                merged = (segments[idx - 1][0], segments[idx][1])
                segments = segments[: idx - 1] + [merged] + segments[idx + 1 :]
            else:
                merged = (segments[idx][0], segments[idx + 1][1])
                segments = segments[:idx] + [merged] + segments[idx + 2 :]

    return segments


def extract_keyframe(video_path: str, timestamp: float, output_path: str) -> bool:
    result = subprocess.run(
        [
            FFMPEG, "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",
            output_path,
        ],
        capture_output=True,
    )
    return result.returncode == 0 and Path(output_path).exists()


def describe_frame(client: anthropic.Anthropic, image_path: str, segment_num: int, total: int) -> str:
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This is segment {segment_num} of {total} from an anime AMV. "
                            "In 2-3 sentences describe: what is happening visually, "
                            "the mood/energy level, and any visible characters or action."
                        ),
                    },
                ],
            }
        ],
    )
    return response.content[0].text


def split_segment(video_path: str, start: float, end: float, output_path: str) -> None:
    subprocess.run(
        [
            FFMPEG, "-y",
            "-ss", str(start),
            "-t", str(end - start),
            "-i", video_path,
            "-c:v", "libx264", "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ],
        capture_output=True,
        check=True,
    )


def analyze_amv(
    amv_path: str,
    output_dir: str,
    max_scenes: int = 12,
    min_scene_duration: float = 3.0,
) -> dict:
    out = Path(output_dir)
    amv_dir = ensure_dir(out / "amv")
    keyframes_dir = ensure_dir(amv_dir / "keyframes")
    frames_dir = ensure_dir(out / "frames")

    total_duration = get_duration(amv_path)
    print(f"AMV duration: {total_duration:.1f}s")

    print("Detecting scene changes...")
    cuts = detect_scene_cuts(amv_path)
    print(f"Found {len(cuts)} raw cut(s)")

    segments = build_segments(cuts, total_duration, min_scene_duration, max_scenes)
    print(f"Built {len(segments)} scene(s) after merging")

    client = anthropic.Anthropic()
    scenes = []

    for i, (start, end) in enumerate(segments, 1):
        duration = end - start
        midpoint = start + duration / 2
        print(f"  Scene {i:02d}/{len(segments):02d}: {start:.1f}s–{end:.1f}s ({duration:.1f}s)")

        keyframe_path = str(keyframes_dir / f"segment_{i:02d}.jpg")
        ok = extract_keyframe(amv_path, midpoint, keyframe_path)

        description = f"Scene {i} of the AMV."
        if ok:
            try:
                description = describe_frame(client, keyframe_path, i, len(segments))
                print(f"    Vision: {description[:80]}...")
            except Exception as e:
                print(f"    Vision API error (using placeholder): {e}")

        segment_path = str(frames_dir / f"scene_{i:02d}.mp4")
        split_segment(amv_path, start, end, segment_path)

        scenes.append(
            {
                "segment_number": i,
                "start_time": round(start, 2),
                "end_time": round(end, 2),
                "duration_seconds": round(duration, 2),
                "keyframe_path": keyframe_path,
                "description": description,
                "segment_path": segment_path,
            }
        )

    analysis = {
        "total_duration": round(total_duration, 2),
        "scene_count": len(scenes),
        "scenes": scenes,
    }

    analysis_path = amv_dir / "amv_analysis.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nAnalysis saved: {analysis_path}")

    return analysis


def main():
    parser = argparse.ArgumentParser(description="Analyze AMV and split into scene segments")
    parser.add_argument("--amv-path", required=True, help="Path to downloaded AMV file")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--max-scenes", type=int, default=12, help="Max number of scenes (default: 12)")
    parser.add_argument("--min-scene-duration", type=float, default=3.0, help="Min scene duration in seconds (default: 3.0)")
    args = parser.parse_args()

    load_config()
    state = StateManager()
    state.update_step("analyze-amv", "running")

    try:
        analysis = analyze_amv(args.amv_path, args.output_dir, args.max_scenes, args.min_scene_duration)
        state.update_step("analyze-amv", "completed", {
            "analysis_path": str(Path(args.output_dir) / "amv" / "amv_analysis.json"),
            "scene_count": analysis["scene_count"],
            "total_duration_seconds": analysis["total_duration"],
        })
        print(f"\nDone: {analysis['scene_count']} scenes, {analysis['total_duration']}s total")
    except Exception as e:
        state.update_step("analyze-amv", "failed", {"error": str(e)})
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
