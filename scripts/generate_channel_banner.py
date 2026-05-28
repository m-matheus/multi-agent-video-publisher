"""
YouTube channel banner generator using the OpenAI Responses API.

Generates a dark atmospheric background, then composites the channel title
text using PIL — centered in the YouTube safe zone.

YouTube canvas:    2560x1440
YouTube safe zone: 1546x423  (visible on all devices)
Text box (inner):  1235x338  (centered within safe zone, with margin)

Usage:
    python scripts/generate_channel_banner.py --channel hakase-anime
    python scripts/generate_channel_banner.py --channel hakase-anime --debug
    python scripts/generate_channel_banner.py --channel hakase-anime --text-only
"""
import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
BANNER_W, BANNER_H = 2560, 1440
SAFE_W,   SAFE_H   = 1546, 423
TEXT_W,   TEXT_H   = 1235, 338

SAFE_X = (BANNER_W - SAFE_W) // 2   # 507
SAFE_Y = (BANNER_H - SAFE_H) // 2   # 508
TEXT_X = (BANNER_W - TEXT_W) // 2   # 662
TEXT_Y = (BANNER_H - TEXT_H) // 2   # 551

# ---------------------------------------------------------------------------
# Font
# ---------------------------------------------------------------------------
FONTS_DIR = Path("assets/fonts")
FONT_URL  = "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf"
FONT_FILE = FONTS_DIR / "Anton-Regular.ttf"

FONT_FALLBACKS = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/ariblk.ttf",
]


def get_font(size: int):
    from PIL import ImageFont

    # Try downloading Anton (Google Fonts, OFL)
    if not FONT_FILE.exists():
        FONTS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            print(f"  Downloading Anton font from Google Fonts...")
            urllib.request.urlretrieve(FONT_URL, FONT_FILE)
            print(f"  Font cached: {FONT_FILE}")
        except Exception as e:
            print(f"  Font download failed ({e}), falling back to system font")

    if FONT_FILE.exists():
        return ImageFont.truetype(str(FONT_FILE), size)

    for path in FONT_FALLBACKS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text drawing helpers
# ---------------------------------------------------------------------------
def measure_spaced(font, text: str, spacing: int) -> tuple[int, int]:
    """Measure total width/height of text with manual letter spacing."""
    from PIL import Image, ImageDraw
    dummy = Image.new("RGB", (1, 1))
    draw  = ImageDraw.Draw(dummy)
    total_w = 0
    max_h   = 0
    for i, ch in enumerate(text):
        bb = draw.textbbox((0, 0), ch, font=font)
        w  = bb[2] - bb[0]
        h  = bb[3] - bb[1]
        total_w += w + (spacing if i < len(text) - 1 else 0)
        max_h    = max(max_h, h)
    return total_w, max_h


def draw_spaced(draw, x: int, y: int, text: str, font, fill, spacing: int):
    """Draw text with manual letter spacing."""
    from PIL import Image, ImageDraw
    dummy  = Image.new("RGB", (1, 1))
    d_dummy = ImageDraw.Draw(dummy)
    cx = x
    for ch in text:
        draw.text((cx, y), ch, font=font, fill=fill)
        bb = d_dummy.textbbox((0, 0), ch, font=font)
        cx += (bb[2] - bb[0]) + spacing
    return cx - spacing  # right edge


def draw_spaced_stroke(draw, x: int, y: int, text: str, font,
                       fill, stroke_fill=(0, 0, 0), stroke: int = 6, spacing: int = 0):
    """Draw text with stroke + manual letter spacing."""
    from PIL import Image, ImageDraw
    dummy   = Image.new("RGB", (1, 1))
    d_dummy = ImageDraw.Draw(dummy)
    cx = x
    for ch in text:
        bb = d_dummy.textbbox((0, 0), ch, font=font)
        cw = bb[2] - bb[0]
        for dx in range(-stroke, stroke + 1):
            for dy in range(-stroke, stroke + 1):
                if dx or dy:
                    draw.text((cx + dx, y + dy), ch, font=font, fill=stroke_fill)
        draw.text((cx, y), ch, font=font, fill=fill)
        cx += cw + spacing
    return cx - spacing


def add_glow(img, x: int, y: int, text: str, font, color, spacing: int,
             radius: int = 28, alpha: int = 160):
    """Paint a blurred glow layer behind text."""
    from PIL import Image, ImageDraw, ImageFilter
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    r, g, b = color
    draw_spaced(gd, x, y, text, font, fill=(r, g, b, alpha), spacing=spacing)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=radius))
    return Image.alpha_composite(img.convert("RGBA"), glow)


