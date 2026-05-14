"""
Automatic context-aware comment replies for YouTube channel videos.

Fetches unreplied comments, generates a contextual English reply via Claude,
and either prints them (dry-run, default) or posts them (--post).

Tracks replied comment IDs in a state file to avoid duplicate replies.

Usage:
    # Preview generated replies without posting
    python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q

    # Actually post the replies
    python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q --post

    # Limit to a specific video
    python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q --video-id dQw4w9WgXcQ --post

    # Process more comments per run (default: 20)
    python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q --max-comments 50 --post
"""
import argparse
import json
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows to handle emojis in comment text
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, PROJECT_ROOT
from scripts.utils.youtube_auth import get_youtube_client

DEFAULT_STATE_FILE = PROJECT_ROOT / "output" / "replied_comments.json"
CHANNEL_PERSONA = "Hakase Anime"


def parse_args():
    parser = argparse.ArgumentParser(description="Auto-reply to YouTube comments with Claude")
    parser.add_argument("--channel-id", default=None,
                        help="YouTube channel ID (defaults to YOUTUBE_CHANNEL_ID in .env)")
    parser.add_argument("--video-id", default=None,
                        help="Limit to a single video ID instead of scanning recent videos")
    parser.add_argument("--max-comments", type=int, default=20,
                        help="Max number of comments to process per run (default: 20)")
    parser.add_argument("--recent-videos", type=int, default=10,
                        help="Number of recent videos to scan when --video-id is not set (default: 10)")
    parser.add_argument("--post", action="store_true",
                        help="Actually post replies. Without this flag, runs in dry-run mode.")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE),
                        help="JSON file tracking replied comment IDs")
    return parser.parse_args()


# ── State tracking ─────────────────────────────────────────────────────────────

def load_state(state_file: str) -> set:
    path = Path(state_file)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("replied_comment_ids", []))
    return set()


def save_state(state_file: str, replied_ids: set):
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"replied_comment_ids": sorted(replied_ids)}, indent=2),
        encoding="utf-8",
    )


# ── YouTube API helpers ────────────────────────────────────────────────────────

def fetch_recent_video_ids(youtube, channel_id: str, max_results: int) -> list[tuple[str, str]]:
    """Returns list of (video_id, title) for recent uploads."""
    response = youtube.search().list(
        channelId=channel_id,
        type="video",
        order="date",
        part="id,snippet",
        maxResults=max_results,
    ).execute()

    videos = []
    for item in response.get("items", []):
        vid = item["id"].get("videoId")
        title = item["snippet"]["title"]
        if vid:
            videos.append((vid, title))
    return videos


def fetch_video_title(youtube, video_id: str) -> str:
    response = youtube.videos().list(part="snippet", id=video_id).execute()
    items = response.get("items", [])
    return items[0]["snippet"]["title"] if items else video_id


def fetch_unreplied_comments(
    youtube,
    video_id: str,
    video_title: str,
    channel_id: str,
    replied_ids: set,
    limit: int,
) -> list[dict]:
    """
    Returns comment threads that have no reply from the channel owner yet.
    Each item: {thread_id, comment_id, author, text, video_id, video_title}
    """
    results = []
    page_token = None

    while len(results) < limit:
        kwargs = dict(
            videoId=video_id,
            part="snippet,replies",
            order="relevance",
            maxResults=min(100, limit * 3),  # over-fetch to account for already-replied
        )
        if page_token:
            kwargs["pageToken"] = page_token

        response = youtube.commentThreads().list(**kwargs).execute()

        for thread in response.get("items", []):
            thread_id = thread["id"]
            top = thread["snippet"]["topLevelComment"]
            comment_id = top["id"]

            if comment_id in replied_ids:
                continue

            # Check if channel owner already replied
            owner_replied = False
            for reply in thread.get("replies", {}).get("comments", []):
                author_channel = reply["snippet"].get("authorChannelId", {}).get("value", "")
                if author_channel == channel_id:
                    owner_replied = True
                    break

            if owner_replied:
                replied_ids.add(comment_id)  # mark so we skip next run too
                continue

            # Skip comments from the channel owner itself (engagement prompts, pinned questions)
            commenter_channel = top["snippet"].get("authorChannelId", {}).get("value", "")
            if commenter_channel == channel_id:
                continue

            # Skip very short or spam-like comments
            text = top["snippet"]["textOriginal"].strip()
            if len(text) < 3:
                continue

            results.append({
                "thread_id": thread_id,
                "comment_id": comment_id,
                "author": top["snippet"]["authorDisplayName"],
                "text": text,
                "video_id": video_id,
                "video_title": video_title,
            })

            if len(results) >= limit:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def post_reply(youtube, thread_id: str, reply_text: str):
    youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": thread_id,
                "textOriginal": reply_text,
            }
        },
    ).execute()


