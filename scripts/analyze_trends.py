"""
YouTube trend analysis — searches for trending anime videos to inform topic selection.

Usage:
    python scripts/analyze_trends.py \
        --queries "top 5 strongest anime characters" "anime power ranking" \
        --days 30 \
        --min-duration 60 \
        --output-file output/trends_cache.json
"""
import argparse
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.youtube_auth import get_youtube_client

# Keywords that identify content we don't produce — excluded by default
DEFAULT_EXCLUDE_KEYWORDS = [
    "edit", "edits", "editing",
    "cosplay",
    "gaming", "game", "roblox",
    "hindi", "dubbed",
    "meme", "memes",
    "reaction", "reacts",
    "amv",
    "wallpaper", "soundtrack", "ost",
    "speedpaint", "drawing",
]


def parse_duration_seconds(iso: str) -> int:
    """Convert ISO 8601 duration (PT1M30S) to total seconds."""
    if not iso:
        return 0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def is_relevant(title: str, duration_seconds: int, exclude_keywords: list[str],
                min_duration: int, max_duration: int) -> bool:
    title_lower = title.lower()
    for kw in exclude_keywords:
        if kw in title_lower:
            return False
    if min_duration and duration_seconds < min_duration:
        return False
    if max_duration and duration_seconds > max_duration:
        return False
    return True


def search_videos(youtube, query: str, days: int, max_results: int = 10) -> list[dict]:
    """Search YouTube for videos matching query published within the last N days."""
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = youtube.search().list(
        q=query,
        type="video",
        order="viewCount",
        part="snippet",
        maxResults=max_results,
        publishedAfter=published_after,
    ).execute()

    results = []
    for item in response.get("items", []):
        snippet = item["snippet"]
        results.append({
            "video_id": item["id"]["videoId"],
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "publish_date": snippet["publishedAt"][:10],
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        })
    return results


def fetch_video_stats(youtube, video_ids: list[str]) -> dict[str, dict]:
    """Fetch view counts and durations for a list of video IDs (batched, max 50)."""
    stats = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        response = youtube.videos().list(
            id=",".join(batch),
            part="statistics,contentDetails",
        ).execute()
        for item in response.get("items", []):
            stats[item["id"]] = {
                "views": int(item.get("statistics", {}).get("viewCount", 0)),
                "duration_iso": item.get("contentDetails", {}).get("duration", ""),
            }
    return stats