# ---------------------------------------------------------------------------
# Main text composition
# ---------------------------------------------------------------------------
def compose_text(img):
    from PIL import Image, ImageDraw

    LETTER_SPC  = 14     # px between characters
    LINE_GAP    = 10     # px between the two words
    STROKE      = 8
    CRIMSON     = (204, 0, 0)
    WHITE       = (255, 255, 255)
    BLACK       = (0,   0,   0)

    # Find the largest font size where both words fit the text box width
    size = 220
    while size > 40:
        font   = get_font(size)
        w_h, h_h = measure_spaced(font, "HAKASE", LETTER_SPC)
        w_a, h_a = measure_spaced(font, "ANIME",  LETTER_SPC)
        total_h  = h_h + LINE_GAP + h_a
        if w_h <= TEXT_W and w_a <= TEXT_W and total_h <= TEXT_H:
            break
        size -= 4

    font    = get_font(size)
    w_h, h_h = measure_spaced(font, "HAKASE", LETTER_SPC)
    w_a, h_a = measure_spaced(font, "ANIME",  LETTER_SPC)
    total_h  = h_h + LINE_GAP + h_a

    start_y = TEXT_Y + (TEXT_H - total_h) // 2
    x_h     = TEXT_X + (TEXT_W - w_h) // 2
    x_a     = TEXT_X + (TEXT_W - w_a) // 2
    y_a     = start_y + h_h + LINE_GAP

    # Glow behind HAKASE (white glow) and ANIME (crimson glow)
    img = add_glow(img, x_h, start_y, "HAKASE", font, WHITE,   LETTER_SPC, radius=32, alpha=120)
    img = add_glow(img, x_a, y_a,     "ANIME",  font, CRIMSON, LETTER_SPC, radius=40, alpha=180)
    img = img.convert("RGB")

    draw = ImageDraw.Draw(img)

    # Thin separator line between the two words
    sep_y  = start_y + h_h + LINE_GAP // 2
    sep_x1 = TEXT_X + (TEXT_W - w_h) // 2
    sep_x2 = TEXT_X + (TEXT_W + w_h) // 2
    draw.line([(sep_x1, sep_y), (sep_x2, sep_y)], fill=(180, 0, 0), width=2)

    # Text with stroke
    draw_spaced_stroke(draw, x_h, start_y, "HAKASE", font,
                       fill=WHITE,   stroke_fill=BLACK, stroke=STROKE, spacing=LETTER_SPC)
    draw_spaced_stroke(draw, x_a, y_a,     "ANIME",  font,
                       fill=CRIMSON, stroke_fill=BLACK, stroke=STROKE, spacing=LETTER_SPC)

    print(f"  Font: Anton {size}px, letter-spacing {LETTER_SPC}px")
    print(f"  Text box origin ({TEXT_X}, {TEXT_Y}), size {TEXT_W}×{TEXT_H}")
    return img


# ---------------------------------------------------------------------------
# Background prompt
# ---------------------------------------------------------------------------
CHANNEL_REQUESTS = {
    "hakase-anime": """Create a YouTube channel art background image. NO characters, NO text, NO logos.

Background only:
- Deep black (#0d0d0d) canvas, full bleed
- One large bold crimson red (#CC0000) brushstroke circle (Japanese rising sun motif), centered
- Grunge ink splatter textures, red paint/blood brushstrokes radiating outward
- Subtle red-to-black vignette darkening toward all four edges
- Dark atmospheric Japanese aesthetic, high contrast

The center must remain relatively uncluttered — text will be added on top later.
No text, no characters, no watermarks, no UI elements.""",
}


def build_request(channel_slug: str) -> str:
    channel_json = Path("channels") / channel_slug / "channel.json"
    channel = json.loads(channel_json.read_text(encoding="utf-8")) if channel_json.exists() else {}

    brand   = channel.get("brand", {})
    palette = brand.get("palette", "")
    style   = brand.get("style", "")

    base = CHANNEL_REQUESTS.get(channel_slug, "")
    if not base:
        dalle_banner = channel.get("dalle_prompts", {}).get("banner", "")
        name         = channel.get("name", channel_slug)
        if not dalle_banner:
            raise ValueError(f"No banner prompt for '{channel_slug}'")
        base = f'Create a YouTube channel art background for "{name}". {dalle_banner} No text, no characters, no watermarks.'

    parts = []
    if palette:
        parts.append(f"Color palette: {palette}.")
    if style:
        parts.append(f"Visual style: {style}.")
    return f"{base}\n\n" + "\n".join(parts)


