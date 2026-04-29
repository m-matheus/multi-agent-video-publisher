"""
Download and analyze multiple AMVs for a multi-character compilation (e.g., "Top 5 Most Powerful").
Scores each segment for fight/action content, selects the best N scenes per character,
and merges all into a single frames/ directory with sequential numbering.

Usage:
    python scripts/fetch_multi_amv.py \
        --urls "url1,url2,url3,url4,url5" \
        --output-dir output/top5-powerful \
        --scenes-per-character 3
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

# Use python -m yt_dlp to avoid PATH issues on Windows
YT_DLP = [sys.executable, "-m", "yt_dlp"]


def download_amv(url: str, output_path: Path, ffmpeg_path: str) -> dict:
    info_result = subprocess.run(
        YT_DLP + ["--dump-json", "--no-playlist", url],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(info_result.stdout)
    metadata = {
        "url": url,
        "title": info.get("title", ""),
        "channel": info.get("channel", info.get("uploader", "")),
        "duration": info.get("duration", 0),
        "description": (info.get("description", "") or "")[:300],
    }
    subprocess.run(
        YT_DLP + [
            "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
            "--merge-output-format", "mp4",
            "--ffmpeg-location", ffmpeg_path,  # full path to exe, not directory
            "-o", str(output_path),
            "--no-playlist",
            url,
        ],
        check=True,
    )
    return metadata


def get_duration(video_path: str, ffmpeg_path: str) -> float:
    """Extract video duration from ffmpeg stderr (no ffprobe needed)."""
    result = subprocess.run(
        [ffmpeg_path, "-i", video_path],
        capture_output=True, text=True,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"Could not determine duration of {video_path}")


def detect_scene_cuts(video_path: str, ffmpeg_path: str, threshold: float = 0.35) -> list[float]:
    result = subprocess.run(
        [
            ffmpeg_path, "-i", video_path,
            "-vf", f"select=gt(scene\\,{threshold}),showinfo",
            "-vsync", "vfr", "-an", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    timestamps = []
    for match in re.finditer(r"pts_time:([\d.]+)", result.stderr):
        timestamps.append(float(match.group(1)))
    return sorted(set(timestamps))


def build_segments(
    cuts: list[float], total_duration: float, min_duration: float = 3.0
) -> list[tuple[float, float]]:
    boundaries = [0.0] + cuts + [total_duration]
    segments = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        if end - start >= min_duration:
            segments.append((start, end))
        elif segments:
            segments[-1] = (segments[-1][0], end)
    return segments


def extract_keyframe(video_path: str, timestamp: float, output_path: str, ffmpeg_path: str) -> bool:
    result = subprocess.run(
        [
            ffmpeg_path, "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",
            output_path,
        ],
        capture_output=True,
    )
    return result.returncode == 0 and Path(output_path).exists()


def score_and_describe_frame(
    client: anthropic.Anthropic, image_path: str, slot: int, total_slots: int
) -> tuple[str, int]:
    """Returns (description, action_score 1-5)."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
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
                            f"This is a frame from anime AMV {slot} of {total_slots} in a 'Top 5 Most Powerful' compilation. "
                            "1) Describe the scene in 1-2 sentences: mood, visible characters, action. "
                            "2) Rate how ACTION/FIGHT-heavy it is from 1-5 (5=intense battle/power display, 1=calm/transition/text). "
                            'Reply ONLY in JSON: {"description": "...", "action_score": N}'
                        ),
                    },
                ],
            }
        ],
    )

    text = response.content[0].text
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("description", text[:150]), int(data.get("action_score", 3))
    except Exception:
        pass
    return text[:200], 3


