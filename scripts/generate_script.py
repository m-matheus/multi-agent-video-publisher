"""
Script generator — writes script.json via Claude and prints AMV search queries.

Content-first: the full script is generated from the topic alone. AMVs are
background — search for them using the queries printed after generation.

Usage:
    python scripts/generate_script.py \
        --output-dir output/20260621-top5-solo-leveling \
        --topic "Top 5 Strongest Hunters in Solo Leveling"

    # Short (Curiosidade format)
    python scripts/generate_script.py \
        --output-dir output/20260621-top5-solo-leveling \
        --topic "Sung Jinwoo was never supposed to survive the Double Dungeon" \
        --short curiosity \
        --anime solo-leveling

    # Dry-run: print script without saving
    python scripts/generate_script.py \
        --output-dir output/20260621-top5-solo-leveling \
        --topic "Top 5 Strongest Hunters in Solo Leveling" \
        --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config

# ── Constants ──────────────────────────────────────────────────────────────────

SCRIPT_MODEL = "claude-sonnet-4-6"

SHORT_FORMATS = ("curiosity", "recap", "detail")

SYSTEM_PROMPT = """\
You are an anime YouTube script writer. Your style is modeled after creators who \
explain anime like a knowledgeable friend talking to another fan — conversational, \
genuinely enthusiastic, with personality. Not a hype announcer. Not a Wikipedia \
summary. A friend who watched the show and can't stop talking about it.

Study these real examples from top anime channels to calibrate your tone:

EXAMPLE 1 (intro hook):
"Listen, I think I haven't even blinked my eyes. I started one episode of these \
anime and next thing I know it's already end."

EXAMPLE 2 (character intro):
"Then there is Ashaf, the calmest guy ever, and bro, he's smoking in almost every \
episode. Something crazy happens. He lights up. Big enemy shows up, he lights \
another, and just like that, the problem's basically solved."

EXAMPLE 3 (show pitch with a reframe):
"Darker than Black is basically what if superpowers came with the world's dumbest \
side effects. Like, yeah, you can control lightning, but you got to eat 10 bowls \
of ramen afterward."

EXAMPLE 4 (personal reaction embedded naturally):
"She moves like she's made of rubber, shows up right when Ganta needs someone, and \
isn't scared of anything. There's clearly something different about her. But she \
smiles so big you kind of forget to question it."

EXAMPLE 5 (honest admission):
"The only sad part, the anime ends super early, so you don't get as much story as \
you might want. But even with that, it's still enjoyable."

---

TONE RULES (derived from examples above)

DO:
- Write like you're talking to a friend who also watches anime
- Use specific, vivid details: what a character does, how they move, their quirks
- Reframe the premise in one unexpected angle before explaining it straight
- Mix long descriptive sentences with short punchy reactions
- Let the narrator's personality show: reactions, opinions, mild humor
- Use casual constructions: "bro", "yeah", "nope", "kind of", "straight up"
- Describe characters by their personality and behavior, not by their power level
- End a section with why a viewer will stay hooked, not with a comparison

DON'T:
- Write ALL CAPS for emphasis — stress comes from word choice and rhythm, not caps
- Use superlatives like "the most BROKEN", "absolute MONSTER", "GOAT"
- Open scenes with "Today we look at", "In this video", "Let's count down"
- Announce power levels or rankings as the main hook ("He's a top-tier S-class—")
- Compare this rank to the next one ("but that's why he's only rank 5")
- Be generic — every sentence must say something specific about this show/character
- Sound like a Wikipedia summary or an encyclopedia entry

---

RANKING VIDEOS — STRUCTURE

Scene 1  (intro, ~12s): Open with a personal reaction or vivid image that sets \
the mood. Hook the viewer into wanting to know the list. NOT a bold claim — a \
relatable feeling or surprising observation.

Scene 2  (normal, ~10s): Brief context — what makes this ranking worth watching. \
Why these specific characters/moments. End with a pivot into the countdown.

For each rank from N down to 1:
  rank_transition (~2.5s): narration_text = "Number N." (syncs with rank card — \
keep it short)
  normal (~20s): Reframe the character/show from an unexpected angle. Then describe \
who they are through behavior and personality, not achievements. Use at least one \
specific vivid detail (a quirk, a moment, a habit).
  normal (~18s): Describe their defining moment or key storyline. Make the viewer \
feel the scene, not just understand it. Present tense, specific sensory details.
  normal (~12s): Why this character/show leaves a mark. What is the one thing a \
viewer will remember. End on the character themselves — not on how they compare \
to the next rank.

Last scene (normal, ~18s): Wrap up the list naturally. Personal take on the topic. \
Ask a genuine question that invites debate — not "like and subscribe".

TARGET: ~300s (5 minutes) for Top 5. Never compress below 270s.

RANK TRANSITIONS
- Always include "name" field. Match the ranking type:
  - Fight ranking → "Fighter A vs Fighter B" (e.g. "Luffy vs Kaido")
  - Character ranking → character name only (e.g. "Itachi")
  - Anime ranking → series title (e.g. "Demon Slayer")