# ---------------------------------------------------------------------------
# Generation + compositing
# ---------------------------------------------------------------------------
def generate_background(channel_slug: str, config: dict, assets_dir: Path) -> Path | None:
    request = build_request(channel_slug)
    print(f"\nPrompt preview:\n{request[:280]}...\n")

    api_key = config.get("openai_api_key")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set in .env")
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model="gpt-4o",
            input=request,
            tools=[{"type": "image_generation", "quality": "high", "size": "1536x1024"}],
        )
        image_data = next(
            (item.result for item in response.output if item.type == "image_generation_call"),
            None,
        )
        if not image_data:
            print("  ERROR: No image in response")
            return None
        raw_path = assets_dir / "banner_raw.png"
        raw_path.write_bytes(base64.b64decode(image_data))
        print(f"  Raw background saved: {raw_path}")
        return raw_path
    except Exception as e:
        print(f"  Responses API failed: {e}")
        return None


def save_debug_overlay(banner_path: Path, assets_dir: Path) -> None:
    from PIL import Image, ImageDraw
    img     = Image.open(banner_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov      = ImageDraw.Draw(overlay)

    sx1, sy1 = SAFE_X,        SAFE_Y
    sx2, sy2 = SAFE_X + SAFE_W, SAFE_Y + SAFE_H
    tx1, ty1 = TEXT_X,        TEXT_Y
    tx2, ty2 = TEXT_X + TEXT_W, TEXT_Y + TEXT_H

    ov.rectangle([0, 0, BANNER_W, sy1],         fill=(0, 0, 0, 130))
    ov.rectangle([0, sy2, BANNER_W, BANNER_H],  fill=(0, 0, 0, 130))
    ov.rectangle([0, sy1, sx1, sy2],            fill=(0, 0, 0, 130))
    ov.rectangle([sx2, sy1, BANNER_W, sy2],     fill=(0, 0, 0, 130))

    img  = Image.alpha_composite(img, overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([sx1, sy1, sx2, sy2], outline=(255, 80, 80), width=4)
    draw.rectangle([tx1, ty1, tx2, ty2], outline=(255, 220, 50), width=3)

    debug_path = assets_dir / "banner_debug.png"
    img.save(str(debug_path), "PNG")
    print(f"  Debug saved: {debug_path}  (red=safe zone, yellow=text box)")


def build_banner(raw_path: Path, assets_dir: Path, debug: bool) -> Path | None:
    from PIL import Image
    img = Image.open(raw_path).convert("RGB")

    scale = max(BANNER_W / img.width, BANNER_H / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    img = img.crop(((nw - BANNER_W) // 2, (nh - BANNER_H) // 2,
                    (nw - BANNER_W) // 2 + BANNER_W, (nh - BANNER_H) // 2 + BANNER_H))

    img = compose_text(img)

    banner_path = assets_dir / "banner.png"
    img.save(str(banner_path), "PNG", optimize=True)
    size_kb = banner_path.stat().st_size // 1024
    print(f"  Banner saved: {banner_path} ({size_kb} KB, {BANNER_W}x{BANNER_H})")

    if debug:
        save_debug_overlay(banner_path, assets_dir)

    return banner_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel",   default="hakase-anime")
    parser.add_argument("--debug",     action="store_true")
    parser.add_argument("--text-only", action="store_true",
                        help="Skip API call; re-composite text on existing banner_raw.png")
    args   = parser.parse_args()
    config = load_config()

    assets_dir = Path("channels") / args.channel / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating channel banner for '{args.channel}'...")

    if args.text_only:
        raw_path = assets_dir / "banner_raw.png"
        if not raw_path.exists():
            print(f"  ERROR: {raw_path} not found — run without --text-only first")
            sys.exit(1)
        print("  Reusing existing background (--text-only).")
    else:
        raw_path = generate_background(args.channel, config, assets_dir)
        if not raw_path:
            sys.exit(1)

    banner_path = build_banner(raw_path, assets_dir, debug=args.debug)
    if not banner_path:
        sys.exit(1)

    print(f"\nDone! Banner: {banner_path}")
    if args.debug:
        print("Check banner_debug.png — red=safe zone, yellow=text box")
    print("Upload: YouTube Studio → Customization → Branding → Banner image")


if __name__ == "__main__":
    main()
