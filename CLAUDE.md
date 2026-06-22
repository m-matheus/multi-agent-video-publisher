# YouTube Video Generator Squad

## Role
You (Claude) are the **orchestrator** of this multi-agent pipeline. You generate the video scripts directly (you ARE the LLM) and trigger each agent's Python script in sequence, managing checkpoints and state.

## How to Run a Video Generation

For **anime content**, the **AMV Workflow** is the default. The script is generated first (content-first), then AMV URLs are collected based on the script's search queries.

---

### Step 1: Script Generation (YOU do this directly)
1. Ask the user for the **topic** and **content type** (anime or amv) if not provided
2. Generate a `script.json` following the schema below
3. Write it to `output/{YYYYMMDD}-{topic}/script/script.json` (date prefix first, e.g. `20260603-top5-db-villains`)
4. Show the script summary to the user for review

### Step 2: CHECKPOINT — Approve Script
- Present: title, number of scenes, total duration, scene list
- Wait for user approval before proceeding
- User can request changes — regenerate if needed

### Step 2b: Generate Thumbnail
```bash
python scripts/generate_thumbnail.py \
    --script-path "{output_dir}/script/script.json" \
    --output-dir "{output_dir}"
```
- Uses Responses API: `client.responses.create(model="gpt-4o", tools=[{"type": "image_generation"}])` — same pipeline as ChatGPT
- GPT-4o writes a detailed image prompt; `gpt-image-1` renders the image
- Output: `{output_dir}/thumbnail/thumbnail.jpg` (1280x720 JPEG)
- Can run in parallel with Step 3 and Step 4

**Visual standards:**
- #1 ranked character centered and large (close shot); other characters in background
- No character names or ranking numbers in the image
- 2–3 bold title words fully visible, never cut off
- Native anime visual style and color palette

### Step 3: Fetch Anime Frames/Clips
This step is handled by the AMV workflow — see AMV Step 3–4 below for downloading and analyzing the source AMV.

The user can also provide a local folder of frames by placing them directly in `{output_dir}/frames/` before running Step 6 (compose).

### Step 4: Generate Voice Narration
```bash
python scripts/generate_voice.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```

### Step 5: Fetch BGM (YOU choose the query)
Based on the video topic and content type, choose a search query and run:

**Primary — Freesound CC0 (zero Content ID claims):**
```bash
python scripts/fetch_bgm.py --query "{bgm_query}" --output-dir "{output_dir}"
```

**Fallback — YouTube (only if Freesound returns nothing):**
```bash
python scripts/fetch_bgm.py --search "{bgm_query}" --output-dir "{output_dir}"
```

**BGM query selection guidelines (use these for both `--query` and `--search`):**
- Anime action/fighting → `"epic orchestral cinematic"`
- Anime emotional/dramatic → `"emotional piano orchestral"`
- Dragon Ball / power ranking → `"epic orchestral cinematic"`
- Naruto → `"epic orchestral cinematic"`
- Demon Slayer → `"dark orchestral epic"`
- General anime → `"epic cinematic orchestral"`

The `--query` mode automatically applies `duration:[60 TO 300] license:"Creative Commons 0"` filter.

### Step 6: Compose Final Video
```bash
python scripts/compose_video.py --script-path "{output_dir}/script/script.json" --frames-dir "{output_dir}/frames" --audio-dir "{output_dir}/audio" --output-dir "{output_dir}" --bgm-path "{output_dir}/audio/bgm.mp3" --bgm-volume 0.15
```

The compositor handles:
- Video clips (mp4, webm): trims or loops to scene duration
- GIFs: loops to fill duration
- Static images: applies Ken Burns zoom/pan effect
- All clips normalized to 1920x1080 @ 24fps

### Step 7: CHECKPOINT — Approve Video
- Report final video path, duration, file size
- Wait for user approval before publishing

### Step 8: Publish to YouTube
Publish as private for manual review (default). If the user already specified a date/time, use `--publish-at` instead:
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --privacy "private" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```
If the user specified a date/time for publishing, use `--publish-at "YYYY-MM-DD HH:MM"` (drop `--privacy`):
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --publish-at "YYYY-MM-DD HH:MM" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

---

## AMV Workflow (YouTube AMV as background)

Use this workflow when the user wants to create an anime video. The full pipeline from trend research to publish.

### AMV Step 1: Trend Research
Run channel analytics first, then trends (trends auto-loads the channel cache for dedup + suggestions):
```bash
python scripts/analyze_channel.py --days 90 --output-file output/channel_analytics.json --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q
```
```bash
python scripts/analyze_trends.py \
  --days 30 \
  --min-duration 60 \
  --channel-cache output/channel_analytics.json \
  --output-file output/trends_cache.json
