"""Post-publish: update description with chapters + hashtags, expand tags, post engagement comment."""
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import google_auth_oauthlib.flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

VIDEO_ID = "4zxKYCF2ieI"
SCRIPT_PATH = "output/20260605-algorithm-buried-anime/script/script.json"

# Build description with chapters
with open(SCRIPT_PATH, encoding="utf-8") as f:
    script = json.load(f)

t = 0.0
chapters_lines = []
for i, scene in enumerate(script["scenes"]):
    stype = scene.get("scene_type")
    if stype == "intro":
        chapters_lines.append(f"0:00 Intro")
    elif stype == "rank_transition":
        rank = scene.get("rank")
        name = scene.get("name")
        m = int(t // 60)
        s_ = int(t % 60)
        chapters_lines.append(f"{m}:{s_:02d} #{rank} — {name}")
    t += scene.get("duration_seconds", 0)
m = int(t // 60); s_ = int(t % 60)
chapters_lines.append(f"{m}:{s_:02d} Outro")

description = (
    "These 5 anime are some of the best ever made — and almost nobody has seen them. "
    "From a psychological thriller that flips everything you think you know, to a jazz-era revenge "
    "story with no superpowers, just pure tension. The algorithm never pushed them. We will.\n\n"
    + "\n".join(chapters_lines)
    + "\n\n#anime #underratedanime #hiddengemanime #animerecommendations #oddtaxi #91days "
      "#vivyfluoriteeye #talentlessnana #rakugoshinju #animemasterpiece"
)

tags = [
    "underrated anime", "hidden gem anime", "anime recommendations", "best anime",
    "odd taxi", "91 days", "vivy fluorite eye's song", "talentless nana",
    "showa genroku rakugo shinju", "anime you missed", "anime masterpiece",
    "algorithm buried anime", "best anime 2026", "anime list", "psychological anime",
    "noir anime", "sci-fi anime", "WIT studio", "mystery anime", "anime to watch",
    "underrated anime 2026", "criminally underrated anime", "anime nobody talks about",
    "top 5 anime", "hakase anime"
]

# Authenticate using existing OAuth credentials
creds_path = ".youtube_credentials.json"
creds = Credentials.from_authorized_user_file(creds_path, [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube",
])
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
youtube = build("youtube", "v3", credentials=creds)

# Update description + tags
update_body = {
    "id": VIDEO_ID,
    "snippet": {
        "title": script["title"],
        "description": description,
        "tags": tags,
        "categoryId": "1",
    },
}
youtube.videos().update(part="snippet", body=update_body).execute()
print(f"Updated description ({len(description)} chars) and {len(tags)} tags")

# Post engagement comment
comment_text = "Which anime from this list is your favorite? Drop it in the comments! 👇 The algorithm doesn't push these shows — but you can."
comment_body = {
    "snippet": {
        "videoId": VIDEO_ID,
        "topLevelComment": {
            "snippet": {"textOriginal": comment_text}
        },
    }
}
resp = youtube.commentThreads().insert(part="snippet", body=comment_body).execute()
print(f"Posted comment: {resp['id']}")
print(f"\nIMPORTANT: Pin the comment manually in YouTube Studio.")
print(f"Studio: https://studio.youtube.com/video/{VIDEO_ID}/comments")
