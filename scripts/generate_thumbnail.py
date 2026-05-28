"""
YouTube thumbnail generator using the OpenAI Responses API.

Replicates ChatGPT's internal pipeline: GPT-4o receives a natural language
request, wraps it into a detailed image prompt internally, and calls gpt-image-1.
This is the exact same flow as typing into ChatGPT — not a manual prompt.

Usage:
    python scripts/generate_thumbnail.py \
        --script-path output/run-001/script/script.json \
        --output-dir output/run-001
"""
import argparse
import base64
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager


def parse_args():
    parser = argparse.ArgumentParser(description="Generate YouTube thumbnail via Responses API")
    parser.add_argument("--script-path", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Build the natural language request (as if typing into ChatGPT)
# ---------------------------------------------------------------------------

def build_chatgpt_request(script: dict) -> str:
    title = script.get("title", "")
    content_type = script.get("content_type", "anime")
    scenes = script.get("scenes", [])

    if content_type == "history":
        intro_visual = next(
            (s.get("visual_prompt", "") for s in scenes if s.get("scene_type") == "intro"),
            scenes[0].get("visual_prompt", "") if scenes else "",
        )
        atmosphere_line = f"Scene reference: {intro_visual[:200]}." if intro_visual else ""
        channel_style = script.get("thumbnail_style", "")

        return "\n".join(filter(None, [
            f'Create a viral YouTube thumbnail for a history documentary titled "{title}".',
            atmosphere_line,
            "Make it look like a professional history documentary thumbnail: "
            "dark atmospheric, dramatic chiaroscuro lighting, oil painting or cinematic photorealistic style, "
            "historically accurate setting. "
            "Include 2-3 bold words of text from the title, fully visible and never cropped. "
            "Do NOT include any labels, dates, or annotations on the image. "
            "High contrast, epic scale, cinematic composition.",
            channel_style if channel_style else "",
        ]))

    top_character = next(
        (s.get("name") for s in scenes
         if s.get("scene_type") == "rank_transition" and s.get("rank") == 1),
        None,
    )
    ranked_names = [
        s.get("name") for s in scenes
        if s.get("scene_type") == "rank_transition" and s.get("name")
    ]
    featured_visual = next(
        (s.get("visual_prompt", "") for s in scenes if s.get("scene_type") == "intro"),
        "",
    )

    character_line = (
        f"The main character should be {top_character} (rank #1), "
        f"with an intense and aggressive expression, filling most of the frame."
        if top_character else ""
    )
    ranked_line = (
        f"The video features these characters in order: {', '.join(ranked_names)}."
        if ranked_names else ""
    )
    atmosphere_line = f"Scene mood: {featured_visual}." if featured_visual else ""

    return "\n".join(filter(None, [
        f'Create a viral YouTube thumbnail for a video titled "{title}".',
        character_line,
        ranked_line,
        atmosphere_line,
        "Make it look like a professional anime YouTube thumbnail with bold text, "
        "dramatic lighting, anime-accurate art style, and high contrast. "
        "Use the visual identity and color palette of the featured anime. "
        "Include 2-3 bold words of text from the title, fully visible and never cropped. "
        "Do NOT include any character names, labels, or ranking numbers on the image.",
    ]))


# ---------------------------------------------------------------------------
# Generate via Responses API (ChatGPT's internal pipeline)
# ---------------------------------------------------------------------------

def generate_via_responses_api(request: str, out_path: Path, config: dict) -> Path | None:
    api_key = config.get("openai_api_key")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set in .env")
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        print(f"  Request ({len(request)} chars): {request[:120]}...")

        response = client.responses.create(
            model="gpt-4o",
            input=request,
            tools=[{
                "type": "image_generation",
                "quality": "high",
                "size": "1536x1024",
            }],
        )

        image_data = next(
            (item.result for item in response.output
             if item.type == "image_generation_call"),
            None,
        )
        if not image_data:
            print("  ERROR: No image in response")
            return None

        out_path.write_bytes(base64.b64decode(image_data))
        return out_path

    except Exception as e:
        print(f"  Responses API failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args      = parse_args()
    config    = load_config()
    script    = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    out_dir   = Path(args.output_dir)
    thumb_dir = ensure_dir(out_dir / "thumbnail")

    state = StateManager()
    state.update_step("step-06-thumbnail-creation", "running")

    request = build_chatgpt_request(script)
    print("Generating thumbnail via Responses API (ChatGPT pipeline)...")

    raw_path = thumb_dir / "dalle_raw.png"
    image_path = generate_via_responses_api(request, raw_path, config)
    if not image_path:
        state.update_step("step-06-thumbnail-creation", "failed")
        sys.exit(1)

    from PIL import Image
    thumbnail_path = thumb_dir / "thumbnail.jpg"
    Image.open(image_path).convert("RGB").resize((1280, 720), Image.LANCZOS).save(
        str(thumbnail_path), "JPEG", quality=93)

    size_kb = thumbnail_path.stat().st_size // 1024
    print(f"  Saved: {thumbnail_path} ({size_kb} KB)")
    state.update_step(
        "step-06-thumbnail-creation", "completed",
        {"thumbnail_path": str(thumbnail_path), "request": request},
    )


if __name__ == "__main__":
    main()
