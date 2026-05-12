"""
YouTube trend analysis — searches for trending anime videos to inform topic selection.

Usage:
    python scripts/analyze_trends.py \
        --queries "anime power ranking" "top anime 2026" \
        --days 30 \
        --output-file output/trends_cache.json
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.youtube_auth import get_youtube_client


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


def run_trend_analysis(queries: list[str], days: int, config: dict) -> dict:
    """Run trend analysis for all queries and return deduplicated, views-sorted results."""
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
    for vid_id, item in all_videos.items():
        s = stats.get(vid_id, {})
        videos.append({
            "video_id": vid_id,
            "title": item["title"],
            "channel": item["channel"],
            "views": s.get("views", 0),
            "publish_date": item["publish_date"],
            "duration_iso": s.get("duration_iso", ""),
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "thumbnail": item["thumbnail"],
        })

    videos.sort(key=lambda v: v["views"], reverse=True)

    return {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queries": queries,
        "videos": videos,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Search YouTube for trending anime videos")
    parser.add_argument("--queries", nargs="+", required=True,
                        help="Search queries (e.g. 'anime power ranking' 'top anime 2026')")
    parser.add_argument("--days", type=int, default=30,
                        help="Look back N days (default: 30)")
    parser.add_argument("--max-results", type=int, default=10,
                        help="Max results per query (default: 10)")
    parser.add_argument("--output-file", default="output/trends_cache.json",
                        help="Output JSON file (default: output/trends_cache.json)")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing cache so results accumulate across runs
    cached_videos: dict[str, dict] = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            for v in existing.get("videos", []):
                cached_videos[v["video_id"]] = v
            print(f"  Loaded {len(cached_videos)} videos from existing cache")
        except Exception:
            pass

    print(f"Analyzing trends for {len(args.queries)} queries over the last {args.days} days...")
    result = run_trend_analysis(args.queries, args.days, config)

    # Merge: new results override stale cached entries by video_id
    merged: dict[str, dict] = {**cached_videos}
    for v in result["videos"]:
        merged[v["video_id"]] = v
    result["videos"] = sorted(merged.values(), key=lambda v: v["views"], reverse=True)

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nTrend analysis saved: {output_path}")
    print(f"Found {len(result['videos'])} unique videos (including cache).")
    if result["videos"]:
        print("\nTop 5 by views:")
        for v in result["videos"][:5]:
            views_fmt = f"{v['views']:,}"
            title = v['title'][:60]
            print(f"  {views_fmt:>12} views  {v['publish_date']}  {title}")


if __name__ == "__main__":
    main()
