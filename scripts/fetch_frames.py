"""
Fetch anime frames/clips from Tenor (primary) or Sakugabooru (fallback).
Tenor supports character-level searches: "madara naruto", "saitama one punch man".
Sakugabooru requires series-level tags only: "naruto fighting", "dragon_ball animated".

Usage:
    python scripts/fetch_frames.py --script-path output/run-001/script/script.json --output-dir output/run-001
    python scripts/fetch_frames.py --tags "madara naruto" --limit 10 --output-dir output/run-001
    python scripts/fetch_frames.py --source sakugabooru --script-path ... --output-dir ...
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.file_helpers import ensure_dir, download_file
from scripts.utils.state_manager import StateManager

SAKUGABOORU_API = "https://www.sakugabooru.com/post.json"
TENOR_API = "https://api.tenor.com/v1/search"


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch anime frames/clips")
    parser.add_argument("--script-path", default=None, help="Path to script.json (auto-extract tags)")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--tags", default=None, help="Manual search tags (space-separated)")
    parser.add_argument("--limit", type=int, default=20, help="Max posts to fetch per query")
    parser.add_argument("--source", default="tenor", choices=["tenor", "sakugabooru", "local"],
                        help="Clip source (default: tenor)")
    parser.add_argument("--local-dir", default=None, help="Path to local frames directory (for source=local)")
    return parser.parse_args()


# ─── Tenor ────────────────────────────────────────────────────────────────────

def search_tenor(query: str, api_key: str, limit: int = 10) -> list[dict]:
    import httpx
    params = {"q": query, "key": api_key, "limit": limit, "media_filter": "minimal"}
    with httpx.Client(timeout=30) as client:
        response = client.get(TENOR_API, params=params)
        response.raise_for_status()
        return response.json().get("results", [])


def best_tenor_mp4(result: dict) -> str | None:
    """Pick the highest-resolution MP4 from a Tenor result."""
    media = result.get("media", [{}])[0]
    # Prefer loopedmp4 (already looped) > mp4 > tinymp4
    for fmt in ("loopedmp4", "mp4", "tinymp4", "webm", "tinywebm"):
        url = media.get(fmt, {}).get("url")
        if url:
            return url
    return None


def download_tenor_clips(results: list[dict], output_dir: Path, prefix: str, max_files: int = 1) -> list[Path]:
    downloaded = []
    # Sort by mp4 size descending to prefer higher quality
    def mp4_size(r):
        return r.get("media", [{}])[0].get("mp4", {}).get("size", 0)

    for result in sorted(results, key=mp4_size, reverse=True)[:max_files]:
        url = best_tenor_mp4(result)
        if not url:
            continue
        ext = "mp4" if "mp4" in url else "webm"
        dest = output_dir / f"{prefix}_01.{ext}"
        try:
            download_file(url, dest, timeout=60)
            downloaded.append(dest)
        except Exception as e:
            print(f"  Failed to download {url}: {e}")
    return downloaded


# ─── Sakugabooru ──────────────────────────────────────────────────────────────

def search_sakugabooru(tags: str, limit: int = 20, page: int = 1) -> list[dict]:
    import httpx
    params = {"tags": tags, "limit": limit, "page": page}
    with httpx.Client(timeout=30) as client:
        response = client.get(SAKUGABOORU_API, params=params)
        response.raise_for_status()
        return response.json()


def download_sakugabooru_posts(posts: list[dict], output_dir: Path, prefix: str, max_files: int = 1) -> list[Path]:
    downloaded = []
    for post in posts[:max_files]:
        file_url = post.get("file_url")
        if not file_url:
            continue
        if file_url.startswith("//"):
            file_url = "https:" + file_url
        ext = file_url.split(".")[-1].split("?")[0]
        if ext not in ("mp4", "webm", "gif", "png", "jpg"):
            ext = "mp4"
        dest = output_dir / f"{prefix}_01.{ext}"
        try:
            download_file(file_url, dest, timeout=60)
            downloaded.append(dest)
        except Exception as e:
            print(f"  Failed to download {file_url}: {e}")
    return downloaded


# ─── Tag helpers ──────────────────────────────────────────────────────────────

def get_scene_query(scene: dict) -> str:
    """Return the search query for a scene, preferring explicit search_tags."""
    tags = scene.get("search_tags", "").strip()
    return tags if tags else "anime fighting animated"


# ─── Main ─────────────────────────────────────────────────────────────────────

def fetch_scene_clip(query: str, output_dir: Path, prefix: str, source: str, config: dict) -> list[Path]:
    """Fetch one clip for a scene. Tries Tenor first, falls back to Sakugabooru."""
    if source == "tenor":
        results = search_tenor(query, config["tenor_api_key"], limit=10)
        if results:
            return download_tenor_clips(results, output_dir, prefix, max_files=1)
        # Fallback: try Sakugabooru with series-only terms
        print(f"    Tenor: no results, trying Sakugabooru fallback...")
        fallback_tags = " ".join(query.split()[-2:])  # last 2 words as series tags
        posts = search_sakugabooru(fallback_tags, limit=5)
        if not posts:
            posts = search_sakugabooru("animated effects", limit=5)
        return download_sakugabooru_posts(posts, output_dir, prefix, max_files=1)

    elif source == "sakugabooru":
        posts = search_sakugabooru(query, limit=20)
        if not posts:
            print(f"    No results, trying broader search...")
            posts = search_sakugabooru("animated effects", limit=5)
        return download_sakugabooru_posts(posts, output_dir, prefix, max_files=1)

    return []


def main():
    args = parse_args()
    config = load_config()

    output_dir = Path(args.output_dir)
    frames_dir = ensure_dir(output_dir / "frames")

    state = StateManager()
    state.update_step("step-02-fetch-frames", "running")

    if args.source == "local":
        if not args.local_dir:
            print("ERROR: --local-dir required when source=local")
            sys.exit(1)
        local_path = Path(args.local_dir)
        if not local_path.exists():
            print(f"ERROR: Local directory not found: {local_path}")
            sys.exit(1)
        import shutil
        files = sorted(local_path.glob("*.*"))
        for i, f in enumerate(files):
            dest = frames_dir / f"scene_{i+1:02d}{f.suffix}"
            shutil.copy2(f, dest)
        print(f"Copied {len(files)} files from local directory")
        state.update_step("step-02-fetch-frames", "completed", {"frame_paths": [str(f) for f in files]})
        return

    source_label = "Tenor" if args.source == "tenor" else "Sakugabooru"

    if args.script_path:
        script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
        scenes = script.get("scenes", [])
        print(f"Fetching clips for {len(scenes)} scenes from {source_label}...")

        all_paths = []
        for i, scene in enumerate(scenes):
            query = get_scene_query(scene)
            print(f"  Scene {i+1}: searching '{query}'...")
            paths = fetch_scene_clip(query, frames_dir, f"scene_{i+1:02d}", args.source, config)
            all_paths.extend(paths)
            if paths:
                print(f"  Scene {i+1}: downloaded {len(paths)} clip(s)")
            else:
                print(f"  Scene {i+1}: WARNING — no clip found")
            time.sleep(0.5)  # light rate limiting

        print(f"\nTotal: {len(all_paths)} clips downloaded")
        state.update_step("step-02-fetch-frames", "completed", {
            "frame_paths": [str(p) for p in all_paths],
            "total_clips": len(all_paths),
        })

    elif args.tags:
        print(f"Searching {source_label} for: '{args.tags}'...")
        paths = fetch_scene_clip(args.tags, frames_dir, "clip", args.source, config)
        print(f"Downloaded {len(paths)} clips")
        state.update_step("step-02-fetch-frames", "completed", {
            "frame_paths": [str(p) for p in paths],
            "total_clips": len(paths),
        })

    else:
        print("ERROR: Provide either --script-path or --tags")
        sys.exit(1)


if __name__ == "__main__":
    main()