```

If there are specific anime currently trending due to news/new seasons, add `--boost-anime`:
```bash
python scripts/analyze_trends.py \
  --days 30 \
  --min-duration 60 \
  --channel-cache output/channel_analytics.json \
  --output-file output/trends_cache.json \
  --boost-anime "Solo Leveling" "Dandadan"
```

The trends script uses a built-in query bank (no `--queries` needed) and prints a **Top 10 Trending** table (with anime + format detected), franchises already on the channel, and a **Suggested Topics** section automatically. Use the suggestions as the basis for AMV Step 2.

### AMV Step 2: CHECKPOINT — Suggest Themes
- Propose 3–5 topic options based on trend + channel data
- For each option, include 2–3 bullet points on what visual moments would best illustrate the ranking (e.g., "Rank 5 – Orochimaru: Orochimaru vs Hiruzen, cursed mark application, snake summoning")
- **Wait for user to pick a theme**

### AMV Step 3: Generate Script
Once the user picks a topic, create the output folder and run `generate_script.py`:
```bash
python scripts/generate_script.py \
  --output-dir "output/{YYYYMMDD}-{slug}" \
  --topic "{chosen topic}"
```
- Generates `script.json` via Claude based on the topic alone (content-first — no AMVs needed yet)
- Prints a scene breakdown + **AMV search queries** (one per rank transition) to find footage
- Output: `{output_dir}/script/script.json`

### AMV Step 4: CHECKPOINT — Approve Script
- Present: title, number of scenes, total duration, narration preview
- Show the printed AMV search queries — one per rank, each with a suggested YouTube search
- User can request tone/topic changes — rerun `generate_script.py` if needed
- **Wait for user to approve before downloading AMVs**

### AMV Step 5: Download AMVs (one per rank)
The script prints one `amv_query` per rank transition. The user searches YouTube using those queries and returns URLs. Download each into its own numbered subdirectory:
```bash
python scripts/fetch_amv.py --url "{amv1_url}" --output-dir "{output_dir}/amv1"
python scripts/fetch_amv.py --url "{amv2_url}" --output-dir "{output_dir}/amv2"
# ...one per rank
```
Creates: `{output_dir}/amvN/amv/amv_source.mp4` and `amvN/amv/amv_metadata.json`

### AMV Step 6: Analyze AMVs
Analyze each AMV in parallel:
```bash
python scripts/analyze_amv.py --amv-path "{output_dir}/amv1/amv/amv_source.mp4" --output-dir "{output_dir}/amv1"
python scripts/analyze_amv.py --amv-path "{output_dir}/amv2/amv/amv_source.mp4" --output-dir "{output_dir}/amv2"
# ...one per AMV
```
- Detects natural scene cuts via ffmpeg
- Splits the AMV into `frames/scene_01.mp4`, `frames/scene_02.mp4`, etc. (pure ffmpeg, no API calls)
- Creates: `{output_dir}/amvN/amv/amv_analysis.json`

Optional flags: `--max-scenes 12` (default), `--min-scene-duration 3.0` (default, seconds)

### AMV Step 7: CHECKPOINT — Review Clips
- Tell the user to open each `amvN/frames/` folder and watch the clips (navigate manually)
- User deletes any clips they don't want used in the video
- **Before asking for confirmation**, calculate and show the screen time per rank block using the `duration_seconds` values from `script.json` — group by rank and sum scene durations. Format as a table: Rank | Scenes | Duration. This helps the user know how much footage each rank has before cutting.
- **Wait for user confirmation** before proceeding
- After confirmation, list how many clips remain per AMV so the user can verify

### AMV Step 8: CHECKPOINT — Approve Script (final review)
- Re-read `script.json` and present: title, number of scenes, total duration, narration preview
- The script was generated from the topic alone — user may want to tweak narration now that they've seen the actual clips
- If changes are needed, rerun `generate_script.py` with an updated `--topic` or edit `script.json` manually
- **Wait for user to confirm before proceeding to voice generation**

### AMV Step 8b: Generate Thumbnail
```bash
python scripts/generate_thumbnail.py \
    --script-path "{output_dir}/script/script.json" \
    --output-dir "{output_dir}"
