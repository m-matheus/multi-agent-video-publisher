"""
YouTube channel analytics — fetches performance metrics to inform content strategy.

Usage:
    python scripts/analyze_channel.py \
        --days 90 \
        --output-file output/channel_analytics.json \
        --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.youtube_auth import get_youtube_client, get_youtube_analytics_client


def fetch_channel_analytics(analytics, channel_id: str, start: str, end: str,
                            dimensions: str = "video", max_results: int = 25) -> dict:
    """Query YouTube Analytics API for channel metrics."""
    params = dict(
        ids=f"channel=={channel_id}",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,likes,shares",
        sort="-views",
        maxResults=max_results,
    )
    if dimensions:
        params["dimensions"] = dimensions

    response = analytics.reports().query(**params).execute()
    return response


def fetch_video_titles(youtube, video_ids: list[str]) -> dict[str, str]:
    """Fetch video titles for a list of video IDs."""
    titles = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        response = youtube.videos().list(id=",".join(batch), part="snippet").execute()
        for item in response.get("items", []):
            titles[item["id"]] = item["snippet"]["title"]
    return titles


def compute_growth(last_views: int, prev_views: int) -> dict:
    growth_pct = ((last_views - prev_views) / prev_views * 100) if prev_views > 0 else 0.0
    return {
        "views_last_30d": last_views,
        "views_prev_30d": prev_views,
        "growth_pct": round(growth_pct, 1),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch YouTube channel analytics")
    parser.add_argument("--days", type=int, default=90,
                        help="Analysis period in days (default: 90)")
    parser.add_argument("--channel-id", default=None,
                        help="YouTube channel ID (defaults to YOUTUBE_CHANNEL_ID in .env)")
    parser.add_argument("--output-file", default="output/channel_analytics.json",
                        help="Output JSON file (default: output/channel_analytics.json)")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()

    channel_id = args.channel_id or config.get("youtube_channel_id")
    if not channel_id:
        print("ERROR: No channel ID found. Pass --channel-id or set YOUTUBE_CHANNEL_ID in .env")
        sys.exit(1)

    print(f"Fetching analytics for channel {channel_id} (last {args.days} days)...")

    youtube = get_youtube_client(config)
    try:
        analytics = get_youtube_analytics_client(config)
    except Exception as e:
        print(f"ERROR: Could not initialize YouTube Analytics client: {e}")
        print("  Make sure the 'YouTube Analytics API' is enabled in your Google Cloud project")
        print("  and included in your OAuth consent screen scopes.")
        sys.exit(1)

    today = date.today()
    end_str = today.strftime("%Y-%m-%d")
    start_full = (today - timedelta(days=args.days)).strftime("%Y-%m-%d")
    start_last30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    start_prev30 = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    end_prev30 = (today - timedelta(days=31)).strftime("%Y-%m-%d")

    # 1. Full period by video (for top videos ranking)
    print("  Fetching per-video metrics...")
    try:
        full_data = fetch_channel_analytics(analytics, channel_id, start_full, end_str, dimensions="video")
    except Exception as e:
        err = str(e)
        if "403" in err or "401" in err or "accessNotConfigured" in err or "insufficientPermissions" in err:
            print(f"ERROR: YouTube Analytics API access denied (channel: {channel_id})")
            print("  Check that the YouTube Analytics Read API is enabled and your OAuth token has the")
            print("  'https://www.googleapis.com/auth/yt-analytics.readonly' scope.")
            print(f"  Details: {err[:300]}")
        else:
            print(f"ERROR fetching analytics: {e}")
        sys.exit(1)
    column_headers = [h["name"] for h in (full_data.get("columnHeaders") or [])]
    rows = full_data.get("rows") or []

    top_videos = []
    video_ids = []
    for row in rows:
        row_dict = dict(zip(column_headers, row))
        vid_id = row_dict.get("video", "")
        if vid_id:
            video_ids.append(vid_id)
            top_videos.append({
                "video_id": vid_id,
                "views": int(row_dict.get("views", 0)),
                "watch_minutes": int(row_dict.get("estimatedMinutesWatched", 0)),
                "avg_view_duration_seconds": int(row_dict.get("averageViewDuration", 0)),
                "subscribers_gained": int(row_dict.get("subscribersGained", 0)),
                "likes": int(row_dict.get("likes", 0)),
                "shares": int(row_dict.get("shares", 0)),
            })

    # Fetch video titles
    if video_ids:
        print(f"  Fetching titles for {len(video_ids)} videos...")
        titles = fetch_video_titles(youtube, video_ids)
        for v in top_videos:
            title = titles.get(v["video_id"])
            if title is None:
                print(f"  WARNING: Title not found for video {v['video_id']} (may be deleted or private)")
                title = "(unknown title)"
            v["title"] = title

    # 2. Last 30 days aggregate
    print("  Fetching last 30-day aggregate...")
    last30_data = fetch_channel_analytics(analytics, channel_id, start_last30, end_str, dimensions="")
    last30_rows = last30_data.get("rows") or []
    last30_views = int(last30_rows[0][0]) if last30_rows else 0

    # 3. Previous 30 days aggregate
    print("  Fetching previous 30-day aggregate...")
    prev30_data = fetch_channel_analytics(analytics, channel_id, start_prev30, end_prev30, dimensions="")
    prev30_rows = prev30_data.get("rows") or []
    prev30_views = int(prev30_rows[0][0]) if prev30_rows else 0

    # Compute totals from full period rows
    total_views = sum(v["views"] for v in top_videos)
    total_watch_minutes = sum(v["watch_minutes"] for v in top_videos)
    total_subscribers = sum(v["subscribers_gained"] for v in top_videos)

    result = {
        "fetched_at": date.today().isoformat(),
        "period_days": args.days,
        "channel_id": channel_id,
        "summary": {
            "total_views": total_views,
            "total_watch_minutes": total_watch_minutes,
            "subscribers_gained": total_subscribers,
            "top_videos": top_videos[:10],
        },
        "trend": compute_growth(last30_views, prev30_views),
    }

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nChannel analytics saved: {output_path}")
    print(f"  Total views ({args.days}d): {total_views:,}")
    print(f"  Last 30d growth: {result['trend']['views_last_30d']:,} vs {result['trend']['views_prev_30d']:,} ({result['trend']['growth_pct']:+.1f}%)")
    if top_videos:
        print(f"  Top video: {top_videos[0].get('title', top_videos[0]['video_id'])} — {top_videos[0]['views']:,} views")


if __name__ == "__main__":
    main()
