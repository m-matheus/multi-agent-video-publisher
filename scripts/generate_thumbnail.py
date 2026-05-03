"""
YouTube thumbnail generator — DALL-E 3 creative brief.

Claude Haiku writes a rich creative prompt from the video script.
DALL-E 3 generates the full thumbnail (1792x1024 HD), including layout and text.
PIL adds only the channel brand badge on top.

Usage:
    python scripts/generate_thumbnail.py \
        --script-path output/run-001/script/script.json \
        --output-dir output/run-001 \
        [--channel-dir channels/hakase-anime] \
        [--no-badge]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, get_ffmpeg_path
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager


def parse_args():
    parser = argparse.ArgumentParser(description="Generate YouTube thumbnail via DALL-E 3")
    parser.add_argument("--script-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--channel-dir", default=None,
                        help="Channel directory (e.g. channels/hakase-anime)")
    parser.add_argument("--badge", action="store_true",
                        help="Add channel brand badge overlay (off by default)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Channel helpers
# ---------------------------------------------------------------------------

def _load_channel(channel_dir: str | None) -> dict:
    if channel_dir:
        p = Path(channel_dir) / "channel.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    base = Path(__file__).parent.parent / "channels"
    if base.exists():
        for sub in sorted(base.iterdir()):
            p = sub / "channel.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _channel_profile(channel_dir: str | None, channel: dict) -> Path | None:
    slug = channel.get("slug", "")
    candidates = []
    if channel_dir:
        candidates += [Path(channel_dir) / "assets" / "profile.png",
                       Path(channel_dir) / "profile.png"]
    if slug:
        base = Path(__file__).parent.parent / "channels" / slug
        candidates += [base / "assets" / "profile.png", base / "profile.png"]
    return next((p for p in candidates if p.exists()), None)


# ---------------------------------------------------------------------------
# Creative prompt generation
# ---------------------------------------------------------------------------

def build_dalle_prompt(script: dict, config: dict) -> str:
    """
    Use GPT-4o to write a rich image generation prompt for gpt-image-1.
    This mirrors how ChatGPT works internally: the chat model expands the
    user's intent into a detailed visual brief before calling the image model.
    """
    title = script.get("title", "")
    scenes = script.get("scenes", [])

    ranked_names = [
        f"#{s['rank']} {s['name']}"
        for s in scenes
        if s.get("scene_type") == "rank_transition" and s.get("name")
    ]
    featured_visual = next(
        (s.get("visual_prompt", "") for s in scenes if s.get("scene_type") == "intro"),
        title,
    )

    series_line = f"Ranked series: {', '.join(ranked_names)}." if ranked_names else ""
    user_brief = (
        f"Video title: \"{title}\". "
        f"{series_line} "
        f"Main visual focus: {featured_visual}. "
        "Generate a YouTube thumbnail with Jinwoo as the centerpiece."
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.get("openai_api_key"))
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert at writing image generation prompts for gpt-image-1. "
                        "Given a brief description of a YouTube anime thumbnail, write a single detailed, "
                        "vivid image generation prompt. Include: character appearance details, lighting, "
                        "atmosphere, color palette, composition, art style, and any text to render. "
                        "The result must look like official anime promotional art — not generic AI art. "
                        "All text in the image must be fully centered and within the frame — never cropped. "
                        "Output ONLY the prompt, no preamble."
                    ),
                },
                {"role": "user", "content": user_brief},
            ],
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  GPT-4o prompt expansion failed: {e} — using fallback")
        return user_brief


# ---------------------------------------------------------------------------
# Image generation (gpt-image-1)
# ---------------------------------------------------------------------------

def generate_image(prompt: str, out_path: Path, config: dict) -> Path | None:
    api_key = config.get("openai_api_key")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set in .env")
        return None
    try:
        import base64
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        print(f"  Prompt ({len(prompt)} chars): {prompt[:120]}...")
        # gpt-image-1: the model behind ChatGPT image generation — much better
        # at anime character styles and text rendering than dall-e-3.
        # Returns base64-encoded PNG (no URL), so we decode and save directly.
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt[:4000],
            size="1536x1024",
            quality="high",
            n=1,
        )
        img_bytes = base64.b64decode(response.data[0].b64_json)
        out_path.write_bytes(img_bytes)
        return out_path
    except Exception as e:
        print(f"  gpt-image-1 failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Channel brand badge overlay (PIL)
# ---------------------------------------------------------------------------

def add_channel_badge(image_path: Path, channel: dict,
                       profile_path: Path | None, output_path: Path):
    """
    Overlay a small brand badge (profile icon + channel name) in the top-right corner.
    This is the only PIL post-processing — everything else is DALL-E generated.
    """
    from PIL import Image, ImageDraw, ImageFont
    import platform

    img = Image.open(image_path).convert("RGB").resize((1280, 720), Image.LANCZOS)

    channel_name = channel.get("name", "HAKASE ANIME").upper()

    # Font
    font_path = None
    candidates = (
        ["C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/ariblk.ttf",
         "C:/Windows/Fonts/arialbd.ttf"]
        if platform.system() == "Windows"
        else ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    )
    for c in candidates:
        if Path(c).exists():
            font_path = c
            break

    badge_h = 52
    icon_size = badge_h - 8
    pad = 10

    try:
        font = ImageFont.truetype(font_path, 26) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    draw_tmp = ImageDraw.Draw(img)
    name_bb  = draw_tmp.textbbox((0, 0), channel_name, font=font)
    name_w   = name_bb[2] - name_bb[0]
    name_h   = name_bb[3] - name_bb[1]

    badge_w = pad + icon_size + pad + name_w + pad
    bx = 1280 - badge_w - 8
    by = 8

    # Background layer
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(
        [bx, by, bx + badge_w, by + badge_h],
        radius=8, fill=(0, 0, 0, 195)
    )
    od.rounded_rectangle(
        [bx, by, bx + badge_w, by + badge_h],
        radius=8, outline=(204, 0, 0, 220), width=2
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Profile icon
    icon_x = bx + pad
    icon_y = by + (badge_h - icon_size) // 2
    if profile_path and profile_path.exists():
        try:
            icon = Image.open(profile_path).convert("RGBA").resize(
                (icon_size, icon_size), Image.LANCZOS)
            mask = Image.new("L", (icon_size, icon_size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, icon_size, icon_size], fill=255)
            img.paste(icon, (icon_x, icon_y), mask=mask)
        except Exception:
            pass

    # Channel name
    tx = icon_x + icon_size + pad
    ty = by + (badge_h - name_h) // 2
    draw.text((tx, ty), channel_name, font=font, fill=(255, 255, 255))

    img.save(str(output_path), "JPEG", quality=93, optimize=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args    = parse_args()
    config  = load_config()
    script  = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    out_dir = Path(args.output_dir)
    thumb_dir = ensure_dir(out_dir / "thumbnail")

    channel      = _load_channel(args.channel_dir)
    profile_path = _channel_profile(args.channel_dir, channel)

    state = StateManager()
    state.update_step("step-06-thumbnail-creation", "running")

    # 1. Build creative prompt
    print("Writing thumbnail brief with Claude Haiku...")
    prompt = build_dalle_prompt(script, config)

    # 2. Generate with DALL-E 3
    print("Generating thumbnail with gpt-image-1 (1536x1024 HD)...")
    raw_path = thumb_dir / "dalle_raw.png"
    image_path = generate_image(prompt, raw_path, config)
    if not image_path:
        state.update_step("step-06-thumbnail-creation", "failed")
        sys.exit(1)

    # 3. Add channel badge (or just resize)
    thumbnail_path = thumb_dir / "thumbnail.jpg"
    if not args.badge or not channel:
        from PIL import Image
        Image.open(image_path).convert("RGB").resize((1280, 720), Image.LANCZOS).save(
            str(thumbnail_path), "JPEG", quality=93)
        print("  Badge skipped")
    else:
        print(f"  Adding channel badge: {channel.get('name', '?')}")
        try:
            add_channel_badge(image_path, channel, profile_path, thumbnail_path)
        except ImportError:
            print("ERROR: Pillow not installed — run: pip install Pillow")
            state.update_step("step-06-thumbnail-creation", "failed")
            sys.exit(1)

    size_kb = thumbnail_path.stat().st_size // 1024
    print(f"  Saved: {thumbnail_path} ({size_kb} KB)")
    state.update_step(
        "step-06-thumbnail-creation", "completed",
        {"thumbnail_path": str(thumbnail_path), "prompt": prompt},
    )


if __name__ == "__main__":
    main()