def split_segment(video_path: str, start: float, end: float, output_path: str, ffmpeg_path: str) -> None:
    subprocess.run(
        [
            ffmpeg_path, "-y",
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


def process_one_amv(
    client: anthropic.Anthropic,
    url: str,
    slot: int,
    total_slots: int,
    char_dir: Path,
    frames_dir: Path,
    scenes_per_char: int,
    global_scene_offset: int,
    ffmpeg_path: str,
) -> dict:
    print(f"\n{'='*55}")
    print(f"[{slot}/{total_slots}] Downloading AMV...")
    video_path = char_dir / "amv_source.mp4"

    # Clean up partial yt-dlp files if merged mp4 doesn't exist
    if not video_path.exists():
        for partial in char_dir.glob("amv_source.f*.mp4"):
            partial.unlink()
        for partial in char_dir.glob("amv_source.f*.m4a"):
            partial.unlink()

    metadata_path = char_dir / "amv_metadata.json"
    if video_path.exists() and metadata_path.exists():
        print("  Already downloaded, skipping.")
        metadata = json.loads(metadata_path.read_text())
    else:
        metadata = download_amv(url, video_path, ffmpeg_path)
        print(f"  Title   : {metadata['title']}")
        print(f"  Duration: {metadata['duration']}s")
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    total_duration = get_duration(str(video_path), ffmpeg_path)
    print("  Detecting scene cuts...")
    cuts = detect_scene_cuts(str(video_path), ffmpeg_path)
    print(f"  {len(cuts)} raw cut(s) → building segments...")
    segments = build_segments(cuts, total_duration)
    print(f"  {len(segments)} candidate segment(s)")

    keyframes_dir = ensure_dir(char_dir / "keyframes")
    candidates = []
    print(f"  Scoring segments for fight content (Claude Vision)...")

    for i, (start, end) in enumerate(segments):
        midpoint = start + (end - start) / 2
        kf_path = str(keyframes_dir / f"seg_{i:03d}.jpg")
        ok = extract_keyframe(str(video_path), midpoint, kf_path, ffmpeg_path)
        description, action_score = "Scene from AMV.", 3
        if ok:
            try:
                description, action_score = score_and_describe_frame(
                    client, kf_path, slot, total_slots
                )
            except Exception as e:
                print(f"    Vision error on seg {i}: {e}")
        candidates.append(
            {
                "start": start,
                "end": end,
                "duration": end - start,
                "keyframe_path": kf_path,
                "description": description,
                "action_score": action_score,
            }
        )

    # Pick top N by action score, restore temporal order
    top = sorted(candidates, key=lambda x: x["action_score"], reverse=True)[:scenes_per_char]
    top = sorted(top, key=lambda x: x["start"])

    print(f"  Selected {len(top)} best fight scene(s):")
    scenes = []
    for local_i, seg in enumerate(top):
        global_num = global_scene_offset + local_i + 1
        seg_path = str(frames_dir / f"scene_{global_num:02d}.mp4")
        split_segment(str(video_path), seg["start"], seg["end"], seg_path, ffmpeg_path)
        print(
            f"    scene_{global_num:02d}.mp4  {seg['start']:.1f}s–{seg['end']:.1f}s "
            f"(action={seg['action_score']})  {seg['description'][:70]}..."
        )
        scenes.append(
            {
                "segment_number": global_num,
                "character_slot": slot,
                "start_time": round(seg["start"], 2),
                "end_time": round(seg["end"], 2),
                "duration_seconds": round(seg["duration"], 2),
                "keyframe_path": seg["keyframe_path"],
                "description": seg["description"],
                "action_score": seg["action_score"],
                "segment_path": seg_path,
            }
        )

    return {
        "slot": slot,
        "url": url,
        "title": metadata["title"],
        "channel": metadata["channel"],
        "scenes": scenes,
    }


def fetch_multi_amv(
    urls: list[str], output_dir: str, scenes_per_character: int = 3
) -> dict:
    out = Path(output_dir)
    amv_dir = ensure_dir(out / "amv")
    frames_dir = ensure_dir(out / "frames")
    client = anthropic.Anthropic()
    ffmpeg_path = get_ffmpeg_path()
    print(f"Using ffmpeg: {ffmpeg_path}")

    characters = []
    all_scenes = []
    global_offset = 0

    for slot, url in enumerate(urls, 1):
        char_dir = ensure_dir(amv_dir / f"character_{slot:02d}")
        char_data = process_one_amv(
            client=client,
            url=url.strip(),
            slot=slot,
            total_slots=len(urls),
            char_dir=char_dir,
            frames_dir=frames_dir,
            scenes_per_char=scenes_per_character,
            global_scene_offset=global_offset,
            ffmpeg_path=ffmpeg_path,
        )
        all_scenes.extend(char_data.pop("scenes"))
        characters.append(char_data)
        global_offset += scenes_per_character

    total_duration = sum(s["duration_seconds"] for s in all_scenes)
    analysis = {
        "total_duration": round(total_duration, 2),
        "scene_count": len(all_scenes),
        "characters": characters,
        "scenes": all_scenes,
    }

    analysis_path = amv_dir / "amv_analysis.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
    print(f"\n{'='*55}")
    print(f"Combined analysis saved: {analysis_path}")

    return analysis


def main():
    parser = argparse.ArgumentParser(
        description="Download and analyze multiple AMVs for a multi-character video"
    )
    parser.add_argument("--urls", required=True, help="Comma-separated YouTube URLs")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument(
        "--scenes-per-character",
        type=int,
        default=3,
        help="Fight scenes to select per AMV (default: 3)",
    )
    args = parser.parse_args()

    load_config()
    state = StateManager()
    state.update_step("fetch-multi-amv", "running")

    urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    print(f"Processing {len(urls)} AMV(s), {args.scenes_per_character} fight scenes each...")

    try:
        analysis = fetch_multi_amv(urls, args.output_dir, args.scenes_per_character)
        state.update_step(
            "fetch-multi-amv",
            "completed",
            {
                "analysis_path": str(Path(args.output_dir) / "amv" / "amv_analysis.json"),
                "scene_count": analysis["scene_count"],
                "total_duration_seconds": analysis["total_duration"],
                "character_count": len(analysis["characters"]),
            },
        )
        print(
            f"\nDone: {analysis['scene_count']} scenes across "
            f"{len(analysis['characters'])} characters, {analysis['total_duration']}s total"
        )
    except Exception as e:
        state.update_step("fetch-multi-amv", "failed", {"error": str(e)})
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
