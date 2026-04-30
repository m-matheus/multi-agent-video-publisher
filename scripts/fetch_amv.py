"""
Download an AMV from YouTube using yt-dlp.

Usage:
    python scripts/fetch_amv.py --url "https://youtube.com/watch?v=..." --output-dir output/my-amv
"""
import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

# Ensure stdout/stderr handle non-ASCII characters (e.g. Japanese video titles on Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, get_ffmpeg_path
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager

YT_DLP = [sys.executable, "-m", "yt_dlp"]


def fetch_amv(url: str, output_dir: str) -> dict:
    out = Path(output_dir)
    amv_dir = ensure_dir(out / "amv")

    # Locate ffmpeg so yt-dlp can merge video+audio streams
    try:
        ffmpeg_bin = str(Path(get_ffmpeg_path()).parent)
    except FileNotFoundError:
        ffmpeg_bin = None

    print(f"Fetching metadata for: {url}")
    info_result = subprocess.run(
        YT_DLP + ["--dump-json", "--no-playlist", url],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    info = json.loads(info_result.stdout)

    metadata = {
        "url": url,
        "title": info.get("title", ""),
        "channel": info.get("channel", info.get("uploader", "")),
        "duration": info.get("duration", 0),
        "description": (info.get("description", "") or "")[:500],
        "upload_date": info.get("upload_date", ""),
    }

    video_path = amv_dir / "amv_source.mp4"
    print(f"Downloading: {metadata['title']} ({metadata['duration']}s)")
    cmd = YT_DLP + [
        "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", str(video_path),
        "--no-playlist",
    ]
    if ffmpeg_bin:
        cmd += ["--ffmpeg-location", ffmpeg_bin]
    cmd.append(url)
    subprocess.run(cmd, check=True)

    metadata["local_path"] = str(video_path)
    (amv_dir / "amv_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Download AMV from YouTube")
    parser.add_argument("--url", required=True, help="YouTube AMV URL")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    args = parser.parse_args()

    load_config()
    state = StateManager()
    state.update_step("fetch-amv", "running")

    try:
        metadata = fetch_amv(args.url, args.output_dir)
        state.update_step("fetch-amv", "completed", {
            "amv_path": metadata["local_path"],
            "title": metadata["title"],
            "duration_seconds": metadata["duration"],
        })
        print(f"\nDone. Saved to: {metadata['local_path']}")
    except subprocess.CalledProcessError as e:
        err = e.stderr or str(e)
        state.update_step("fetch-amv", "failed", {"error": err})
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        state.update_step("fetch-amv", "failed", {"error": str(e)})
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