```
- Uses Responses API: `client.responses.create(model="gpt-4o", tools=[{"type": "image_generation"}])` — same pipeline as ChatGPT
- GPT-4o writes a detailed image prompt; `gpt-image-1` renders the image
- Output: `{output_dir}/thumbnail/thumbnail.jpg` (1280x720 JPEG)
- Can run in parallel with AMV Step 9

**Visual standards:**
- #1 ranked character centered and large (close shot); other characters in background
- No character names or ranking numbers in the image
- 2–3 bold title words fully visible, never cut off
- Native anime visual style and color palette

### AMV Step 9: Generate Voice Narration
```bash
python scripts/generate_voice.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```

### AMV Step 10: Fetch BGM

**Primary — Freesound CC0 (zero Content ID claims):**
```bash
python scripts/fetch_bgm.py --query "{bgm_query}" --output-dir "{output_dir}"
```

**Fallback — YouTube (only if Freesound returns nothing):**
```bash
python scripts/fetch_bgm.py --search "{bgm_query}" --output-dir "{output_dir}"
```
Use the BGM query guidelines from the standard workflow above.

### AMV Step 11: Compose Final Video
**Single AMV:**
```bash
python scripts/compose_video.py \
  --script-path "{output_dir}/script/script.json" \
  --frames-dir "{output_dir}/frames" \
  --audio-dir "{output_dir}/audio" \
  --output-dir "{output_dir}" \
  --bgm-path "{output_dir}/audio/bgm.mp3" \
  --bgm-volume 0.15 \
  --endcard-path "channels/hakase-anime/assets/endcard.png" \
  --endcard-duration 10
```

**Multi-AMV (Top N):**
```bash
python scripts/compose_video.py \
  --script-path "{output_dir}/script/script.json" \
  --frames-dir "{output_dir}/amv1/frames" \
  --audio-dir "{output_dir}/audio" \
  --output-dir "{output_dir}" \
  --bgm-path "{output_dir}/audio/bgm.mp3" \
  --bgm-volume 0.15 \
  --amv-base-dir "{output_dir}" \
  --endcard-path "channels/hakase-anime/assets/endcard.png" \
  --endcard-duration 10
```

> **`--zoom-crop` is opt-in only** — add it only if the user explicitly requested it when submitting the AMV URL (e.g., "esse amv precisa de zoom"). Never pass it by default.

The compositor automatically:
- Routes scenes to `amvN/frames/` based on the `amv` field in script.json
- Uses `clip_index` if specified, otherwise cycles clips in order
- **Never cuts narration** — extends scene duration to fit full TTS audio
- **Always appends end card** (via `--endcard-path` flag above)

### AMV Step 12: CHECKPOINT — Approve Video
- Report final video path, duration, file size
- Wait for user approval before publishing

### AMV Step 13: Publish to YouTube
Publish as private for manual review (default). If the user already specified a date/time, use `--publish-at` instead:
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --privacy "private" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```
If the user specified a date/time for publishing, use `--publish-at "YYYY-MM-DD HH:MM"` (drop `--privacy`):
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --publish-at "YYYY-MM-DD HH:MM" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

### AMV Step 14: Post-Publish Steps
After the video is uploaded (still private), do all of these before making it public:

1. **Update description (chapters + hashtags) + tags + make public** — run `update_video.py`:
   ```bash
   python scripts/update_video.py \
     --video-id "{video_id}" \
     --script-path "{output_dir}/script/script.json" \
     --make-public
   ```
   - Rebuilds the description with chapter timestamps generated from `script.json` scene durations
   - Appends hashtags from the script tags list
   - Expands tags with SEO keywords (series names, year, genre)
   - `--make-public` changes privacy to public (skip this flag if `--publish-at` was used — it goes public automatically at scheduled time)
   - Use `--dry-run` first to preview description + tags without calling the API

2. **Post engagement comment** — post a pinned comment asking viewers to engage (e.g., "Which anime from this list is your favorite? Drop it in the comments! 👇"). Then ask the user to go to YouTube Studio and pin it, as the API cannot pin comments directly.