def run_trend_analysis(queries: list[str], days: int, config: dict,
                       exclude_keywords: list[str], min_duration: int,
                       max_duration: int) -> dict:
    """Run trend analysis for all queries and return deduplicated, filtered, views-sorted results."""
    if len(queries) > 10:
        print("ERROR: Too many queries (>10 = >1000 quota units). Reduce the number of queries.")
        sys.exit(1)
    print(f"INFO: Will consume ~{len(queries) * 100} quota units for search (budget: 10,000/day)")

    youtube = get_youtube_client(config)

    all_videos: dict[str, dict] = {}
    for query in queries:
        print(f"  Searching: {query!r}")
        items = search_videos(youtube, query, days)
        for item in items:
            vid = item["video_id"]
            if vid not in all_videos:
                all_videos[vid] = item

    if not all_videos:
        print("WARNING: No videos found for the given queries.")
        return {"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "queries": queries, "videos": []}

    print(f"  Fetching stats for {len(all_videos)} unique videos...")
    stats = fetch_video_stats(youtube, list(all_videos.keys()))

    videos = []
    excluded = 0
    for vid_id, item in all_videos.items():
        s = stats.get(vid_id, {})
        duration_iso = s.get("duration_iso", "")
        duration_seconds = parse_duration_seconds(duration_iso)

        if not is_relevant(item["title"], duration_seconds, exclude_keywords, min_duration, max_duration):
            excluded += 1
            continue

        views = s.get("views", 0)
        # views_per_day: velocity metric — how many views/day since upload
        try:
            days_live = max(1, (date.today() - date.fromisoformat(item["publish_date"])).days)
        except Exception:
            days_live = 1
        views_per_day = round(views / days_live)

        videos.append({
            "video_id": vid_id,
            "title": item["title"],
            "channel": item["channel"],
            "views": views,
            "views_per_day": views_per_day,
            "days_live": days_live,
            "publish_date": item["publish_date"],
            "duration_seconds": duration_seconds,
            "duration_iso": duration_iso,
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "thumbnail": item["thumbnail"],
        })

    if excluded:
        print(f"  Filtered out {excluded} irrelevant videos (edits, cosplay, gaming, etc.)")

    videos.sort(key=lambda v: v["views"], reverse=True)

    return {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queries": queries,
        "filters": {
            "exclude_keywords": exclude_keywords,
            "min_duration_seconds": min_duration,
            "max_duration_seconds": max_duration,
        },
        "videos": videos,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Search YouTube for trending anime narrated videos")
    parser.add_argument("--queries", nargs="+", required=True,
                        help="Search queries targeting narrated content")
    parser.add_argument("--days", type=int, default=30,
                        help="Look back N days (default: 30)")
    parser.add_argument("--max-results", type=int, default=10,
                        help="Max results per query (default: 10)")
    parser.add_argument("--min-duration", type=int, default=60,
                        help="Minimum video duration in seconds (default: 60, excludes Shorts)")
    parser.add_argument("--max-duration", type=int, default=0,
                        help="Maximum video duration in seconds (default: 0 = no limit)")
    parser.add_argument("--exclude-keywords", nargs="*", default=None,
                        help="Title keywords to exclude (default: edits, cosplay, gaming, etc.)")
    parser.add_argument("--no-default-exclusions", action="store_true",
                        help="Disable the default keyword exclusion list")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore existing cache and fetch fresh data only")
    parser.add_argument("--output-file", default="output/trends_cache.json",
                        help="Output JSON file (default: output/trends_cache.json)")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build exclusion list
    if args.no_default_exclusions:
        exclude_keywords = args.exclude_keywords or []
    else:
        exclude_keywords = list(DEFAULT_EXCLUDE_KEYWORDS)
        if args.exclude_keywords:
            exclude_keywords.extend(args.exclude_keywords)

    # Load existing cache — only keep entries published within the requested window
    # so stale videos from prior runs don't pollute fresh trend analysis
    cached_videos: dict[str, dict] = {}
    if output_path.exists() and not args.no_cache:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).date().isoformat()
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            kept = 0
            for v in existing.get("videos", []):
                if v.get("publish_date", "0000") >= cutoff:
                    cached_videos[v["video_id"]] = v
                    kept += 1
            print(f"  Loaded {kept} recent videos from cache (cutoff: {cutoff})")
        except Exception:
            pass

    print(f"Analyzing trends for {len(args.queries)} queries over the last {args.days} days...")
    if args.min_duration:
        print(f"  Filter: min duration {args.min_duration}s (excluding Shorts)")
    print(f"  Filter: excluding keywords — {', '.join(exclude_keywords[:8])}{'...' if len(exclude_keywords) > 8 else ''}")

    result = run_trend_analysis(
        args.queries, args.days, config,
        exclude_keywords=exclude_keywords,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
    )

    # Merge: new results override stale cached entries by video_id
    merged: dict[str, dict] = {**cached_videos}
    for v in result["videos"]:
        merged[v["video_id"]] = v
    result["videos"] = sorted(merged.values(), key=lambda v: v["views"], reverse=True)

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nTrend analysis saved: {output_path}")
    print(f"Found {len(result['videos'])} relevant videos (including cache).")
    if result["videos"]:
        print("\nTop 10 by views/day (fastest growing):")
        by_velocity = sorted(result["videos"], key=lambda v: v.get("views_per_day", 0), reverse=True)
        for v in by_velocity[:10]:
            vpd = f"{v.get('views_per_day', 0):,}/day"
            views_fmt = f"{v['views']:,} total"
            dur = v.get("duration_seconds", 0)
            dur_str = f"{dur//60}m{dur%60:02d}s" if dur else "?"
            title = v["title"][:55]
            print(f"  {vpd:>12}  ({views_fmt:>14})  {dur_str:>7}  {v['publish_date']}  {title}")

        print("\nTop 10 by total views:")
        for v in result["videos"][:10]:
            vpd = f"{v.get('views_per_day', 0):,}/day"
            views_fmt = f"{v['views']:,}"
            dur = v.get("duration_seconds", 0)
            dur_str = f"{dur//60}m{dur%60:02d}s" if dur else "?"
            title = v["title"][:55]
            print(f"  {views_fmt:>12} views  {vpd:>12}  {dur_str:>7}  {v['publish_date']}  {title}")


if __name__ == "__main__":
    main()
