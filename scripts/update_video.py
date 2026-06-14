"""
Post-publish video updater — updates description (with chapters), tags, and privacy.

Run after publish_youtube.py has uploaded the video. Automates AMV Step 14 items 1–3:
  1. Rebuild description with chapter timestamps + hashtags
  2. Push comprehensive tags
  3. Make video public (only when published as private; skip for --publish-at schedules)

Usage:
    # Update chapters + tags, then make public
    python scripts/update_video.py \
        --video-id "dQw4w9WgXcQ" \
        --script-path output/20260613-top5-db-villains/script/script.json \
        --make-public

    # Update chapters + tags only (leave privacy unchanged)
    python scripts/update_video.py \
        --video-id "dQw4w9WgXcQ" \
        --script-path output/20260613-top5-db-villains/script/script.json

    # Dry-run: print what would be sent without calling the API
    python scripts/update_video.py \
        --video-id "dQw4w9WgXcQ" \
        --script-path output/20260613-top5-db-villains/script/script.json \
        --make-public \
        --dry-run
"""
import argparse
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.youtube_auth import get_youtube_client

CATEGORY_MAP = {
    "anime": "1",
    "amv": "1",
}


# ---------------------------------------------------------------------------
# Chapter generation
# ---------------------------------------------------------------------------

def format_timestamp(total_seconds: float) -> str:
    """Convert seconds to MM:SS (or H:MM:SS for videos over an hour)."""
    t = int(total_seconds)
    h, remainder = divmod(t, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_chapters(scenes: list[dict]) -> str:
    """Build YouTube chapter lines from script scenes.

    Only emits a chapter line when the scene_type or rank changes, so the
    chapters list stays readable (not one entry per scene).
    """
    lines = []
    cursor = 0.0
    last_label = None

    for scene in scenes:
        scene_type = scene.get("scene_type", "normal")
        rank = scene.get("rank")
        name = scene.get("name", "")
        duration = float(scene.get("duration_seconds", 0))

        if scene_type == "intro":
            label = "Intro"
        elif scene_type == "rank_transition" and rank is not None:
            label = f"#{rank} — {name}" if name else f"#{rank}"
        else:
            label = None  # normal content scenes don't get their own chapter line

        if label and label != last_label:
            lines.append(f"{format_timestamp(cursor)} {label}")
            last_label = label

        cursor += duration

    return "\n".join(lines)


def build_description(script: dict) -> str:
    """Reconstruct description with chapters block and hashtags appended."""
    base_description = script.get("description", "").strip()
    scenes = script.get("scenes", [])
    tags = script.get("tags", [])

    chapters = build_chapters(scenes)

    # Build hashtags from tags (max 15, YouTube limit)
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:15])

    parts = []
    if base_description:
        parts.append(base_description)
    if chapters:
        parts.append(chapters)
    if hashtags:
        parts.append(hashtags)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Tag expansion
# ---------------------------------------------------------------------------

def build_tags(script: dict) -> list[str]:
    """Expand script tags with additional SEO keywords from scene names and content type."""
    base_tags = list(script.get("tags", []))

    # Pull anime names from rank_transition scenes
    rank_names = [
        scene["name"]
        for scene in script.get("scenes", [])
        if scene.get("scene_type") == "rank_transition" and scene.get("name")
    ]

    content_type = script.get("content_type", "anime")
    generic_tags = ["anime", "anime ranking", "anime top 5", "anime analysis"]
    if content_type in ("anime", "amv"):
        generic_tags += ["anime 2025", "best anime", "anime characters"]

    all_tags = base_tags + rank_names + generic_tags

    # Deduplicate while preserving order; YouTube allows up to 500 chars total
    seen: set[str] = set()
    deduped: list[str] = []
    total_chars = 0
    for tag in all_tags:
        tag = tag.strip()
        key = tag.lower()
        if key in seen or not tag:
            continue
        seen.add(key)
        total_chars += len(tag) + 1  # +1 for the comma separator
        if total_chars > 490:
            break
        deduped.append(tag)

    return deduped


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_current_snippet(youtube, video_id: str) -> dict:
    """Fetch the video's current snippet (needed for a full videos().update() call)."""
    response = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        print(f"ERROR: Video {video_id!r} not found or not accessible.")
        sys.exit(1)
    return items[0]


def update_video(youtube, video_id: str, snippet: dict, new_status: dict | None) -> dict:
    """Call videos().update() with the patched snippet and optional status."""
    body = {"id": video_id, "snippet": snippet}
    parts = ["snippet"]
    if new_status:
        body["status"] = new_status
        parts.append("status")

    return youtube.videos().update(part=",".join(parts), body=body).execute()


# ---------------------------------------------------------------------------
# Argument parsing + main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Update YouTube video: chapters in description, expanded tags, optional make-public",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--video-id", required=True, help="YouTube video ID to update")
    parser.add_argument("--script-path", required=True, help="Path to script.json for this video")
    parser.add_argument(
        "--make-public", action="store_true",
        help="Change privacy from private/unlisted to public after updating metadata",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be sent to the API without making any changes",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()

    script_path = Path(args.script_path)
    if not script_path.exists():
        print(f"ERROR: script.json not found: {script_path}")
        sys.exit(1)

    script = json.loads(script_path.read_text(encoding="utf-8"))

    print(f"Fetching current video metadata for {args.video_id}...")
    youtube = get_youtube_client(config)

    current = fetch_current_snippet(youtube, args.video_id)
    current_snippet = current["snippet"]
    current_status = current["status"]

    # Build updated fields
    new_description = build_description(script)
    new_tags = build_tags(script)

    updated_snippet = {
        **current_snippet,
        "description": new_description,
        "tags": new_tags,
        "categoryId": CATEGORY_MAP.get(script.get("content_type", "anime"), "1"),
    }

    new_status = None
    if args.make_public:
        current_privacy = current_status.get("privacyStatus", "private")
        if current_privacy == "public":
            print("  Video is already public — skipping privacy update.")
        elif current_status.get("publishAt"):
            print("  Video has a scheduled publish time (--publish-at was used) — skipping make-public.")
            print("  It will go public automatically at the scheduled time.")
        else:
            new_status = {**current_status, "privacyStatus": "public"}

    # Print preview
    print("\n" + "=" * 70)
    print("DESCRIPTION PREVIEW")
    print("=" * 70)
    print(new_description[:1000] + ("..." if len(new_description) > 1000 else ""))

    print("\n" + "=" * 70)
    print(f"TAGS ({len(new_tags)} total)")
    print("=" * 70)
    print(", ".join(new_tags))

    if new_status:
        print(f"\nPRIVACY: {current_status.get('privacyStatus')} → public")

    if args.dry_run:
        print("\n[DRY-RUN] No changes made. Remove --dry-run to apply.")
        return

    print("\nApplying updates...")
    result = update_video(youtube, args.video_id, updated_snippet, new_status)

    privacy_now = result.get("status", {}).get("privacyStatus", "?")
    print(f"  Updated successfully.")
    print(f"  Title:   {result['snippet']['title']}")
    print(f"  Privacy: {privacy_now}")
    print(f"  Tags:    {len(result['snippet'].get('tags', []))} tags set")
    print(f"\n  Studio: https://studio.youtube.com/video/{args.video_id}/edit")


if __name__ == "__main__":
    main()