3. **Generate community post** — run the community post generator:
   ```bash
   python scripts/post_community.py \
     --script-path "{output_dir}/script/script.json" \
     --video-id "{video_id}" \
     --output-dir "{output_dir}" \
     --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
   ```
   Print the full `post_text` output to the conversation so the user can copy and paste it directly into YouTube Studio Community tab. Do **not** try to open YouTube Studio — the user will navigate there manually.

**Note:** OAuth scope `youtube.force-ssl` is required for posting comments. If authentication fails, delete `.youtube_credentials.json` and re-authenticate.

### AMV Step 15: Reply to Comments — run at the end of EVERY video pipeline

**Always run this step after publishing** (main video + companion Short). Scans the entire channel for unreplied comments, not just recent videos.

```bash
# Dry-run first — review generated replies
python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q

# Post the replies
python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q --post
```

Do NOT use `--recent-videos` — always scan all channel videos so older comments are never missed.

Other options:
```bash
# Limit to a specific video
python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q --video-id {video_id} --post
```

- Replies are generated by Claude Haiku in English, regardless of comment language
- Validates comments: skips spam, very short comments, and already-replied threads
- Tracks replied comment IDs in `output/replied_comments.json` to avoid duplicates across runs
- Default processes up to 20 comments per run (`--max-comments N` to change)
- Always run dry-run first, review the generated replies, then re-run with `--post`

---

When generating the script, produce this exact JSON structure:

```json
{
  "title": "Compelling YouTube title (max 100 chars)",
  "description": "YouTube video description with relevant keywords",
  "tags": ["tag1", "tag2", "tag3"],
  "content_type": "anime | amv",
  "target_duration_seconds": 60,
  "scenes": [
    {
      "scene_number": 1,
      "scene_type": "intro | normal | rank_transition",
      "rank": 5,
      "name": "Anime Title",
      "amv": 1,
      "clip_index": 3,
      "duration_seconds": 8.0,
      "visual_prompt": "Detailed scene description for image/clip search",
      "narration_text": "Text spoken aloud during this scene",
      "transition": "fade | cut | dissolve",
      "search_tags": "sakugabooru tags — only used for content_type 'anime' with local frames"
    }
  ]
}
```

- `scene_type`: `"intro"` (opening scene), `"normal"` (default), `"rank_transition"` (animated rank reveal)
- `rank`: integer, used on `rank_transition` scenes and on character scenes to indicate which rank is being narrated
- `name`: **required on `rank_transition` scenes** — the anime title to display on the rank card (e.g., `"Jujutsu Kaisen"`). The compositor renders it above the gold rank number.
- `amv`: integer (1–N), used in multi-AMV videos to route this scene's clips to the correct `amvN/frames/` pool
- `clip_index`: 0-based index into the sorted list of available clips for that AMV. **Do NOT use by default** — omit it and let the compositor cycle clips in sequence. Only assign when the user explicitly requests a specific clip for a specific scene.
- All fields except `scene_number`, `duration_seconds`, `narration_text` are optional

### The `search_tags` field
Only used when working with a local frame library. For AMV content, **omit `search_tags`** — frames are already extracted from the AMV.

---

## Script Generation Guidelines

### Tone — Conversational & Genuine (applies to ALL scripts)
Write narration like a knowledgeable friend talking to another anime fan — not a hype announcer, not a Wikipedia summary. Study these real examples:

- **Reframe before explaining**: "Darker than Black is basically what if superpowers came with the world's dumbest side effects." — pitch the show from an unexpected angle first.
- **Describe characters by behavior, not power**: "Ashaf, the calmest guy ever, and bro, he's smoking in almost every episode. Something crazy happens. He lights up." — not "Ashaf is an incredibly powerful mage."
- **Embed personal reactions**: "She smiles so big you kind of forget to question it." — the narrator has a personality, not just information.
- **Mix sentence lengths**: Long descriptive sentences followed by short punchy reactions. Not fragments the whole time.
- **Specific vivid details**: What a character does, how they move, their habits. Never generic traits.
- **Casual language when it fits**: "bro", "yeah", "nope", "kind of", "straight up" — sounds human, not scripted.
- **No ALL CAPS**: Stress comes from word choice and rhythm, not capitalization.
- **No superlatives**: Never "the most BROKEN", "absolute GOAT", "CHANGES EVERYTHING".
- **No filler openers**: Never "Today we look at...", "In this video...", "Let's count down...".
- **End on the character, not a comparison**: Close each rank by saying what makes them memorable — never "but that's why they're only rank N".

