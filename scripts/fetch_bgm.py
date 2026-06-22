"""
Background music download for video composition.

Two modes:
  1. YouTube URL  — download audio via yt-dlp (no API key required)
     python scripts/fetch_bgm.py --url "https://youtu.be/..." --output-dir output/run-001

  2. Freesound search — search by keyword, download preview (requires FREESOUND_API_KEY in .env)
     python scripts/fetch_bgm.py --query "epic anime orchestra" --output-dir output/run-001

Good royalty-free YouTube music sources:
  - YouTube Audio Library: https://www.youtube.com/audiolibrary
  - NCS (No Copyright Sounds): https://www.youtube.com/@NoCopyrightSounds
  - Epidemic Sound free previews: search YouTube
"""
import argparse
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, get_ffmpeg_path
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager

YT_DLP = [sys.executable, "-m", "yt_dlp"]


def parse_args():
    parser = argparse.ArgumentParser(description="Download background music for video composition")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="YouTube URL to download audio from")
    group.add_argument("--search", help="YouTube search query — downloads top result (e.g. 'epic anime orchestra royalty free')")
    group.add_argument("--query", help="Freesound search query (requires FREESOUND_API_KEY in .env)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Mode 1: YouTube via yt-dlp
# ---------------------------------------------------------------------------

def download_from_youtube(url: str, output_path: Path) -> None:
    """Download audio from a YouTube URL using yt-dlp + FFmpeg conversion."""
    ffmpeg_path = get_ffmpeg_path()
    tmp_audio = output_path.with_suffix(".tmp_audio")

    # Step 1: download best audio stream (no ffprobe needed — no post-processing)
    dl_cmd = [
        *YT_DLP,
        "-f", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
        "--no-playlist",
        "--output", str(tmp_audio) + ".%(ext)s",
        "--ffmpeg-location", ffmpeg_path,
        url,
    ]
    print("  Downloading audio stream...")
    result = subprocess.run(dl_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr[-1000:]}")

    # Step 2: find the downloaded file (extension varies)
    candidates = sorted(output_path.parent.glob(tmp_audio.name + ".*"))
    if not candidates:
        raise FileNotFoundError("yt-dlp finished but downloaded audio file not found")
    tmp_file = candidates[0]

    # Step 3: convert to MP3 with FFmpeg
    print(f"  Converting {tmp_file.suffix} -> mp3...")
    ffmpeg_cmd = [
        ffmpeg_path, "-y", "-i", str(tmp_file),
        "-vn", "-acodec", "libmp3lame", "-q:a", "4",
        str(output_path),
    ]
    result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=120)
    tmp_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed:\n{result.stderr.decode()[-500:]}")


# ---------------------------------------------------------------------------
# Mode 2: Freesound search
# ---------------------------------------------------------------------------

def search_freesound(query: str, api_key: str) -> list[dict]:
    """Search Freesound for tracks matching the query."""
    import requests
    resp = requests.get(
        "https://freesound.org/apiv2/search/text/",
        params={
            "token": api_key,
            "query": query,
            "filter": "duration:[60 TO 600] type:mp3",
            "fields": "id,name,duration,previews",
            "sort": "score",
            "page_size": 10,
            "format": "json",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def pick_random_track(results: list[dict]) -> dict:
    """Pick a random track from the top 5 results to avoid always reusing the same BGM."""
    import random
    pool = results[:5]
    return random.choice(pool)


def download_freesound_preview(sound: dict, output_path: Path) -> None:
    """Download the HQ MP3 preview from a Freesound sound object."""
    import requests
    previews = sound.get("previews", {})
    url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
    if not url:
        raise RuntimeError(f"No preview URL in sound {sound.get('id')}")
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    config = load_config()
    output_dir = Path(args.output_dir)
    audio_dir = ensure_dir(output_dir / "audio")
    bgm_path = audio_dir / "bgm.mp3"

    state = StateManager()
    state.update_step("step-bgm-fetch", "running")

    if args.url or args.search:
        # --- YouTube / yt-dlp search mode ---
        target = args.url if args.url else f"ytsearch1:{args.search}"
        try:
            download_from_youtube(target, bgm_path)
        except Exception as e:
            print(f"ERROR: {e}")
            state.update_step("step-bgm-fetch", "failed")
            sys.exit(1)

    else:
        # --- Freesound mode ---
        api_key = config.get("freesound_api_key")
        if not api_key:
            print("ERROR: FREESOUND_API_KEY not set in .env")
            print("  Get a free key at https://freesound.org/apiv2/apply/")
            sys.exit(1)
        try:
            import requests
        except ImportError:
            print("ERROR: pip install requests")
            sys.exit(1)

        print(f"  Searching Freesound: '{args.query}'...")
        try:
            results = search_freesound(args.query, api_key)
        except Exception as e:
            print(f"ERROR searching Freesound: {e}")
            state.update_step("step-bgm-fetch", "failed")
            sys.exit(1)

        if not results:
            print(f"ERROR: No tracks found for '{args.query}'")
            state.update_step("step-bgm-fetch", "failed")
            sys.exit(1)

        track = pick_random_track(results)
        print(f"  Found: '{track.get('name')}' ({track.get('duration', '?'):.0f}s) [picked from top {min(5, len(results))}]")
        try:
            download_freesound_preview(track, bgm_path)
        except Exception as e:
            print(f"ERROR downloading preview: {e}")
            state.update_step("step-bgm-fetch", "failed")
            sys.exit(1)

    size_kb = bgm_path.stat().st_size // 1024
    print(f"  BGM saved: {bgm_path} ({size_kb}KB)")
    state.update_step("step-bgm-fetch", "completed", {"bgm_path": str(bgm_path)})


if __name__ == "__main__":
    main()
