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

# Baseline framing applied to every multi-anime thumbnail — mirrors the visual
# language of top creators (Anime Balls Deep, Plot Armor, Anime Explained, etc.).
PREMIUM_BASELINE = """
Create a modern viral anime YouTube thumbnail optimized for high CTR.

Composition rules:
One dominant character occupies 50% of the thumbnail on the right side.
The character should be extremely detailed, sharp, confident, and visually powerful.

Place secondary characters in the background, partially shadowed and smaller.
Create strong depth separation between foreground and background.

Use cinematic anime key art quality, similar to official promotional posters.

Background should feature epic environmental effects related to the anime
(energy, cosmos, flames, lightning, dimensional effects, aura, destruction, etc).

Use dramatic rim lighting, strong glow effects, volumetric lighting and high contrast.

TEXT RULES — critical:
- Include 2–4 short punchy words that tease the video's hook. Text should demand attention.
- Examples of good text: "NOBODY WATCHES THIS", "ACTUALLY PERFECT", "BURIED BY THE ALGORITHM", "YOU MISSED THIS".
- DO NOT use generic red/yellow block letters. NEVER use thick outline fonts.
- Style: editorial magazine or film poster typography — clean, confident, high contrast.
  Think: a word or short phrase set in a strong condensed sans-serif or dramatic serif,
  integrated into the composition, not slapped on top.
- Color should complement the image (white, off-white, pale gold, deep black, or drawn from the character palette).
- Text placement must feel intentional — top-left flush, bottom-right anchor, or overlaid on negative space.
- The result should look like a human designer made it, not an AI template.

Thumbnail should instantly communicate power, ranking, mystery, or superiority.

No clutter. No UI elements. No subtitles. No ranking numbers.
Only one clear focal point.
""".strip()


# Baseline for single-anime ranking videos — the franchise's official logo and
# the protagonist (or main hero) anchor the design, not generic "you missed this"
# clickbait copy. Lifted from how the official channels and big anime creators
# brand their fight-ranking content.
SINGLE_SERIES_BASELINE = """
Create a viral YouTube thumbnail for a single-franchise ranking video.

Composition:
The franchise's main protagonist is the dominant figure — centered or slightly right,
filling roughly half the thumbnail in a powerful close shot. Render them in their
most iconic form (peak transformation, signature pose, or definitive battle stance).

Place 1–2 supporting characters from the same anime in the background — smaller,
partially shadowed, partially behind the protagonist. Hint at the rest of the
ranked cast without crowding the frame. No ranking numbers anywhere.

Use cinematic anime key art quality matching the show's official promotional posters.
Background should evoke an iconic location or signature visual effect from the series
(flag of the crew, the show's signature aura color, a battlefield from a memorable arc, etc).

Use dramatic rim lighting, strong glow effects, volumetric lighting and high contrast.

TEXT RULES — critical:
- The headline must be the franchise name treated as the show's official logo.
  Use the show's actual logo aesthetic (color, font, weight, glow) — no generic fonts.
  Place the logo prominently in the upper-left or upper-center.
- Below or beside the logo, add 2–3 punchy words that describe the ranking
  (e.g. "TOP 5 FIGHTS", "STRONGEST BATTLES", "GREATEST DUELS", "BEST FIGHTS EVER").
  This subtitle should be smaller than the logo but still bold and fully visible.
- DO NOT use generic clickbait phrases like "YOU MISSED THIS" or "NOBODY WATCHES THIS".
- All text must be fully visible — never cropped at any edge.

Thumbnail should instantly read as "this is THE ranking video for {SERIES}".

No clutter. No UI elements. No subtitles. No ranking numbers on the image.
""".strip()



# Typography style hint per anime — used when the video is about a single series.
# Instructs GPT-4o to mimic each show's official visual identity (color, font feel, logo aesthetic).
ANIME_LOGO_STYLE: dict[str, str] = {
    "dragon ball": "Use the Dragon Ball Z logo aesthetic: bold orange-gold kanji-style lettering, dark outline, fiery aura surrounding the title treatment.",
    "naruto": "Use the Naruto logo aesthetic: orange and black lettering, brushstroke style, with subtle leaf village motifs.",
    "demon slayer": "Use the Kimetsu no Yaiba logo aesthetic: thin elegant Japanese calligraphy-inspired lettering in deep red on black, very minimal.",
    "attack on titan": "Use the Attack on Titan logo aesthetic: stark military stencil-style lettering in white or grey, gritty and austere.",
    "jujutsu kaisen": "Use the Jujutsu Kaisen logo aesthetic: white clean modern lettering with purple-blue cursed energy glow, minimal and striking.",
    "one piece": "Use the One Piece logo aesthetic: bold adventure-style lettering in yellow-gold with black outline, slightly weathered.",
    "bleach": "Use the Bleach logo aesthetic: sharp white lettering with subtle orange trim, clean and powerful.",
    "fullmetal alchemist": "Use the Fullmetal Alchemist logo aesthetic: gold alchemical engraving style, red accents, detailed and intricate.",
    "my hero academia": "Use the My Hero Academia logo aesthetic: bold red-white-blue comic-book style with clean superhero energy.",
    "one punch man": "Use the One Punch Man logo aesthetic: plain bold black lettering on a stark background — intentionally understated and ironic.",
    "hunter x hunter": "Use the Hunter x Hunter logo aesthetic: clean blue-green gem-like lettering, refined and slightly mysterious.",
    "black clover": "Use the Black Clover logo aesthetic: jagged dark lettering with bright green magic glow, gritty and energetic.",
    "vinland saga": "Use the Vinland Saga logo aesthetic: Norse rune-inspired, worn stone or wood engraving feel, cold grey-blue palette.",
    "chainsaw man": "Use the Chainsaw Man logo aesthetic: raw dripping horror-comic lettering in blood red and black, unpolished and visceral.",
    "spy x family": "Use the Spy x Family logo aesthetic: sleek mission-briefing sans-serif with pastel spy-thriller colors, playful yet elegant.",
    "tokyo ghoul": "Use the Tokyo Ghoul logo aesthetic: fragmented cracked lettering in crimson and black, ominous and organic.",
    "sword art online": "Use the Sword Art Online logo aesthetic: clean digital fantasy lettering in silver-blue, high-tech and sleek.",
    "fairy tail": "Use the Fairy Tail logo aesthetic: rounded warm guild-emblem style, warm amber and brown tones, inviting and bold.",
    "re:zero": "Use the Re:Zero logo aesthetic: dark blue-black lettering with pale lavender shadows, quiet and melancholic.",
    "overlord": "Use the Overlord logo aesthetic: gothic dark-fantasy lettering in bone-white and obsidian, regal and sinister.",
}