### For AMV:
- Scene durations are a starting point — the compositor auto-extends scenes to fit TTS audio
- Do NOT generate `search_tags` — frames are already split and in `frames/`
- rank_transition scenes MUST have short narration_text (e.g., `"Number five."`) for rank card sync

#### Ranking videos (Top N) — required structure
When the topic is a ranking (Top 5, Top 10, etc.), always generate scenes in this order.

**Target duration: ~5 minutes (280–320s).** Ranking videos should be deep and engaging, not rushed. Use longer narration per rank to build storytelling depth. The intro block (scenes 1–3) must be especially compelling to maximize viewer retention.

```
Scene 1:    scene_type="intro",           ~12s, open with a personal reaction or vivid image that sets the mood — NOT a bold claim, amv=<varied>
Scene 2:    scene_type="normal",          ~10s, brief context on why this ranking is worth watching, pivot into the countdown, amv=<varied>

For each rank from N down to 1:
  Scene X:    scene_type="rank_transition", ~2.5s, rank=N, name="<rank label>", amv=N, narration_text="Number N."
  Scene X+1:  scene_type="normal",          ~20s,  rank=N, amv=N, reframe the character from an unexpected angle + who they are through behavior and personality, include one specific vivid detail
  Scene X+2:  scene_type="normal",          ~18s,  rank=N, amv=N, their defining moment or key storyline narrated in present tense with sensory detail — make the viewer feel the scene
  Scene X+3:  scene_type="normal",          ~12s,  rank=N, amv=N, what makes this character/moment memorable on its own terms. End on the character — never compare to the next rank.

Last scene: scene_type="normal", ~18s, outro — personal take on the list + genuine debate question (CTA overlay auto-added by compositor), amv=<any>
```

**Intro retention rule**: Scene 1 must open with a personal reaction or vivid image that hooks the viewer — something relatable or surprising, not a bold claim about rank 1. Scene 2 gives a genuine reason to keep watching. The tone is a friend recommending something, not a countdown announcement.

**3 normal scenes per rank**: Each rank gets intro + analysis + "what sets them apart" scenes so the narration has real depth. Never compress to 2 scenes unless the user explicitly asks for a shorter video.

**Multi-AMV intro/hook**: For intro and hook scenes, assign `amv` values that span multiple different series (e.g., `amv=4` for intro, `amv=2` for scene 2) to give visual variety before the ranking begins. Avoid using `amv=1` for both.

**Last scene duration**: After voice generation, check the actual TTS duration for the last scene and set `duration_seconds` to exactly that value. No buffer needed.

**`name` field on rank transitions**: Always include `"name"` on every `rank_transition` scene. The compositor renders this label above the gold rank number on the black card. **Pick the label by ranking type:**
- **Fight ranking** (Top 5 fights, best battles, etc.) → `"Fighter A vs Fighter B"` (both combatants — e.g. `"Luffy vs Kaido"`, `"Zoro vs Mihawk"`)
- **Character ranking** (Top 5 villains, strongest characters) → character name only (e.g. `"Kaido"`, `"Eren"`)
- **Anime / arc ranking** (Top 5 anime of all time, best arcs) → series or arc title (e.g. `"Demon Slayer"`, `"Marineford Arc"`)

**Rank transition narration sync**: Every `rank_transition` scene MUST have a short `narration_text` (e.g., `"Number five."`, `"Number one."`) so the rank card reveal syncs with the audio announcement. The compositor holds the rank card until TTS finishes.

**`amv` field on rank transitions**: In multi-AMV ranking videos, every `rank_transition` MUST include `"amv": N` matching the rank's AMV (e.g. rank #5 from amv=2 → the rank card has `amv=2`). The compositor uses this to extract the blurred background frame from the correct AMV. Without it, all rank cards fall back to the same global frame and look identical.

**No arc/location announcement after rank cards**: Do NOT open the post-rank-card narration with the arc or location name (e.g. avoid "East Blue. Roronoa Zoro versus Dracule Mihawk."). Go straight into the matchup ("Roronoa Zoro versus Dracule Mihawk."). The arc/location can be woven into the body of the narration if relevant, but never as a standalone opening sentence.