- Always include "amv" field matching the rank's AMV number.
- narration_text must be exactly "Number N." — nothing else.

---

SHORT VIDEOS (40–55s) — 5-BEAT STRUCTURE

Beat 1 — HOOK    (~3s):  One specific, surprising observation. Feels personal, not \
announced. "I cannot believe nobody talks about this."
Beat 2 — CONTEXT (~8s):  The situation or setup that makes the hook surprising.
Beat 3 — REVEAL  (~15s): The actual fact, moment, or detail — narrated with the \
same conversational energy, not as a list.
Beat 4 — IMPACT  (~10s): Why it matters. What it changed. What fans miss.
Beat 5 — CTA     (~5s):  A genuine, specific question. Not "smash like". \
Something the viewer actually wants to answer.

---

OUTPUT FORMAT
Return a single valid JSON object. No markdown fences. No explanation before or \
after. The JSON must exactly match this schema:

{
  "title": "Compelling YouTube title (max 100 chars)",
  "description": "YouTube video description with relevant keywords",
  "tags": ["tag1", "tag2", "tag3"],
  "content_type": "amv",
  "target_duration_seconds": 300,
  "scenes": [
    {
      "scene_number": 1,
      "scene_type": "intro | normal | rank_transition",
      "rank": 5,
      "name": "Character or 'A vs B' — required on rank_transition scenes",
      "amv_query": "specific YouTube search query to find AMV footage for this rank (rank_transition scenes only)",
      "amv": 1,
      "duration_seconds": 15.0,
      "visual_prompt": "Detailed scene description",
      "narration_text": "Spoken narration for this scene",
      "transition": "fade | cut | dissolve"
    }
  ]
}

