"""
YouTube trend analysis — searches for trending anime videos to inform topic selection.

Usage (default — uses built-in query bank):
    python scripts/analyze_trends.py \
        --days 30 \
        --min-duration 60 \
        --channel-cache output/channel_analytics.json \
        --output-file output/trends_cache.json

    # Extra queries for anime currently in the news:
    python scripts/analyze_trends.py --boost-anime "Solo Leveling" "Dandadan"

    # Custom queries (replaces the built-in bank entirely):
    python scripts/analyze_trends.py --queries "top 5 strongest anime" "demon slayer ranking"
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

# ---------------------------------------------------------------------------
# Exclusion filters
# ---------------------------------------------------------------------------
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
    "unboxing",
]

# ---------------------------------------------------------------------------
# Built-in query bank
# Organized by tier so the most signal-rich queries run first.
# ---------------------------------------------------------------------------
QUERY_BANK = [
    # Tier 1 — format-first (directly targets ranking/analysis content)
    "top 5 strongest anime characters",
    "top 10 anime power ranking",
    "strongest anime villain ranked",
    "best anime fights of all time ranked",
    "most powerful anime characters 2025",
    "anime character power tier list 2025",

    # Tier 2 — top franchise ranking queries (evergreen, high search volume)
    "dragon ball strongest characters ranked",
    "naruto strongest characters ranking",
    "one piece power ranking 2025",
    "demon slayer strongest characters ranked",
    "jujutsu kaisen strongest characters ranked",
    "attack on titan strongest characters ranked",
    "bleach strongest characters ranked",
    "my hero academia strongest heroes ranked",

    # Tier 3 — rising / recently popular franchises
    "solo leveling strongest characters ranked",
    "chainsaw man power ranking",
    "frieren anime strongest characters",
    "blue lock best players ranked",
    "vinland saga strongest warriors ranked",
    "kaiju no 8 strongest characters",
    "black clover strongest characters ranked",
    "hunter x hunter strongest characters ranked",
    "one punch man strongest characters ranked",
    "fairy tail strongest characters ranked",

    # Tier 4 — isekai (separate niche with massive audience)
    "best isekai anime to watch 2025",
    "top 10 isekai anime ranked",
    "isekai anime with overpowered mc",
    "strongest isekai main character ranked",
    "most overpowered isekai protagonist",

    # Tier 5 — overpowered MC (cross-genre, high search intent)
    "most overpowered anime mc ranked",
    "top 5 overpowered anime protagonist",
    "anime with strongest main character",
    "op mc anime you need to watch",

    # Tier 6 — anime recommendations / watch lists (discovery content)
    "best anime to watch 2025",
    "most underrated anime of all time",
    "anime you need to watch before you die",
    "best anime series ranked 2025",
    "anime with best story ranked",
]

# ---------------------------------------------------------------------------
# Franchise keyword map
# Maps canonical franchise name → keywords to detect in video titles.
# Keys are the canonical name; values are lowercase substrings.
# ---------------------------------------------------------------------------
FRANCHISE_MAP: dict[str, list[str]] = {
    "Dragon Ball": [
        "dragon ball", "goku", "vegeta", "frieza", "cell dragon", "beerus",
        "broly", "gohan", "piccolo", "jiren", "ultra instinct",
    ],
    "Naruto": [
        "naruto", "sasuke", "itachi", "kakashi", "madara", "minato uchiha",
        "tsunade", "gaara", "obito", "boruto",
    ],
    "One Piece": [
        "one piece", "luffy", "roronoa zoro", "sanji straw", "boa hancock",
        "kaido one", "shanks one piece", "blackbeard one piece", "akainu",
        "portgas d ace",
    ],
    "Demon Slayer": [
        "demon slayer", "kimetsu no yaiba", "tanjiro", "nezuko", "muzan",
        "rengoku", "kokushibo", "doma demon",
    ],
    "Jujutsu Kaisen": [
        "jujutsu kaisen", "jjk", "satoru gojo", "yuji itadori", "sukuna",
        "megumi fushiguro", "nobara kugisaki",
    ],
    "Attack on Titan": [
        "attack on titan", "shingeki no kyojin", "eren yeager", "mikasa",
        "levi ackerman", "armin arlert", "founding titan",
    ],
    "Bleach": [
        "bleach anime", "ichigo kurosaki", "sosuke aizen", "kenpachi zaraki",
        "byakuya kuchiki", "yhwach", "zangetsu",
    ],
    "My Hero Academia": [
        "my hero academia", "boku no hero", "izuku midoriya", "katsuki bakugo",
        "all might", "shoto todoroki", "endeavor hero",
    ],
    "Solo Leveling": [
        "solo leveling", "sung jin-woo", "sung jinwoo", "shadow monarch",
    ],
    "Chainsaw Man": [
        "chainsaw man", "denji chainsaw", "makima chainsaw", "pochita",
        "power chainsaw", "fujimoto",
    ],
    "Frieren": [
        "frieren", "frieren beyond journey",
    ],
    "Blue Lock": [
        "blue lock", "isagi yoichi", "bachira meguru", "rin itoshi",
    ],
    "Vinland Saga": [
        "vinland saga", "thorfinn vinland", "askeladd",
    ],
    "Kaiju No. 8": [
        "kaiju no 8", "kaiju no8", "kafka hibino",
    ],
    "Black Clover": [
        "black clover", "asta black clover", "julius novachrono",
    ],
    "Fairy Tail": [
        "fairy tail", "natsu dragneel", "erza scarlet", "zeref fairy",
    ],
    "Hunter x Hunter": [
        "hunter x hunter", "hxh", "killua zoldyck", "hisoka morow",
        "meruem hxh", "gon freecss",
    ],
    "Fullmetal Alchemist": [
        "fullmetal alchemist", "fmab", "edward elric", "roy mustang",
        "alphonse elric",
    ],
    "One Punch Man": [
        "one punch man", "opm", "saitama one punch", "garou one punch",
        "blast one punch",
    ],
    "Re:Zero": [
        "re:zero", "rezero", "subaru natsuki", "emilia re:zero",
    ],
    "Overlord": [
        "overlord anime", "ainz ooal gown", "albedo overlord",
    ],
    "Dandadan": [
        "dandadan", "momo ayase", "okarun dandadan",
    ],
    "Spy x Family": [
        "spy x family", "loid forger", "anya forger", "yor forger",
    ],
    "Mob Psycho": [
        "mob psycho", "shigeo kageyama", "reigen arataka",
    ],
    "Tokyo Ghoul": [
        "tokyo ghoul", "ken kaneki",
    ],
    "Mushoku Tensei": [
        "mushoku tensei", "rudeus greyrat",
    ],
    "Sword Art Online": [
        "sword art online", "kirito sao", "asuna sao",
    ],
    "Code Geass": [
        "code geass", "lelouch vi britannia", "zero code geass",
    ],
    "Oshi no Ko": [
        "oshi no ko", "aqua hoshino", "ruby hoshino", "ai hoshino",
    ],
    "Hell's Paradise": [
        "hell's paradise", "jigokuraku", "gabimaru",
    ],
}

# ---------------------------------------------------------------------------
# Format detection patterns
# ---------------------------------------------------------------------------
FORMAT_PATTERNS: dict[str, list[str]] = {
    "ranking": [
        r"top\s+\d+", r"rank(ed|ing)", r"tier\s+list", r"best\s+\d+",
        r"strongest\s+\d+", r"most\s+powerful",
    ],
    "vs": [
        r"\bvs\.?\b", r"\bversus\b",
    ],
    "lore": [
        r"\bexplain(ed)?\b", r"\blore\b", r"\borigin\b", r"\bhistory\b",
        r"\bstory\s+of\b", r"\bwho\s+is\b",
    ],
    "analysis": [
        r"\banalys(is|ed)\b", r"\bbreakdown\b", r"\bpower\s+level\b",
        r"\bhow\s+(strong|powerful)\b",
    ],
    "news": [
        r"\bannounced?\b", r"\bnew\s+season\b", r"\brelease\s+date\b",
        r"\btrailer\b", r"\bofficial\b",
    ],
    "isekai": [
        r"\bisekai\b",
    ],
    "overpowered": [
        r"\boverpowered\b", r"\bop\s+mc\b", r"\bop\s+protagonist\b",
        r"\boverpowered\s+(mc|protagonist|main\s+character)\b",
    ],
    "recommendation": [
        r"\bto\s+watch\b", r"\byou\s+need\s+to\s+watch\b", r"\bbest\s+anime\b",
        r"\bunderrated\b", r"\bmust\s+watch\b", r"\bbefore\s+you\s+die\b",
        r"\bbinge\b",
    ],
}


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def detect_anime(title: str) -> str:
    """Return the canonical franchise name found in the title, or 'Unknown'."""
    t = title.lower()
    for franchise, keywords in FRANCHISE_MAP.items():
        for kw in keywords:
            if kw in t:
                return franchise
    return "Unknown"


def detect_format(title: str) -> str:
    """Return the content format type detected in the title."""
    t = title.lower()
    for fmt, patterns in FORMAT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, t):
                return fmt
    return "other"


# ---------------------------------------------------------------------------
# YouTube API helpers
# ---------------------------------------------------------------------------

def parse_duration_seconds(iso: str) -> int:
    """Convert ISO 8601 duration (PT1M30S) to total seconds."""
    if not iso:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def is_relevant(title: str, duration_seconds: int, exclude_keywords: list[str],
                min_duration: int, max_duration: int) -> bool:
    t = title.lower()
    for kw in exclude_keywords:
        if kw in t:
            return False
    if min_duration and duration_seconds < min_duration:
        return False
    if max_duration and duration_seconds > max_duration:
        return False
    return True


def search_videos(youtube, query: str, days: int, max_results: int = 10) -> list[dict]:
    """Search YouTube for videos matching query published within the last N days."""
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        response = youtube.search().list(
            q=query,
            type="video",
            order="viewCount",
            part="snippet",
            maxResults=max_results,
            publishedAfter=published_after,
        ).execute()
    except Exception as e:
        print(f"  WARNING: Query failed ({query!r}): {e}")
        return []

    results = []
    for item in response.get("items", []):
        snippet = item["snippet"]
        results.append({
            "video_id": item["id"]["videoId"],
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "publish_date": snippet["publishedAt"][:10],
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            "matched_query": query,
        })
    return results


def fetch_video_stats(youtube, video_ids: list[str]) -> dict[str, dict]:
    """Fetch view counts and durations for a list of video IDs (batched, max 50)."""
    stats = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            response = youtube.videos().list(
                id=",".join(batch),
                part="statistics,contentDetails",
            ).execute()
            for item in response.get("items", []):
                stats[item["id"]] = {
                    "views": int(item.get("statistics", {}).get("viewCount", 0)),
                    "duration_iso": item.get("contentDetails", {}).get("duration", ""),
                }
        except Exception as e:
            print(f"  WARNING: Failed to fetch stats for batch: {e}")
    return stats


# ---------------------------------------------------------------------------
# Channel cache helpers
# ---------------------------------------------------------------------------

def load_channel_cache(cache_path: str) -> dict:
    """Load channel analytics cache produced by analyze_channel.py."""
    path = Path(cache_path)
    if not path.exists():
        print(f"  WARNING: Channel cache not found at {cache_path} — skipping dedup")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        total = len(data.get("all_videos", []))
        print(f"  Loaded channel cache: {total} existing videos for topic dedup")
        return data
    except Exception as e:
        print(f"  WARNING: Could not load channel cache: {e}")
        return {}


def build_channel_topic_set(channel_data: dict) -> set[str]:
    """Return the set of franchise names already covered on the channel."""
    covered: set[str] = set()
    for v in channel_data.get("all_videos", []):
        franchise = detect_anime(v.get("title", ""))
        if franchise != "Unknown":
            covered.add(franchise)
    return covered


# ---------------------------------------------------------------------------
# Boost query builder (for news-driven anime)
# ---------------------------------------------------------------------------

def build_boost_queries(anime_names: list[str]) -> list[str]:
    """Generate ranking-focused queries for specific anime in the news."""
    queries = []
    for name in anime_names:
        queries.append(f"{name} strongest characters ranked")
        queries.append(f"{name} power ranking top 5")
    return queries


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def run_trend_analysis(queries: list[str], days: int, config: dict,
                       exclude_keywords: list[str], min_duration: int,
                       max_duration: int, max_results_per_query: int = 10) -> dict:
    quota_est = len(queries) * 100
    print(f"INFO: Running {len(queries)} queries (~{quota_est} quota units, budget: 10,000/day)")
    if quota_est > 5000:
        print("  WARNING: High quota usage. Consider using --queries to narrow the bank.")

    youtube = get_youtube_client(config)

    all_videos: dict[str, dict] = {}
    for query in queries:
        print(f"  Searching: {query!r}")
        items = search_videos(youtube, query, days, max_results=max_results_per_query)
        for item in items:
            vid = item["video_id"]
            if vid not in all_videos:
                all_videos[vid] = item

    if not all_videos:
        print("WARNING: No videos found for the given queries.")
        return {
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "queries": queries,
            "videos": [],
        }

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
            "detected_anime": detect_anime(item["title"]),
            "detected_format": detect_format(item["title"]),
            "matched_query": item.get("matched_query", ""),
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


# ---------------------------------------------------------------------------
# Suggestions engine
# ---------------------------------------------------------------------------

def generate_suggestions(videos: list[dict], channel_topics: set[str],
                         top_n: int = 5) -> list[dict]:
    """Synthesize topic suggestions from trending videos not yet covered on the channel."""
    suggestions = []
    seen: set[str] = set()

    # Sort by velocity (views/day) — fastest-growing first
    by_velocity = sorted(videos, key=lambda v: v.get("views_per_day", 0), reverse=True)

    for v in by_velocity:
        franchise = v.get("detected_anime", "Unknown")
        fmt = v.get("detected_format", "other")

        # Cross-genre formats don't need a known franchise — use format as the dedup key
        dedup_key = fmt if fmt in ("isekai", "overpowered", "recommendation") else franchise
        if dedup_key == "Unknown" or dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Generate a concrete, actionable topic suggestion
        if fmt == "isekai":
            topic = f"Top 5 Best Isekai Anime to Watch"
        elif fmt == "overpowered":
            topic = f"Top 5 Most Overpowered Anime Protagonists"
        elif fmt == "recommendation":
            topic = f"Top 5 Anime You Need to Watch in 2025"
        elif fmt in ("ranking", "analysis"):
            topic = f"Top 5 Strongest {franchise} Characters"
        elif fmt == "vs":
            topic = f"Greatest Fights in {franchise} Ranked"
        elif fmt == "lore":
            topic = f"Top 5 Most Powerful Moments in {franchise}"
        else:
            topic = f"Top 5 Strongest Characters in {franchise}"

        suggestions.append({
            "franchise": franchise,
            "suggested_topic": topic,
            "reference_video": v["title"],
            "reference_views_per_day": v["views_per_day"],
            "reference_url": v["url"],
            "already_on_channel": franchise in channel_topics and franchise != "Unknown",
            "format": fmt,
        })

    # Uncovered franchises first, then already-covered ones
    uncovered = [s for s in suggestions if not s["already_on_channel"]]
    covered = [s for s in suggestions if s["already_on_channel"]]
    return (uncovered + covered)[:top_n]


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_trending_table(videos: list[dict], channel_topics: set[str], top_n: int = 10):
    """Print the Top N trending table with anime + format columns."""
    W = 110
    print(f"\n{'='*W}")
    print(f"  Top {top_n} Trending Videos  (by views/day — fastest growing)")
    print(f"{'='*W}")
    hdr = f"  {'views/day':>12}  {'total views':>13}  {'dur':>7}  {'date':>10}  {'anime':<20}  {'format':<10}  {'on ch':>5}  title"
    print(hdr)
    print(f"  {'-'*12}  {'-'*13}  {'-'*7}  {'-'*10}  {'-'*20}  {'-'*10}  {'-'*5}  {'-'*44}")

    by_velocity = sorted(videos, key=lambda v: v.get("views_per_day", 0), reverse=True)
    for v in by_velocity[:top_n]:
        vpd = f"{v.get('views_per_day', 0):,}/day"
        total = f"{v['views']:,}"
        dur = v.get("duration_seconds", 0)
        dur_str = f"{dur//60}m{dur%60:02d}s" if dur else "?"
        anime = v.get("detected_anime", "Unknown")[:20]
        fmt = v.get("detected_format", "other")[:10]
        on_ch = "yes" if v.get("detected_anime", "") in channel_topics else ""
        title = v["title"][:44]
        print(f"  {vpd:>12}  {total:>13}  {dur_str:>7}  {v['publish_date']}  {anime:<20}  {fmt:<10}  {on_ch:>5}  {title}")
    print()


def print_suggestions(suggestions: list[dict]):
    """Print the Suggested Topics section."""
    W = 110
    print(f"{'='*W}")
    print("  Suggested Topics for Next Video")
    print(f"{'='*W}")
    if not suggestions:
        print("  No suggestions (no trending videos with known franchises).")
        return

    for i, s in enumerate(suggestions, 1):
        tag = " [already on channel]" if s["already_on_channel"] else " [NEW]"
        vpd = f"{s['reference_views_per_day']:,} views/day"
        print(f"\n  {i}. {s['suggested_topic']}{tag}")
        print(f"     Trending: {s['reference_video'][:65]}")
        print(f"     Velocity: {vpd}  →  {s['reference_url']}")
    print()


# ---------------------------------------------------------------------------
# Argument parsing + main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Search YouTube for trending anime narrated videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/analyze_trends.py --days 30 --channel-cache output/channel_analytics.json\n"
            "  python scripts/analyze_trends.py --boost-anime 'Solo Leveling' 'Dandadan'\n"
            "  python scripts/analyze_trends.py --queries 'top 5 strongest anime' 'demon slayer ranking'\n"
        ),
    )
    parser.add_argument(
        "--queries", nargs="+", default=None,
        help="Custom search queries — replaces the built-in query bank entirely",
    )
    parser.add_argument(
        "--boost-anime", nargs="+", default=None, metavar="ANIME",
        help="Append extra ranking queries for specific anime (e.g. 'Solo Leveling' 'Dandadan')",
    )
    parser.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    parser.add_argument("--max-results", type=int, default=10, help="Max results per query (default: 10)")
    parser.add_argument("--min-duration", type=int, default=60,
                        help="Minimum video duration in seconds (default: 60, excludes Shorts)")
    parser.add_argument("--max-duration", type=int, default=0,
                        help="Maximum video duration in seconds (default: 0 = no limit)")
    parser.add_argument("--exclude-keywords", nargs="*", default=None,
                        help="Additional title keywords to exclude (appended to defaults)")
    parser.add_argument("--no-default-exclusions", action="store_true",
                        help="Disable the default keyword exclusion list")
    parser.add_argument(
        "--channel-cache", default=None, metavar="PATH",
        help="Path to channel_analytics.json for topic dedup + suggestions (auto-loaded when provided)",
    )
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore existing output cache and fetch fresh data")
    parser.add_argument("--output-file", default="output/trends_cache.json",
                        help="Output JSON file (default: output/trends_cache.json)")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build query list
    if args.queries:
        queries = list(args.queries)
        print(f"Using {len(queries)} custom queries (built-in bank bypassed).")
    else:
        queries = list(QUERY_BANK)
        print(f"Using built-in query bank ({len(queries)} queries).")

    if args.boost_anime:
        boost = build_boost_queries(args.boost_anime)
        queries.extend(boost)
        print(f"  + {len(boost)} boost queries for: {', '.join(args.boost_anime)}")

    # Exclusion list
    if args.no_default_exclusions:
        exclude_keywords = list(args.exclude_keywords or [])
    else:
        exclude_keywords = list(DEFAULT_EXCLUDE_KEYWORDS)
        if args.exclude_keywords:
            exclude_keywords.extend(args.exclude_keywords)

    # Channel cache for dedup
    channel_data: dict = {}
    channel_topics: set[str] = set()
    if args.channel_cache:
        channel_data = load_channel_cache(args.channel_cache)
        channel_topics = build_channel_topic_set(channel_data)
        if channel_topics:
            names = ", ".join(sorted(channel_topics))
            print(f"  Franchises already on channel: {names}")

    # Load existing output cache (keep only videos within the requested window)
    cached_videos: dict[str, dict] = {}
    if output_path.exists() and not args.no_cache:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).date().isoformat()
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            kept = 0
            for v in existing.get("videos", []):
                if v.get("publish_date", "0000") >= cutoff:
                    # Back-fill detection fields for old cache entries
                    if "detected_anime" not in v:
                        v["detected_anime"] = detect_anime(v.get("title", ""))
                    if "detected_format" not in v:
                        v["detected_format"] = detect_format(v.get("title", ""))
                    cached_videos[v["video_id"]] = v
                    kept += 1
            print(f"  Loaded {kept} recent videos from cache (cutoff: {cutoff})")
        except Exception:
            pass

    print(f"\nAnalyzing trends for {len(queries)} queries over the last {args.days} days...")
    if args.min_duration:
        print(f"  Filter: min {args.min_duration}s (excluding Shorts)")
    kw_preview = ", ".join(exclude_keywords[:8]) + ("..." if len(exclude_keywords) > 8 else "")
    print(f"  Filter: excluding keywords — {kw_preview}")

    result = run_trend_analysis(
        queries=queries,
        days=args.days,
        config=config,
        exclude_keywords=exclude_keywords,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        max_results_per_query=args.max_results,
    )

    # Merge fresh results with cache; new entries win on conflict
    merged: dict[str, dict] = {**cached_videos}
    for v in result["videos"]:
        merged[v["video_id"]] = v
    result["videos"] = sorted(merged.values(), key=lambda v: v["views"], reverse=True)

    # Generate suggestions before saving
    suggestions = generate_suggestions(result["videos"], channel_topics)
    result["suggestions"] = suggestions

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nTrend analysis saved: {output_path}")
    print(f"Found {len(result['videos'])} relevant videos (including cache).")

    # Print trending table + suggestions
    if result["videos"]:
        print_trending_table(result["videos"], channel_topics)
        print_suggestions(suggestions)


if __name__ == "__main__":
    main()
