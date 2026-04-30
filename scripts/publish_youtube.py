"""
YouTube video publishing via Data API v3.

Usage:
    python scripts/publish_youtube.py --script-path output/run-001/script/script.json --video-path output/run-001/final/final_video.mp4 --thumbnail-path output/run-001/thumbnail/thumbnail.png --privacy private
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, PROJECT_ROOT
from scripts.utils.state_manager import StateManager

CATEGORY_MAP = {
    "anime": "1",
    "bedtime-story": "24",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Publish video to YouTube")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--video-path", required=True, help="Path to final video")
    parser.add_argument("--thumbnail-path", required=True, help="Path to thumbnail image")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    parser.add_argument("--channel-id", default=None, help="YouTube channel ID to upload to (for multi-channel accounts)")
    parser.add_argument("--list-channels", action="store_true", help="List available channels and exit")
    return parser.parse_args()


def authenticate(config: dict):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds_path = PROJECT_ROOT / config["youtube_credentials_path"]
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]

    creds = None
    if creds_path.exists():
        creds = Credentials.from_authorized_user_file(str(creds_path), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_config = {
                "installed": {
                    "client_id": config["youtube_client_id"],
                    "client_secret": config["youtube_client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, scopes)
            creds = flow.run_local_server(port=0)
        creds_path.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def list_channels(youtube) -> list[dict]:
    """List all YouTube channels accessible by the authenticated account."""
    response = youtube.channels().list(
        part="snippet,contentDetails",
        mine=True,
    ).execute()

    channels = []
    for item in response.get("items", []):
        channels.append({
            "id": item["id"],
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", "")[:80],
            "custom_url": item["snippet"].get("customUrl", ""),
        })
    return channels


def select_channel(youtube, channel_id: str = None) -> str:
    """
    Select which channel to upload to.
    If channel_id is provided, validates it exists.
    If not, uses YOUTUBE_CHANNEL_ID from .env, or defaults to primary channel.
    """
    channels = list_channels(youtube)

    if not channels:
        print("ERROR: No YouTube channels found for this account")
        sys.exit(1)

    if channel_id:
        valid_ids = [c["id"] for c in channels]
        if channel_id not in valid_ids:
            print(f"ERROR: Channel ID '{channel_id}' not found. Available channels:")
            for c in channels:
                print(f"  {c['id']} - {c['title']} ({c['custom_url']})")
            sys.exit(1)
        return channel_id

    if len(channels) == 1:
        print(f"  Channel: {channels[0]['title']} ({channels[0]['custom_url']})")
        return channels[0]["id"]

    # Multiple channels — use env config or first one
    config = load_config()
    env_channel = config.get("youtube_channel_id")
    if env_channel:
        return select_channel(youtube, env_channel)

    print(f"  Using default channel: {channels[0]['title']} ({channels[0]['custom_url']})")
    return channels[0]["id"]


def upload_video(youtube, video_path: Path, metadata: dict) -> str:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(video_path), chunksize=256 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=metadata, media_body=media)

    response = None
    max_retries = 10
    retry = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  Upload progress: {int(status.progress() * 100)}%")
        except Exception as e:
            retry += 1
            if retry > max_retries:
                raise
            wait_time = min(2 ** retry, 60)
            print(f"  Upload error, retrying in {wait_time}s: {e}")
            time.sleep(wait_time)

    return response["id"]


def set_thumbnail(youtube, video_id: str, thumbnail_path: Path) -> bool:
    from googleapiclient.http import MediaFileUpload

    ext = thumbnail_path.suffix.lower()
    mimetype = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    try:
        media = MediaFileUpload(str(thumbnail_path), mimetype=mimetype)
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
        return True
    except Exception as e:
        print(f"  WARNING: Failed to set thumbnail: {e}")
        return False


def main():
    args = parse_args()
    config = load_config()

    # Authenticate first (needed for both listing and uploading)
    youtube = authenticate(config)

    # List channels mode
    if args.list_channels:
        channels = list_channels(youtube)
        print(f"\nAvailable YouTube channels ({len(channels)}):\n")
        for c in channels:
            print(f"  ID:    {c['id']}")
            print(f"  Name:  {c['title']}")
            print(f"  URL:   {c['custom_url']}")
            print(f"  ---")
        print(f"\nTo set a default channel, add to .env:")
        print(f"  YOUTUBE_CHANNEL_ID=<channel_id>")
        return

    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    video_path = Path(args.video_path)
    thumbnail_path = Path(args.thumbnail_path)

    if not video_path.exists():
        print(f"ERROR: Video file not found: {video_path}")
        sys.exit(1)

    state = StateManager()
    state.update_step("step-07-youtube-publishing", "running")

    # Select channel
    channel_id = args.channel_id or config.get("youtube_channel_id")
    selected_channel = select_channel(youtube, channel_id)

    content_type = script.get("content_type", "anime")
    metadata = {
        "snippet": {
            "title": script["title"][:100],
            "description": script.get("description", ""),
            "tags": script.get("tags", []),
            "categoryId": CATEGORY_MAP.get(content_type, "22"),
            "channelId": selected_channel,
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": content_type == "bedtime-story",
        },
    }

    print(f"Publishing to YouTube: {script['title']}")
    print(f"  Channel: {selected_channel}")
    print(f"  Privacy: {args.privacy}")
    print(f"  Category: {CATEGORY_MAP.get(content_type, '22')}")

    try:
        video_id = upload_video(youtube, video_path, metadata)
        print(f"  Video uploaded! ID: {video_id}")

        if thumbnail_path.exists():
            set_thumbnail(youtube, video_id, thumbnail_path)
            print("  Thumbnail set successfully")

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        studio_url = f"https://studio.youtube.com/video/{video_id}/edit"

        result = {
            "video_id": video_id,
            "url": video_url,
            "studio_url": studio_url,
            "privacy": args.privacy,
            "channel_id": selected_channel,
            "title": script["title"],
        }

        output_dir = Path(args.video_path).parent.parent
        result_path = output_dir / "publish_result.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print(f"\n  Video URL: {video_url}")
        print(f"  Studio: {studio_url}")

        state.update_step("step-07-youtube-publishing", "completed", result)

    except Exception as e:
        print(f"ERROR: Publishing failed: {e}")
        state.update_step("step-07-youtube-publishing", "failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