Rules:
- Never include "clip_index" — let the compositor cycle clips in sequence.
- Never include "search_tags" — frames are already extracted from the AMV.
- scene_type values: "intro", "normal", "rank_transition" only.
- rank field: integer, present on rank_transition and all normal scenes within a rank.
- amv field: integer (1–N), required on every scene in multi-AMV videos.
- amv_query field: only on rank_transition scenes. Specific YouTube search to find AMV \
footage for that rank (e.g. "sung jinwoo shadow monarch amv 4k"). Include character + \
series + "amv". For fights: include both fighters.
- duration_seconds must sum to target_duration_seconds (±5%).
- Minimum 5 scenes. Maximum 60 scenes.
- All narration in English.
"""



# ── AMV analysis loader ────────────────────────────────────────────────────────

def find_amv_analyses(output_dir: Path) -> list[tuple[int, dict]]:
    results = []
    for i in range(1, 20):
        path = output_dir / f"amv{i}" / "amv" / "amv_analysis.json"
        if path.exists():
            results.append((i, json.loads(path.read_text(encoding="utf-8"))))
    if results:
        return results
    path = output_dir / "amv" / "amv_analysis.json"
    if path.exists():
        return [(1, json.loads(path.read_text(encoding="utf-8")))]
    return []


def count_remaining_clips(output_dir: Path, amv_index: int) -> int:
    frames_dir = output_dir / f"amv{amv_index}" / "frames"
    if not frames_dir.exists():
        frames_dir = output_dir / "frames"
    if not frames_dir.exists():
        return 0
    return len([f for f in frames_dir.iterdir() if f.suffix in (".mp4", ".webm", ".gif", ".jpg", ".png")])


# ── Prompt builders ────────────────────────────────────────────────────────────

def build_script_prompt(
    topic: str,
    analyses: list[tuple[int, dict]],
    output_dir: Path,
    short_format: str | None,
    anime_slug: str | None,
    amv_index: int | None = None,
) -> str:
    lines = []

    if short_format:
        format_label = {"curiosity": "Curiosidade", "recap": "Iconic Moment Recap", "detail": "Hidden Detail"}[short_format]
        lines.append(f"Generate a {format_label} Short script (40–55s, 5-beat structure).")
        lines.append(f"Topic / hook: {topic}")
        if anime_slug:
            lines.append(f"Anime: {anime_slug}")
        lines.append("")
    else:
        lines.append("Generate a full ranking video script.")
        lines.append(f"Topic: {topic}")
        lines.append("")

    if analyses:
        lines.append(f"Number of AMVs available: {len(analyses)}")
        lines.append("")
        for amv_idx, analysis in analyses:
            clips_remaining = count_remaining_clips(output_dir, amv_idx)
            total_duration = analysis.get("total_duration_seconds", 0)
            scenes = analysis.get("scenes", [])
            lines.append(f"=== AMV {amv_idx} ===")
            lines.append(f"Total duration: {total_duration:.1f}s | Clips: {clips_remaining}")
            lines.append("")
    else:
        lines.append("No AMV analyses available — assign amv=1 to all scenes (single AMV assumed).")
        lines.append("")

    if short_format:
        # For Shorts, lock all scenes to a single AMV to keep visual focus
        forced = amv_index if amv_index else 1
        lines.append(f"IMPORTANT: This is a Short about a single moment. Set amv={forced} on ALL scenes — do NOT spread scenes across different AMVs.")
        lines.append("")
    elif not short_format:
        lines.append("IMPORTANT SCRIPT RULES:")
        lines.append("- Route each scene to the correct AMV using the 'amv' field.")
        lines.append("- Narration drives pacing — compositor auto-extends scenes to fit TTS audio.")
        lines.append("- Intro scenes (1–3) should draw from different AMVs for visual variety.")
        lines.append("- rank_transition 'name' must match the ranking type (see system prompt).")
        lines.append("- rank_transition 'amv' must match the rank's AMV number.")
        lines.append("- Last scene duration will be trimmed to actual TTS length — write a ~20s outro.")
        lines.append("")

    lines.append("Return only valid JSON. No markdown, no explanation.")
    return "\n".join(lines)


# ── Claude calls ───────────────────────────────────────────────────────────────

def generate_script(user_prompt: str, config: dict) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
    print(f"Calling {SCRIPT_MODEL}...")
    response = client.messages.create(
        model=SCRIPT_MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
    return json.loads(raw)


# ── Output helpers ─────────────────────────────────────────────────────────────

def resolve_output_path(output_dir: Path, short_format: str | None, anime_slug: str | None) -> Path:
    script_dir = output_dir / "script"
    script_dir.mkdir(parents=True, exist_ok=True)
    if short_format is None:
        return script_dir / "script.json"
    slug = anime_slug or "anime"
    return script_dir / f"script_{short_format}_{slug}.json"


def print_amv_queries(script: dict):
    ranks = [s for s in script.get("scenes", []) if s.get("scene_type") == "rank_transition"]
    if not ranks:
        return
    print()
    print("AMV search queries (search on YouTube and pass URLs to fetch_amv.py):")
    for scene in sorted(ranks, key=lambda s: s.get("rank", 0), reverse=True):
        rank = scene.get("rank", "?")
        name = scene.get("name", "?")
        query = scene.get("amv_query", "")
        amv_idx = scene.get("amv", rank)
        print(f"  amv{amv_idx} (Rank {rank} — {name}): \"{query}\"")


def print_script_summary(script: dict, output_path: Path):
    scenes = script.get("scenes", [])
    total = sum(s.get("duration_seconds", 0) for s in scenes)
    print()
    print("=" * 60)
    print(f"Title:    {script.get('title', 'N/A')}")
    print(f"Scenes:   {len(scenes)}")
    print(f"Duration: {total:.0f}s ({total / 60:.1f} min)")
    print(f"Tags:     {', '.join(script.get('tags', [])[:6])}")
    print()
    print("Scene breakdown:")
    for scene in scenes:
        n = scene.get("scene_number", "?")
        stype = scene.get("scene_type", "normal")
        rank = scene.get("rank")
        name = scene.get("name", "")
        dur = scene.get("duration_seconds", 0)
        narration = scene.get("narration_text", "")[:70]
        rank_label = f" [rank {rank}]" if rank else ""
        name_label = f" — {name}" if name else ""
        print(f"  {n:>2}. [{stype}{rank_label}{name_label}] {dur:.1f}s")
        if narration:
            print(f"      \"{narration}{'...' if len(scene.get('narration_text', '')) > 70 else ''}\"")
    print()
    print(f"Output:   {output_path}")
    print("=" * 60)


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Generate script.json via Claude")
    parser.add_argument("--output-dir", required=True,
                        help="Run output directory (e.g. output/20260621-top5-naruto)")
    parser.add_argument("--topic", required=True,
                        help="Video topic or hook sentence")
    parser.add_argument("--short", choices=SHORT_FORMATS, default=None,
                        help="Generate a Short script instead of a full video")
    parser.add_argument("--anime", default=None,
                        help="Anime slug for Short filename (e.g. 'naruto', 'one-piece')")
    parser.add_argument("--amv", type=int, default=None,
                        help="For Shorts: lock all scenes to this AMV index (e.g. --amv 1). Defaults to 1 if not set.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the generated script without saving it")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    analyses = find_amv_analyses(output_dir)
    if analyses:
        print(f"Found {len(analyses)} AMV analysis file(s).")
        for amv_idx, analysis in analyses:
            n_scenes = len(analysis.get("scenes", []))
            dur = analysis.get("total_duration_seconds", 0)
            clips = count_remaining_clips(output_dir, amv_idx)
            print(f"  AMV {amv_idx}: {n_scenes} clips, {dur:.0f}s total, {clips} after curation")
    else:
        print("No AMV analyses found — generating script without clip context.")

    user_prompt = build_script_prompt(
        topic=args.topic,
        analyses=analyses,
        output_dir=output_dir,
        short_format=args.short,
        anime_slug=args.anime,
        amv_index=args.amv,
    )

    script = generate_script(user_prompt, config)
    output_path = resolve_output_path(output_dir, args.short, args.anime)

    print_script_summary(script, output_path)
    print_amv_queries(script)

    if args.dry_run:
        print("\nDRY-RUN: script not saved.")
        print()
        print(json.dumps(script, indent=2, ensure_ascii=False))
        return

    output_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nScript saved to: {output_path}")
    print("Next: download AMVs using the queries above, then run fetch_amv.py + analyze_amv.py.")


if __name__ == "__main__":
    main()
