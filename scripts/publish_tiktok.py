"""
TikTok video publishing via Content Posting API v2.

Usage:
    python scripts/publish_tiktok.py \
        --script-path output/20260618-top5/script/script.json \
        --video-path output/20260618-top5/short_curiosity_naruto/final/final_short.mp4 \
        --privacy PUBLIC_TO_EVERYONE

    python scripts/publish_tiktok.py --check-auth

Authentication:
    1. Create a TikTok Developer App at https://developers.tiktok.com/
    2. Add to .env:
         TIKTOK_CLIENT_KEY=your_client_key
         TIKTOK_CLIENT_SECRET=your_client_secret
    3. Run once with --check-auth to complete OAuth flow and save credentials

Redirect URI (register this in TikTok Developer Portal):
    https://m-matheus.github.io/multi-agent-video-publisher/callback.html
"""
import argparse
import hashlib
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, PROJECT_ROOT
from scripts.utils.state_manager import StateManager

TIKTOK_CREDENTIALS_PATH = PROJECT_ROOT / ".tiktok_credentials.json"
OAUTH_REDIRECT_URI = "https://m-matheus.github.io/multi-agent-video-publisher/callback.html"
OAUTH_SCOPE = "video.publish,user.info.basic"

PRIVACY_LEVELS = {
    "public": "PUBLIC_TO_EVERYONE",
    "friends": "MUTUAL_FOLLOW_FRIENDS",
    "private": "SELF_ONLY",
    "PUBLIC_TO_EVERYONE": "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS": "MUTUAL_FOLLOW_FRIENDS",
    "SELF_ONLY": "SELF_ONLY",
}

# TikTok Content Posting API v2 endpoints
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
VIDEO_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# Upload size limits
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB chunks