# ── Claude reply generation ────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""\
You are the creator of {CHANNEL_PERSONA}, an anime YouTube channel focused on power rankings, \
character analysis, and anime curiosities. You reply to viewer comments in a warm, genuine, \
and enthusiastic way.

Rules:
- Always reply in English, regardless of the comment language.
- Agree with and validate what the viewer said — be on their side, not questioning them.
- Directly address what the viewer said — never give a generic "thanks for watching" reply.
- Keep it 1–3 sentences. Be concise.
- Match the commenter's energy: excited → enthusiastic, emotional → empathetic, opinionated → affirming.
- Vary how you start (don't always say "Hey" or "Hi").
- Do NOT end with a question every time — most replies should just be a warm, affirming statement.
- Only ask a follow-up question occasionally, and only when it feels very natural (not forced).
- Sound human. No hashtags. No emojis unless the commenter used them.
- If the comment is spam or incomprehensible, reply with the single word: SKIP\
"""


def generate_reply(comment: dict, config: dict) -> str | None:
    import anthropic

    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])

    user_message = (
        f'Video: "{comment["video_title"]}"\n'
        f'Comment by {comment["author"]}: "{comment["text"]}"\n\n'
        f"Write your reply:"
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    reply = response.content[0].text.strip()
    if reply.upper() == "SKIP" or not reply:
        return None
    return reply


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    config = load_config()
    channel_id = args.channel_id or config.get("youtube_channel_id") or "UCyRJuLu9xr7mrRh-j52RQ9Q"

    print("Authenticating with YouTube...")
    youtube = get_youtube_client(config)

    replied_ids = load_state(args.state_file)
    print(f"State: {len(replied_ids)} comments already replied to.")

    # Gather (video_id, video_title) pairs to scan
    if args.video_id:
        video_title = fetch_video_title(youtube, args.video_id)
        videos = [(args.video_id, video_title)]
        print(f"Scanning 1 video: {video_title}")
    else:
        print(f"Fetching {args.recent_videos} most recent videos...")
        videos = fetch_recent_video_ids(youtube, channel_id, args.recent_videos)
        print(f"Found {len(videos)} videos.")

    # Collect unreplied comments across all videos
    all_comments: list[dict] = []
    remaining = args.max_comments

    for video_id, video_title in videos:
        if remaining <= 0:
            break
        comments = fetch_unreplied_comments(
            youtube, video_id, video_title, channel_id, replied_ids, limit=remaining
        )
        all_comments.extend(comments)
        remaining -= len(comments)
        if comments:
            print(f"  [{video_title[:50]}] -> {len(comments)} unreplied comment(s)")

    if not all_comments:
        print("\nNo unreplied comments found. All caught up!")
        save_state(args.state_file, replied_ids)
        return

    print(f"\nGenerating replies for {len(all_comments)} comment(s) via Claude...\n")

    dry_run = not args.post
    if dry_run:
        print("=" * 60)
        print("DRY-RUN MODE — replies will NOT be posted. Use --post to publish.")
        print("=" * 60)

    posted = 0
    skipped = 0

    for i, comment in enumerate(all_comments, 1):
        print(f"\n[{i}/{len(all_comments)}] Video: {comment['video_title'][:60]}")
        print(f"  @{comment['author']}: {comment['text'][:120]}")

        reply = generate_reply(comment, config)

        if reply is None:
            print("  -> SKIP (spam/unrecognized)")
            replied_ids.add(comment["comment_id"])
            skipped += 1
            continue

        print(f"  -> Reply: {reply}")

        if not dry_run:
            try:
                post_reply(youtube, comment["thread_id"], reply)
                replied_ids.add(comment["comment_id"])
                posted += 1
                # Respect YouTube API rate limits
                time.sleep(0.5)
            except Exception as e:
                print(f"  FAILED to post reply: {e}")

    # Persist state
    save_state(args.state_file, replied_ids)

    print("\n" + "=" * 60)
    if dry_run:
        print(f"DRY-RUN complete: {len(all_comments) - skipped} replies generated, {skipped} skipped.")
        print("Run with --post to publish these replies.")
    else:
        print(f"Done: {posted} replies posted, {skipped} skipped.")
    print(f"State saved to: {args.state_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
