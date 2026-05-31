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

# Baseline framing applied to every anime thumbnail — mirrors the visual language
# of top creators (Anime Balls Deep, Plot Armor, Anime Explained, etc.).
PREMIUM_BASELINE = """
Make this look like a premium anime YouTube thumbnail produced by a top creator
with millions of subscribers (e.g. Anime Balls Deep, Plot Armor, Anime Explained).

Use:
- Massive foreground character with sharp anime poster quality
- Vibrant purple, blue, and gold lighting
- Cosmic atmosphere with energy effects
- Cinematic depth and high contrast
- Professional typography, 2-3 bold title words fully visible and never cropped
- Extremely high contrast, readable at mobile size

The image should feel like an official anime movie poster fused with a viral
YouTube thumbnail. Do NOT include any character names, labels, or ranking
numbers on the image.
""".strip()


def _build_history_request(script: dict) -> str:
    title = script.get("title", "")
    scenes = script.get("scenes", [])
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


def _infer_theme(scenes: list, ranked_names: list) -> str:
    """Pick a theme line based on the script's scene shape."""
    distinct = {n for n in ranked_names if n}
    if len(distinct) >= 3:
        return "Power ranking, legendary characters, strongest beings"
    if len(distinct) == 2:
        return "Rivalry, clash, decisive confrontation"
    if len(distinct) == 1:
        return "Power, dominance, ultimate strength"
    return "Anime power, action, spectacle"


def build_context_block(script: dict) -> str:
    """Structured context — feeds GPT-4o the whole video shape, not just the title."""
    scenes = script.get("scenes", [])
    title = script.get("title", "")

    top_character = next(
        (s.get("name") for s in scenes
         if s.get("scene_type") == "rank_transition" and s.get("rank") == 1),
        None,
    )
    # Allow script to override which character is centered in the thumbnail
    top_character = script.get("thumbnail_character", top_character)
    ranked_names = [
        s.get("name") for s in scenes
        if s.get("scene_type") == "rank_transition" and s.get("name")
    ]
    series = script.get("series", "")
    theme = _infer_theme(scenes, ranked_names)

    sections = [
        ("Video Topic", title),
        ("Main Character", top_character or ""),
        ("Characters Featured", ", ".join(ranked_names)),
        ("Anime / Series", series),
        ("Theme", theme),
    ]
    # Drop sections with empty values so the block stays clean on sparser scripts
    return "\n\n".join(f"{label}:\n{value}" for label, value in sections if value)


def build_chatgpt_request(script: dict) -> str:
    if script.get("content_type") == "history":
        return _build_history_request(script)

    context = build_context_block(script)

    return "\n\n".join(filter(None, [
        "Create a viral YouTube thumbnail for an anime video.",
        context,
        PREMIUM_BASELINE,
        # Honor existing thumbnail_style override if present
        script.get("thumbnail_style", "") or "",
    ])).strip()


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