def parse_args():
    parser = argparse.ArgumentParser(description="Publish video to TikTok")
    parser.add_argument("--script-path", help="Path to script.json")
    parser.add_argument("--video-path", help="Path to final video (1080x1920 Short)")
    parser.add_argument("--privacy", default="SELF_ONLY",
                        help="Privacy: public / friends / private (default: private/SELF_ONLY)")
    parser.add_argument("--check-auth", action="store_true", help="Check auth status and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without uploading")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def _run_oauth_flow(config: dict) -> dict:
    """Open browser for TikTok OAuth. User copies the code from the callback page."""
    state = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
    params = {
        "client_key": config["tiktok_client_key"],
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "state": state,
    }
    auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)

    print(f"\nOpening browser for TikTok authentication...")
    print(f"If the browser doesn't open, visit this URL manually:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("After authorizing, the browser will show a page with an authorization code.")
    code = input("Paste the authorization code here and press Enter: ").strip()

    if not code:
        raise RuntimeError("No authorization code provided.")

    return _exchange_code_for_token(config, code)


def _exchange_code_for_token(config: dict, code: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_key": config["tiktok_client_key"],
        "client_secret": config["tiktok_client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": OAUTH_REDIRECT_URI,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Token exchange failed: {data}")
    return data


def _refresh_token(config: dict, creds: dict) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_key": config["tiktok_client_key"],
        "client_secret": config["tiktok_client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": creds["refresh_token"],
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Token refresh failed: {data}")
    return data


def get_credentials(config: dict) -> dict:
    """Load or refresh TikTok credentials. Triggers full OAuth flow if none exist."""
    creds = None

    if TIKTOK_CREDENTIALS_PATH.exists():
        try:
            creds = json.loads(TIKTOK_CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except Exception:
            creds = None

    if creds:
        expires_at = creds.get("expires_at", 0)
        # Refresh if within 5 minutes of expiry
        if time.time() > expires_at - 300:
            print("TikTok token expiring — refreshing...")
            try:
                refreshed = _refresh_token(config, creds)
                creds.update(refreshed)
                creds["expires_at"] = time.time() + creds.get("expires_in", 86400)
                TIKTOK_CREDENTIALS_PATH.write_text(
                    json.dumps(creds, indent=2), encoding="utf-8"
                )
                print("Token refreshed.")
            except Exception as e:
                print(f"Refresh failed ({e}) — re-authenticating...")
                creds = None

    if not creds:
        creds = _run_oauth_flow(config)
        creds["expires_at"] = time.time() + creds.get("expires_in", 86400)
        TIKTOK_CREDENTIALS_PATH.write_text(
            json.dumps(creds, indent=2), encoding="utf-8"
        )
        print("TikTok credentials saved.")

    return creds


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def get_user_info(access_token: str) -> dict:
    resp = requests.get(
        USER_INFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "open_id,display_name,avatar_url"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", {}).get("user", {})


def _init_direct_post(access_token: str, payload: dict) -> dict:
    resp = requests.post(
        VIDEO_INIT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok init failed: {data['error']}")
    return data["data"]


def _upload_chunk(upload_url: str, video_path: Path, start: int, end: int, total: int):
    chunk_size = end - start
    with open(video_path, "rb") as f:
        f.seek(start)
        chunk = f.read(chunk_size)

    resp = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes {start}-{end - 1}/{total}",
            "Content-Length": str(chunk_size),
        },
        data=chunk,
        timeout=120,
    )
    if resp.status_code not in (200, 201, 206):
        raise RuntimeError(f"Chunk upload failed [{resp.status_code}]: {resp.text[:200]}")


def upload_video(access_token: str, video_path: Path, metadata: dict) -> str:
    """Initialize upload, send chunks, return publish_id."""
    file_size = video_path.stat().st_size
    chunk_count = max(1, (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE)

    payload = {
        "post_info": metadata,
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": CHUNK_SIZE,
            "total_chunk_count": chunk_count,
        },
    }

    print(f"  Initializing upload ({file_size / 1024 / 1024:.1f} MB, {chunk_count} chunk(s))...")
    init_data = _init_direct_post(access_token, payload)
    upload_url = init_data["upload_url"]
    publish_id = init_data["publish_id"]

    for i in range(chunk_count):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, file_size)
        print(f"  Uploading chunk {i + 1}/{chunk_count} ({start // 1024 // 1024}–{end // 1024 // 1024} MB)...")
        _upload_chunk(upload_url, video_path, start, end, file_size)

    print(f"  Upload complete. publish_id: {publish_id}")
    return publish_id


def wait_for_processing(access_token: str, publish_id: str, timeout: int = 300) -> dict:
    """Poll status until PUBLISH_COMPLETE or FAILED."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.post(
            VIDEO_STATUS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        status_data = data.get("data", {})
        status = status_data.get("status", "UNKNOWN")
        print(f"  Status: {status}")
        if status == "PUBLISH_COMPLETE":
            return status_data
        if status in ("FAILED", "SPAM_RISK_TOO_MANY_POSTS", "SPAM_RISK_USER_BANNED_FROM_POSTING"):
            raise RuntimeError(f"TikTok publish failed: {status} — {status_data}")
        time.sleep(5)
    raise RuntimeError(f"TikTok processing timed out after {timeout}s")


# ---------------------------------------------------------------------------
# Description builder
# ---------------------------------------------------------------------------

def build_description(script: dict) -> str:
    """Build TikTok description from script. Max 2200 chars (TikTok limit)."""
    tags = script.get("tags", [])
    # TikTok hashtags: prefix each tag with #, max ~30 tags
    hashtags = " ".join(f"#{t.replace(' ', '').replace('-', '')}" for t in tags[:30])
    # Short description — TikTok description is the caption, keep it punchy
    title = script.get("title", "").split("#")[0].strip()
    desc = f"{title}\n\n{hashtags}"
    return desc[:2200]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    config = load_config()

    if not config.get("tiktok_client_key"):
        print("ERROR: TIKTOK_CLIENT_KEY not set in .env")
        print("  1. Create an app at https://developers.tiktok.com/")
        print("  2. Add TIKTOK_CLIENT_KEY=... and TIKTOK_CLIENT_SECRET=... to .env")
        sys.exit(1)

    # Auth check mode
    if args.check_auth:
        creds = get_credentials(config)
        user = get_user_info(creds["access_token"])
        print(f"\nTikTok auth OK")
        print(f"  Account: {user.get('display_name', '(unknown)')}")
        print(f"  Open ID:  {user.get('open_id', '(unknown)')}")
        print(f"  Credentials saved at: {TIKTOK_CREDENTIALS_PATH}")
        return

    if not args.script_path or not args.video_path:
        print("ERROR: --script-path and --video-path are required for publishing")
        sys.exit(1)

    script_path = Path(args.script_path)
    video_path = Path(args.video_path)

    if not script_path.exists():
        print(f"ERROR: Script not found: {script_path}")
        sys.exit(1)
    if not video_path.exists():
        print(f"ERROR: Video not found: {video_path}")
        sys.exit(1)

    script = json.loads(script_path.read_text(encoding="utf-8"))

    privacy = PRIVACY_LEVELS.get(args.privacy.lower(), args.privacy)

    description = build_description(script)
    metadata = {
        "title": script["title"][:150],
        "privacy_level": privacy,
        "disable_duet": False,
        "disable_comment": False,
        "disable_stitch": False,
        "video_cover_timestamp_ms": 1000,
    }

    print(f"Publishing to TikTok: {script['title']}")
    print(f"  Privacy: {privacy}")
    print(f"  Description ({len(description)} chars):\n    {description[:120]}...")

    if args.dry_run:
        print("\n[DRY RUN] payload:")
        print(json.dumps({"post_info": metadata, "description": description}, indent=2, ensure_ascii=False))
        return

    creds = get_credentials(config)
    access_token = creds["access_token"]

    state = StateManager()
    state.update_step("step-tiktok-publishing", "running")

    try:
        publish_id = upload_video(access_token, video_path, metadata)
        print("  Waiting for TikTok to process video...")
        status_data = wait_for_processing(access_token, publish_id)

        result = {
            "publish_id": publish_id,
            "privacy": privacy,
            "title": script["title"],
            "status": status_data.get("status"),
        }

        output_dir = video_path.parent.parent
        result_path = output_dir / "tiktok_publish_result.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print(f"\n  TikTok publish complete!")
        print(f"  publish_id: {publish_id}")
        print(f"  Check your TikTok profile to confirm the video is live.")

        state.update_step("step-tiktok-publishing", "completed", result)

    except Exception as e:
        print(f"ERROR: TikTok publishing failed: {e}")
        state.update_step("step-tiktok-publishing", "failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