**Per-rank `search_tags` rule**: Every normal scene narrating a character MUST use that character's series-specific tags. All scenes within the same rank must share the same series tags. Examples:
- Rank about Alucard (Hellsing) → `hellsing animated` for all scenes in that rank
- Rank about Saitama (One Punch Man) → `one-punch_man effects` for all scenes in that rank
- Rank about Goku (Dragon Ball) → `dragon_ball_super effects` for all scenes in that rank

---

## Content Strategy

### AMV Videos (main workflow)
- Use YouTube AMVs as background (yt-dlp download)
- Script scenes align with the AMV's natural cut points
- Heavy narration overlay on top of AMV visual
- Accept Content ID claims (not strikes)
- Topics: power rankings, character analysis, lore, "what if" scenarios

---

## Companion Shorts — Default After Every Video

After the main video is approved and published, **always** offer a companion Short with ready-to-pick topic suggestions drawn from the AMVs already downloaded for that video.

There are three Short formats available:

| Format | Slug | What it is | Best for |
|--------|------|-----------|----------|
| **Curiosidade** | `curiosity` | Surprising fact about an anime/character | Lore-heavy anime |
| **Iconic Moment Recap** | `recap` | One iconic scene narrated with context | Emotionally strong moments |
| **Hidden Detail** | `detail` | Overlooked detail / foreshadowing reveal | Any anime |

### How to offer the Short

Do NOT just ask "which format do you want?" — come with concrete topic suggestions already written. For each AMV used in the main video, propose 1–2 specific Short topics (one per format, choosing the best fit for that footage). Format:

> "Quer fazer um Short? Aqui estão algumas sugestões usando os AMVs que já temos:
>
> **Curiosidade**
> - *"Vegeta nunca treinou para superar Goku — ele treinou para provar que Goku estava errado"* (amv1 — Vegeta vs Beerus)
> - *"Gohan foi planejado para ser o protagonista permanente após a saga Cell — Toriyama mudou de ideia"* (amv5 — Gohan SSJ2)
>
> **Recap**
> - *"A transformação SSJ2 do Gohan — o momento que redefiniu Dragon Ball"* (amv5 — Gohan SSJ2)
>
> **Hidden Detail**
> - *"O detalhe que ninguém percebeu na transformação Ultra Instinct do Goku"* (amv4 — Ultra Instinct)
>
> Qual você prefere? Ou quer um tema diferente?"

Once the user picks a topic, immediately run `generate_script.py --short`:
```bash
python scripts/generate_script.py \
  --output-dir "{output_dir}" \
  --topic "{chosen topic}" \
  --short {curiosity|recap|detail} \
  --anime {anime-slug} \
  --amv {N}
```
- `--amv N` locks all scenes to `amv=N` (the AMV the topic is based on) — always include it for Shorts
- Output: `{output_dir}/script/script_{format}_{anime}.json`
- Show the script summary and wait for approval before proceeding

**No inline script generation** — always use `generate_script.py --short`. Never write the Short script manually in the conversation.

---

### Short Script Quality Rules (applies to ALL formats)

These rules override the generic script guidelines for any Short (vertical, `--shorts`):

**Hook rule — 0–2 second claim:**
- Scene 1 must land the main claim by second 2. No setup, no context, no "today we'll talk about".
- Use bold, specific, and falsifiable statements: *"Este personagem foi planejado para morrer no episódio 1."*
- Never open with a question — open with a statement that forces the viewer to think "wait, really?"

**5-beat structure (all Short formats):**
```
Beat 1 — CLAIM     (~3s):  One bold, surprising statement. The hook.
Beat 2 — CONFLICT  (~8s):  The context that makes the claim surprising or meaningful.
Beat 3 — REVEAL    (~15s): The actual information — the fact, the moment, the detail.
Beat 4 — IMPACT    (~10s): Why this matters. What it changes. What the fan community doesn't realize.
Beat 5 — CTA       (~5s):  Direct question to the viewer ("Você sabia disso? Comenta aí!")
```
Total: 40–55s. No narration during scene 1 transitions if the visual does the work.

**Pacing:**
- Narration must be fast-paced and energetic — no long pauses between sentences
- Each beat should feel like it's escalating
- CTA must be a genuine question that invites debate (not "like and subscribe")

---

### AMV Decision Checkpoint

