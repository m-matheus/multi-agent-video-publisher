"""
Community post generator — creates an English engagement post for YouTube Studio.

Generates post text + poll suggestion using Claude, saves to JSON,
and opens the YouTube Studio community tab in the browser.

Usage:
    python scripts/post_community.py \
        --script-path output/run-001/script/script.json \
        --video-id "dQw4w9WgXcQ" \
        --output-dir output/run-001 \
        --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q
"""
import argparse
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config


def extract_anime_names(script: dict) -> list[str]:
    """Extract featured anime names from rank_transition scenes, fallback to tags."""
    names = [
        scene["name"]
        for scene in script.get("scenes", [])
        if scene.get("scene_type") == "rank_transition" and scene.get("name")
    ]
    if not names:
        names = script.get("tags", [])[:5]
    return names


def build_prompt(script: dict, video_id: str) -> str:
    title = script.get("title", "Anime video")
    anime_names = extract_anime_names(script)
    anime_list = ", ".join(anime_names) if anime_names else "various anime series"
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    return f"""You are an anime YouTube content creator writing a community post in English.

Video just published:
Title: {title}
Anime featured: {anime_list}
URL: {video_url}

Generate a YouTube community post that:
1. Asks an engaging question about the anime or ranking in the video (in English)
2. Includes a poll with exactly 4 options (use the anime names from the video, or relevant choices)
3. Includes 2-3 relevant hashtags

Respond ONLY with raw JSON, no markdown, no explanation:
{{"post_text": "...", "poll_question": "...", "poll_options": ["...", "...", "...", "..."], "hashtags": ["...", "..."]}}"""


def generate_community_post(script: dict, video_id: str, config: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    prompt = build_prompt(script, video_id)
    model = config.get("anthropic_model_haiku", "claude-haiku-4-5-20251001")

    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip any markdown code fences (```json ... ``` or ``` ... ```)
    import re as _re
    raw = _re.sub(r"^```[a-zA-Z]*\s*", "", raw).rstrip("`").strip()

    try:
        post = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw response:\n{raw[:500]}")

    options = post.get("poll_options", [])
    if len(options) < 2:
        raise ValueError(f"Expected at least 2 poll options, got: {options}")
    # Pad to 4 if fewer, truncate if more
    while len(options) < 4:
        options.append(f"Other")
    post["poll_options"] = options[:4]
    return post


def main():
    parser = argparse.ArgumentParser(description="Generate YouTube community post")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--video-id", required=True, help="YouTube video ID (after upload)")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--channel-id", default=None,
                        help="YouTube channel ID (defaults to YOUTUBE_CHANNEL_ID in .env)")
    args = parser.parse_args()

    config = load_config()
    channel_id = args.channel_id or config.get("youtube_channel_id") or "UCyRJuLu9xr7mrRh-j52RQ9Q"

    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))

    print("Generating community post...")
    post = generate_community_post(script, args.video_id, config)
    post["video_url"] = f"https://www.youtube.com/watch?v={args.video_id}"

    output_path = Path(args.output_dir) / "community_post.json"
    output_path.write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print("COMMUNITY POST")
    print("=" * 60)
    print(f"\nPost text:\n{post['post_text']}")
    print(f"\nPoll: {post['poll_question']}")
    for i, opt in enumerate(post["poll_options"], 1):
        print(f"  {i}. {opt}")
    print(f"\nHashtags: {' '.join(post['hashtags'])}")
    print(f"\nVideo URL: {post['video_url']}")
    print("=" * 60)
    print(f"\nSaved to: {output_path}")
    print(f"\nYouTube Studio Community tab: https://studio.youtube.com/channel/{channel_id}/community")
    print("Copy the post_text above and paste it there manually.")


if __name__ == "__main__":
    main()
