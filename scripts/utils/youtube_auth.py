"""
Shared YouTube OAuth authentication module.

Provides authenticated clients for both YouTube Data API v3 and YouTube Analytics API v2.
All scripts that need YouTube API access should import from here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.utils.config import load_config, PROJECT_ROOT

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _get_credentials(config: dict = None):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    if config is None:
        config = load_config()

    creds_path = PROJECT_ROOT / config["youtube_credentials_path"]
    creds = None

    if creds_path.exists():
        # Load WITHOUT passing scopes so creds.scopes reflects only what's stored in the file
        try:
            creds = Credentials.from_authorized_user_file(str(creds_path))
        except Exception:
            creds = None

        # Force re-auth if stored token doesn't cover all required scopes
        if creds and not set(SCOPES).issubset(set(creds.scopes or [])):
            print("INFO: YouTube credentials missing new scopes — re-authentication required.")
            creds = None

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
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
        creds_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_youtube_client(config: dict = None):
    """Returns an authenticated YouTube Data API v3 client."""
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_get_credentials(config))


def get_youtube_analytics_client(config: dict = None):
    """Returns an authenticated YouTube Analytics API v2 client."""
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=_get_credentials(config))