Before running `generate_script.py --short`, confirm which frames to use:
- **Use existing frames** → proceed directly (script's `amv` field points to existing `amvN/frames/`)
- **New AMV** (user provides URL) → download and analyze first:
  ```bash
  python scripts/fetch_amv.py --url "{new_amv_url}" --output-dir "{output_dir}/amv_short"
  python scripts/analyze_amv.py --amv-path "{output_dir}/amv_short/amv/amv_source.mp4" --output-dir "{output_dir}/amv_short"
  ```
  Then use `--frames-dir "{output_dir}/amv_short/frames"` and `--amv-base-dir "{output_dir}/amv_short"` in the compose step.

### Short Pre-Step: Check Existing Channel Videos

Before writing any Short script, fetch the channel's recent uploads and check for topic overlap:

```python
youtube.search().list(
    channelId="UCyRJuLu9xr7mrRh-j52RQ9Q",
    type="video",
    order="date",
    maxResults=50
)
```

Scan titles and descriptions. Do **not** generate a script about a topic already covered on the channel. If overlap is found, propose an alternative angle or different anime.

### Caption Color Selection

Before generating captions, choose `--color` based on the anime's mood:
- Action/fighting → `yellow` or `orange`
- Dramatic/emotional → `white`
- Sci-fi/futuristic → `cyan`
- Horror/dark → `red`
- Default → `yellow`

### Curiosidade Step 1: Generate script
Run `generate_script.py --short curiosity` with the chosen topic:
```bash
python scripts/generate_script.py \
  --output-dir "{output_dir}" \
  --topic "{chosen topic hook}" \
  --short curiosity \
  --anime {anime-slug}
```
Output: `{output_dir}/script/script_curiosity_{anime}.json`
- Title must contain `#Shorts` (generated automatically)
- Show the script summary and wait for user approval before proceeding

### Curiosidade Step 2: Generate Short Cover
```bash
python scripts/generate_thumbnail.py \
    --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
    --output-dir "{output_dir}" \
    --shorts
```
Output: `{output_dir}/thumbnail/cover.jpg` (1080x1920 JPEG). Can run in parallel with voice generation.

### Curiosidade Step 3: Generate Voice (with timestamps)
```bash
python scripts/generate_voice.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --output-dir "{output_dir}/short_curiosity_{anime}" \
  --timestamps
```

### Curiosidade Step 4: Generate Kinetic Captions
```bash
python scripts/generate_captions.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --audio-dir "{output_dir}/short_curiosity_{anime}/audio" \
  --output-dir "{output_dir}/short_curiosity_{anime}" \
  --shorts \
  --color {chosen_color}
```
Choose `--color` based on the anime mood (see color selection guide above). Default: `yellow`.

### Curiosidade Step 5: Compose Short
```bash
python scripts/compose_video.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --frames-dir "{output_dir}/amvN/frames" \
  --audio-dir "{output_dir}/short_curiosity_{anime}/audio" \
  --output-dir "{output_dir}/short_curiosity_{anime}" \
  --bgm-path "{output_dir}/audio/bgm.mp3" \
  --bgm-volume 0.15 \
  --shorts \
  --amv-base-dir "{output_dir}" \
  --endcard-path "channels/hakase-anime/assets/endcard.png" \
  --endcard-duration 10 \
  --captions-path "{output_dir}/short_curiosity_{anime}/audio/captions.ass"
```

> **`--zoom-crop` is opt-in only** — add it only if explicitly requested for this Short.

### Curiosidade Step 6: Publish to YouTube
```bash
python scripts/publish_youtube.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --video-path "{output_dir}/short_curiosity_{anime}/final/final_short.mp4" \
  --thumbnail-path "{output_dir}/thumbnail/cover.jpg" \
  --privacy "public" \
  --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

### Curiosidade Step 7: Publish to TikTok
After YouTube upload succeeds, publish the same video to TikTok (requires credentials):
```bash
python scripts/publish_tiktok.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --video-path "{output_dir}/short_curiosity_{anime}/final/final_short.mp4" \
  --privacy SELF_ONLY
```
- Default privacy is `SELF_ONLY` (private) for manual review — user changes to public in TikTok Studio
- First-time setup: run `python scripts/publish_tiktok.py --check-auth` to complete OAuth
- TikTok credentials saved at `.tiktok_credentials.json` (gitignored)
- If `TIKTOK_CLIENT_KEY` is missing from `.env`, skip this step and remind the user to configure it

---

## Iconic Moment Recap Short

A Short (40–55s) narrating a single iconic scene: the context, the moment itself, and its lasting impact.

**When to use:** User asks for a recap of a specific scene, fight, or arc moment.

### Recap Script: generate via generate_script.py
```bash
python scripts/generate_script.py \
  --output-dir "{output_dir}" \
  --topic "{chosen topic hook}" \
  --short recap \
  --anime {anime-slug}
```
Output: `{output_dir}/script/script_recap_{anime}.json`
- Title must contain `#Shorts`
- Show the script summary and wait for user approval before proceeding

### Recap Pipeline
Same steps as Curiosidade (Steps 2–7 above), with these filename substitutions:
- Script: `script_recap_{anime_slug}.json`
- Output dir: `{output_dir}/short_recap_{anime_slug}/`
- Final video: `{output_dir}/short_recap_{anime_slug}/final/final_short.mp4`
- Cover thumbnail: `{output_dir}/thumbnail/cover.jpg` (generated in Step 2 with `--shorts`)

---

## Hidden Detail Short

A Short (40–55s) revealing a detail, foreshadowing, or easter egg most viewers missed.

**When to use:** User asks for a "detalhe que ninguém viu" or foreshadowing Short.

### Hidden Detail Script: generate via generate_script.py
```bash
python scripts/generate_script.py \
  --output-dir "{output_dir}" \
  --topic "{chosen topic hook}" \
  --short detail \
  --anime {anime-slug}
```
Output: `{output_dir}/script/script_detail_{anime}.json`
- Title must contain `#Shorts` and a hook like "O detalhe que NINGUÉM viu em {anime}"
- Show the script summary and wait for user approval before proceeding

### Hidden Detail Pipeline
Same steps as Curiosidade (Steps 2–7 above), with these filename substitutions:
- Script: `script_detail_{anime_slug}.json`
- Output dir: `{output_dir}/short_detail_{anime_slug}/`
- Final video: `{output_dir}/short_detail_{anime_slug}/final/final_short.mp4`
- Cover thumbnail: `{output_dir}/thumbnail/cover.jpg` (generated in Step 2 with `--shorts`)

---

## Rules
- **Output folder naming**: always use `YYYYMMDD-{slug}` format (e.g. `20260603-top5-db-villains`). Date prefix first so folders sort chronologically. Never put the date at the end.
- Scene durations must sum to target_duration_seconds (±5s for short videos; ±5% for long videos)
- Minimum 5 scenes, maximum 60 scenes
- First scene must hook the viewer
- Always show the user the script before proceeding
- Report progress after each step completes
- If a step fails, inform the user and offer to retry or skip
- For anime content: accept that Content ID claims may occur (not strikes)
- **NEVER cut narration** — if TTS is longer than scene duration, the compositor extends the scene automatically
- **ALWAYS include end card** — endcard is auto-detected per channel from `channels/{channel-slug}/assets/endcard.png`. Pass `--endcard-duration 10` to `compose_video.py` (use `--no-endcard` only if explicitly requested)
- **ALWAYS sync rank card with audio** — rank_transition scenes must have narration_text so the card reveal syncs with the spoken announcement
- **BGM: Freesound CC0 first** — use `--query` flag with `fetch_bgm.py` (CC0 license, zero Content ID claims). Fall back to `--search` (YouTube) only if Freesound returns nothing.
- **Zoom-crop is opt-in** — never pass `--zoom-crop` to `compose_video.py` by default. Only add it when the user explicitly requests it at AMV URL submission time.
- **Shorts cover is mandatory** — always run `generate_thumbnail.py --shorts` before voice generation for every Short. Output is `cover.jpg` (1080x1920). Use it as `--thumbnail-path` when publishing the Short to YouTube.
- **Dramatic/hype tone** — all scripts (main video and Shorts) must use the tone guidelines in the Script Generation section: short punchy sentences, superlatives, present-tense action, no filler openers.
- **TikTok after every Short** — after publishing a Short to YouTube, always offer to publish to TikTok. Skip if `TIKTOK_CLIENT_KEY` is missing from `.env`.
- **TikTok privacy default** — always use `--privacy SELF_ONLY` for TikTok (user reviews and publishes manually in TikTok Studio).

## Environment
- Ensure `.env` is configured with API keys before running agent scripts
- FFmpeg must be installed and available in PATH
- Output goes to `output/` directory (gitignored)
- State tracked in `state.json`
