"""
YouTube thumbnail generation using anime character images from Jikan API (MAL)
with Safebooru fallback, composed into a clickbait-style collage via PIL.

Layout (1280×720):
  Left half  (640×720): #1 hero character (largest)
  Right half (640×720): 2×2 grid of #2–#5 (320×360 each)
  Overlay:  "TOP N" at top, rank badges per panel, title subtitle at bottom

Usage:
    python scripts/generate_thumbnail.py --script-path output/run-001/script/script.json --output-dir output/run-001
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.file_helpers import ensure_dir, download_file
from scripts.utils.state_manager import StateManager

_WORD_TO_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def parse_args():
    parser = argparse.ArgumentParser(description="Generate YouTube thumbnail from anime images")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Character extraction
# ---------------------------------------------------------------------------

def extract_ranked_characters(scenes: list[dict]) -> list[tuple[int, str]]:
    """Return [(rank, name)] sorted ascending by rank (1 = most powerful = hero)."""
    entries = []
    seen_ranks = set()
    for scene in scenes:
        m = re.search(r"[Nn]umber (\w+)\s*[—\-,:]\s*([^,\n]+)", scene.get("narration_text", ""))
        if m:
            rank = _WORD_TO_NUM.get(m.group(1).lower(), 99)
            if rank in seen_ranks:
                continue
            words = m.group(2).strip().split()[:4]
            name = " ".join(words).rstrip(".,!")
            if name:
                entries.append((rank, name))
                seen_ranks.add(rank)
    entries.sort(key=lambda x: x[0])
    return entries


# ---------------------------------------------------------------------------
# Image fetching
# ---------------------------------------------------------------------------

def _name_to_tags(name: str) -> list[str]:
    """Generate Safebooru tag candidates for a character name."""
    base = name.lower().replace(".", "").strip()
    tags = [base.replace(" ", "_")]
    words = base.split()
    if len(words) > 1:
        tags.append(words[0])          # first name
        tags.append(words[-1])         # last name
        tags.append("_".join(reversed(words[:2])))  # reversed (jp name order)
    return tags


def _fetch_jikan(name: str, session) -> str | None:
    try:
        resp = session.get(
            "https://api.jikan.moe/v4/characters",
            params={"q": name, "order_by": "favorites", "sort": "desc", "limit": 5},
            timeout=15,
        )
        hits = resp.json().get("data", [])
        if hits:
            return hits[0]["images"]["jpg"]["image_url"]
    except Exception as e:
        print(f"    Jikan error for '{name}': {e}")
    return None


def _fetch_safebooru(name: str, session) -> str | None:
    for tag in _name_to_tags(name):
        try:
            resp = session.get(
                "https://safebooru.org/index.php",
                params={"page": "dapi", "s": "post", "q": "index",
                        "json": "1", "tags": f"{tag} rating:safe", "limit": 10},
                timeout=15,
            )
            posts = resp.json()
            if posts and isinstance(posts, list):
                best = max(posts, key=lambda p: int(p.get("score", 0)))
                url = best.get("file_url", "")
                if url.startswith("//"):
                    url = "https:" + url
                elif not url.startswith("http"):
                    url = f"https://safebooru.org/images/{best.get('directory','')}/{best.get('image','')}"
                if url:
                    return url
        except Exception as e:
            print(f"    Safebooru tag '{tag}' error: {e}")
        time.sleep(0.3)
    return None


def fetch_character_images(
    ranked: list[tuple[int, str]], char_dir: Path
) -> list[tuple[int, str, Path | None]]:
    """Download one image per character. Returns [(rank, name, local_path|None)]."""
    import requests
    session = requests.Session()
    session.headers["User-Agent"] = "multi-agent-video-publisher/1.0"
    results = []
    for rank, name in ranked:
        print(f"  [{rank}] {name}...", end=" ", flush=True)
        img_url = _fetch_jikan(name, session)
        source = "jikan"
        if not img_url:
            img_url = _fetch_safebooru(name, session)
            source = "safebooru"
        if img_url:
            print(f"✓ {source}")
            ext = Path(img_url.split("?")[0]).suffix or ".jpg"
            dest = char_dir / f"char_{rank:02d}{ext}"
            try:
                download_file(img_url, dest)
                results.append((rank, name, dest))
            except Exception as e:
                print(f"    download failed: {e}")
                results.append((rank, name, None))
        else:
            print("✗ not found")
            results.append((rank, name, None))
        time.sleep(0.4)  # Jikan rate limit
    return results


# ---------------------------------------------------------------------------
# PIL collage
# ---------------------------------------------------------------------------

def _find_font(bold: bool = True) -> str | None:
    import platform
    if platform.system() == "Windows":
        candidates = (
            ["C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/ariblk.ttf",
             "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]
            if bold else ["C:/Windows/Fonts/arial.ttf"]
        )
    else:
        candidates = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                      "/System/Library/Fonts/Helvetica.ttc"]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def _fit_crop(img, target_w: int, target_h: int):
    """Scale to fill then center-crop, biasing upward so faces stay in frame."""
    from PIL import Image
    img = img.convert("RGB")
    ratio = max(target_w / img.width, target_h / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - target_w) // 2
    # Bias crop upward (top third) so character faces remain visible
    top = max(0, (nh - target_h) // 4)
    return img.crop((left, top, left + target_w, top + target_h))


def _draw_rank_badge(draw, font_path: str | None, rank: int, name: str,
                     panel_x: int, panel_y: int, panel_w: int, panel_h: int):
    """Draw #rank + name badge at the bottom of a character panel."""
    from PIL import ImageFont
    if not font_path:
        return
    rank_sz = max(22, panel_w // 5)
    name_sz = max(13, panel_w // 9)
    try:
        f_rank = ImageFont.truetype(font_path, rank_sz)
        f_name = ImageFont.truetype(font_path, name_sz)
    except Exception:
        return
    pad = 8
    box_h = rank_sz + name_sz + pad * 3
    by = panel_y + panel_h - box_h
    # Semi-transparent dark box
    draw.rectangle([(panel_x, by), (panel_x + panel_w, panel_y + panel_h)],
                   fill=(0, 0, 0, 190))
    # Gold rank number
    draw.text((panel_x + pad, by + pad), f"#{rank}", font=f_rank, fill=(255, 215, 0, 255))
    # White character name (truncated)
    short = (name[:13] + "…") if len(name) > 14 else name
    draw.text((panel_x + pad, by + pad + rank_sz + 4), short.upper(),
              font=f_name, fill=(255, 255, 255, 255))


def _short_subtitle(title: str) -> str:
    cleaned = re.sub(r"top\s*\d+\s*", "", title, flags=re.IGNORECASE).strip()
    words = cleaned.split()
    return " ".join(words[:6]) if len(words) > 6 else cleaned


def compose_collage(
    char_data: list[tuple[int, str, Path | None]],
    title: str,
    output_path: Path,
):
    """
    Build the thumbnail collage and save to output_path.

    Layout:
      Left  640×720: #1 hero (full height)
      Right 640×720: 2×2 grid (#2 top-left, #3 top-right, #4 bottom-left, #5 bottom-right)
    """
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1280, 720
    HERO_W, HERO_H = 640, 720
    GRID_W, GRID_H = 320, 360

    # Sort ascending: rank 1 = hero
    sorted_chars = sorted(char_data, key=lambda x: x[0])
    hero = sorted_chars[0] if sorted_chars else None
    grid = sorted_chars[1:5]  # up to 4

    grid_pos = [
        (HERO_W,          0),
        (HERO_W + GRID_W, 0),
        (HERO_W,          GRID_H),
        (HERO_W + GRID_W, GRID_H),
    ]

    # Dark base background
    canvas = Image.new("RGB", (W, H), (8, 8, 20))

    # Paste grid images
    for i, (rank, name, img_path) in enumerate(grid):
        gx, gy = grid_pos[i]
        if img_path and img_path.exists():
            try:
                img = _fit_crop(Image.open(img_path), GRID_W, GRID_H)
                canvas.paste(img, (gx, gy))
            except Exception as e:
                print(f"    skip grid {name}: {e}")

    # Paste hero
    if hero and hero[2] and hero[2].exists():
        try:
            img = _fit_crop(Image.open(hero[2]), HERO_W, HERO_H)
            canvas.paste(img, (0, 0))
        except Exception as e:
            print(f"    skip hero {hero[1]}: {e}")

    # --- Overlay layer ---
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Dividers between panels
    draw.line([(HERO_W, 0), (HERO_W, H)], fill=(0, 0, 0, 220), width=5)
    draw.line([(HERO_W + GRID_W, 0), (HERO_W + GRID_W, H)], fill=(0, 0, 0, 180), width=3)
    draw.line([(HERO_W, GRID_H), (W, GRID_H)], fill=(0, 0, 0, 180), width=3)

    font_path = _find_font(bold=True)

    # Rank badges on each panel
    if hero:
        _draw_rank_badge(draw, font_path, hero[0], hero[1], 0, 0, HERO_W, HERO_H)
    for i, (rank, name, _) in enumerate(grid):
        gx, gy = grid_pos[i]
        _draw_rank_badge(draw, font_path, rank, name, gx, gy, GRID_W, GRID_H)

    # TOP N label at top
    n = len(sorted_chars)
    top_text = f"TOP {n}"
    if font_path:
        try:
            f_top = ImageFont.truetype(font_path, int(H * 0.20))
        except Exception:
            f_top = ImageFont.load_default()
        # Dark bar at top
        draw.rectangle([(0, 0), (W, int(H * 0.26))], fill=(0, 0, 0, 150))
        bbox = draw.textbbox((0, 0), top_text, font=f_top)
        tx = W // 2 - (bbox[2] - bbox[0]) // 2
        ty = int(H * 0.02)
        # Red outline
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                if dx or dy:
                    draw.text((tx + dx, ty + dy), top_text, font=f_top, fill=(180, 0, 0, 255))
        # Gold fill
        draw.text((tx, ty), top_text, font=f_top, fill=(255, 215, 0, 255))

    # Subtitle bar at bottom
    subtitle = _short_subtitle(title)
    if subtitle and font_path:
        try:
            f_sub = ImageFont.truetype(font_path, int(H * 0.068))
        except Exception:
            f_sub = ImageFont.load_default()
        bar_h = int(H * 0.16)
        draw.rectangle([(0, H - bar_h), (W, H)], fill=(0, 0, 0, 210))
        bbox = draw.textbbox((0, 0), subtitle.upper(), font=f_sub)
        sx = W // 2 - (bbox[2] - bbox[0]) // 2
        sy = H - bar_h // 2 - (bbox[3] - bbox[1]) // 2
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx or dy:
                    draw.text((sx + dx, sy + dy), subtitle.upper(), font=f_sub,
                              fill=(0, 0, 0, 255))
        draw.text((sx, sy), subtitle.upper(), font=f_sub, fill=(255, 255, 255, 255))

    result = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    result.save(str(output_path), "PNG")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    thumbnail_dir = ensure_dir(output_dir / "thumbnail")
    char_dir = ensure_dir(thumbnail_dir / "characters")

    state = StateManager()
    state.update_step("step-06-thumbnail-creation", "running")

    title = script.get("title", "")
    ranked = extract_ranked_characters(script["scenes"])

    if not ranked:
        print("WARNING: No ranked characters found in script")
    else:
        print(f"Characters: {', '.join(f'#{r} {n}' for r, n in ranked)}")

    try:
        char_data = fetch_character_images(ranked, char_dir)
    except ImportError:
        print("ERROR: requests not installed — run: pip install requests")
        state.update_step("step-06-thumbnail-creation", "failed")
        sys.exit(1)

    found = sum(1 for _, _, p in char_data if p)
    print(f"Images fetched: {found}/{len(char_data)}")

    thumbnail_path = thumbnail_dir / "thumbnail.png"
    print("Composing collage...")
    try:
        compose_collage(char_data, title, thumbnail_path)
    except ImportError:
        print("ERROR: Pillow not installed — run: pip install Pillow")
        state.update_step("step-06-thumbnail-creation", "failed")
        sys.exit(1)

    size_kb = thumbnail_path.stat().st_size // 1024
    print(f"  Thumbnail saved: {thumbnail_path} ({size_kb}KB)")
    state.update_step("step-06-thumbnail-creation", "completed",
                      {"thumbnail_path": str(thumbnail_path)})


if __name__ == "__main__":
    main()