def _detect_single_series(script: dict) -> str:
    """Detect if all ranked entries belong to a single anime franchise.

    Returns the franchise key (e.g. 'one piece') or '' if it's a multi-anime
    ranking. Detection looks at the title first (e.g. "Top 5 One Piece Fights")
    and falls back to the explicit `series` field.
    """
    series = (script.get("series") or "").lower()
    if series:
        return series
    title = (script.get("title") or "").lower()
    for key in ANIME_LOGO_STYLE.keys():
        if key in title:
            return key
    return ""


# Default protagonist for single-anime rankings — used to center the franchise's
# face character in the thumbnail when the ranking is all one series (e.g. a
# "Top 5 One Piece fights" video should feature Luffy, not the #1 villain).
SERIES_PROTAGONIST: dict[str, str] = {
    "one piece": "Monkey D. Luffy",
    "naruto": "Naruto Uzumaki",
    "dragon ball": "Goku",
    "bleach": "Ichigo Kurosaki",
    "demon slayer": "Tanjiro Kamado",
    "attack on titan": "Eren Yeager",
    "jujutsu kaisen": "Yuji Itadori",
    "my hero academia": "Izuku Midoriya",
    "fullmetal alchemist": "Edward Elric",
    "hunter x hunter": "Gon Freecss",
    "black clover": "Asta",
    "chainsaw man": "Denji",
    "tokyo ghoul": "Ken Kaneki",
    "sword art online": "Kirito",
    "fairy tail": "Natsu Dragneel",
    "spy x family": "Loid Forger",
    "vinland saga": "Thorfinn",
    "re:zero": "Subaru Natsuki",
    "overlord": "Ainz Ooal Gown",
    "one punch man": "Saitama",
}


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
    ranked_names = [
        s.get("name") for s in scenes
        if s.get("scene_type") == "rank_transition" and s.get("name")
    ]
    series_key = _detect_single_series(script)
    # Single-anime ranking: feature the franchise protagonist, not the #1 villain.
    # (e.g. "Top 5 One Piece Fights" → Luffy centered, not Kaido.)
    if series_key and series_key in SERIES_PROTAGONIST:
        top_character = SERIES_PROTAGONIST[series_key]
    # Allow explicit `thumbnail_character` to override either default.
    top_character = script.get("thumbnail_character", top_character)
    series = script.get("series", "") or (series_key.title() if series_key else "")
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


def _resolve_anime_logo_style(script: dict, ranked_names: list) -> str:
    """Return a logo-style hint if the video is clearly about a single anime series."""
    series = script.get("series", "").lower()
    title = script.get("title", "").lower()

    # Single-series: either `series` field set, or only one distinct ranked name
    distinct = {n for n in ranked_names if n}
    candidate = series or (list(distinct)[0].lower() if len(distinct) == 1 else "")

    if not candidate:
        return ""

    for key, style in ANIME_LOGO_STYLE.items():
        if key in candidate or key in title:
            return style

    # Generic fallback for unknown single-series: minimal elegant treatment
    return (
        f"Incorporate the official logo aesthetic of {candidate.title()} if recognizable. "
        "Use colors drawn from the show's official art — avoid generic red/yellow/white. "
        "Keep text minimal and styled like the show's title card, not a generic YouTube template."
    )


def build_chatgpt_request(script: dict) -> str:
    context = build_context_block(script)
    scenes = script.get("scenes", [])
    ranked_names = [
        s.get("name") for s in scenes
        if s.get("scene_type") == "rank_transition" and s.get("name")
    ]
    logo_hint = _resolve_anime_logo_style(script, ranked_names)

    # Single-anime ranking → use the franchise-logo baseline (official-looking
    # title treatment + protagonist), not the generic clickbait baseline.
    series_key = _detect_single_series(script)
    is_single_series = bool(series_key) or len({n for n in ranked_names if n}) == 1
    baseline = SINGLE_SERIES_BASELINE if is_single_series else PREMIUM_BASELINE

    return "\n\n".join(filter(None, [
        "Create a viral YouTube thumbnail for an anime video.",
        context,
        baseline,
        logo_hint,
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
