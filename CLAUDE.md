# YouTube Video Generator Squad

## Role
You (Claude) are the **orchestrator** of this multi-agent pipeline. You generate the video scripts directly (you ARE the LLM) and trigger each agent's Python script in sequence, managing checkpoints and state.

## How to Run a Video Generation

For **anime content**, the **AMV Workflow** is the default. Ask the user for a YouTube AMV URL.

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

The user can also provide a local folder of frames:
```bash
python scripts/fetch_frames.py --source local --local-dir "/path/to/frames" --output-dir "{output_dir}"
```

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
If the user specifies a date/time, always use `--publish-at` (schedules automatically — no `--privacy` needed):
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --publish-at "YYYY-MM-DD HH:MM" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```
Otherwise publish as private for manual review:
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --privacy "private" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
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
The trends script prints a **Top 10 Trending** table (with anime + format detected) and a **Suggested Topics** section automatically. Use the suggestions as the basis for AMV Step 2.

### AMV Step 2: CHECKPOINT — Suggest Themes + Generate Draft Script
- Propose 3–5 topic options based on trend + channel data
- **Wait for user to pick a theme**
- Once theme is chosen, **generate the full draft script immediately** (YOU do this, same rules as AMV Step 7 below, but without AMV analysis — write the narration based on your knowledge of the anime/characters/topic)
- Show the script summary (title, scene list, narration preview)
- For each rank, summarize in 1–2 sentences what the narration says and what visual moments would best illustrate it (e.g., "Rank 5 – Orochimaru: narration covers his immortality experiments and Sannin history. Best clips: Orochimaru vs Hiruzen, cursed mark application, snake summoning")
- **Wait for user to return with AMV URL(s)** — the per-rank visual hints help them pick the right AMV

The draft script may be lightly revised after AMV analysis (AMV Step 6) to align `visual_prompt` fields with what the AMVs actually show, but the narration should stay largely unchanged.

### AMV Step 3: Download AMV(s)
**Single AMV:**
```bash
python scripts/fetch_amv.py --url "{youtube_url}" --output-dir "{output_dir}"
```
Creates: `{output_dir}/amv/amv_source.mp4` and `amv/amv_metadata.json`

**Multi-AMV (Top N videos):** download each into its own subdirectory:
```bash
python scripts/fetch_amv.py --url "{amv1_url}" --output-dir "{output_dir}/amv1"
python scripts/fetch_amv.py --url "{amv2_url}" --output-dir "{output_dir}/amv2"
# ...one per rank
```

### AMV Step 4: Analyze AMV(s)
**Single AMV:**
```bash
python scripts/analyze_amv.py --amv-path "{output_dir}/amv/amv_source.mp4" --output-dir "{output_dir}"
```
- Detects natural scene cuts via ffmpeg
- Extracts a keyframe per scene
- Describes each scene using Claude Vision (Haiku)
- Splits the AMV into `frames/scene_01.mp4`, `frames/scene_02.mp4`, etc.
- Creates: `{output_dir}/amv/amv_analysis.json`

**Multi-AMV:** analyze each in parallel:
```bash
python scripts/analyze_amv.py --amv-path "{output_dir}/amv1/amv/amv_source.mp4" --output-dir "{output_dir}/amv1"
python scripts/analyze_amv.py --amv-path "{output_dir}/amv2/amv/amv_source.mp4" --output-dir "{output_dir}/amv2"
# ...one per AMV
```

Optional flags: `--max-scenes 12` (default), `--min-scene-duration 3.0` (default, seconds)

### AMV Step 5: CHECKPOINT — Review Clips
- Tell the user to open each `amvN/frames/` folder and watch the clips
- User deletes any clips they don't want used in the video
- **Wait for user confirmation** before proceeding to script generation
- After confirmation, list how many clips remain per AMV so the user can verify

### AMV Step 6: CHECKPOINT — Review AMV Analysis & Align Script
- Read all `amv_analysis.json` files
- Present: total duration, number of scenes, brief description of each scene per AMV
- Compare the AMV clip descriptions against the draft script's `visual_prompt` fields
- If a scene's `visual_prompt` doesn't match what the clips actually show, update it to reflect reality
- Narration text stays unchanged unless the user requests a tone/topic change
- Ask the user to confirm before proceeding to voice generation

### AMV Step 7: Revise Script if Needed (YOU do this)
If the AMV analysis revealed significant mismatches between the draft script and the available clips, update `script.json`:
- Use the `amv` field (1–N) to route each scene to the correct AMV's clip pool
- Scene durations should match the content rhythm (not necessarily the raw clip durations)
- Narration drives the pacing — the compositor extends scenes to fit TTS audio
- **Never assign `clip_index`** — omit it so clips cycle in sequence. Only use if user explicitly requests a specific clip.

Write to `{output_dir}/script/script.json` and show the script summary.

**Claude generates the script directly — do NOT spawn a subagent for script generation.** Read the AMV analyses and write the script in the conversation.

**No artificial duration cap** — set `target_duration_seconds` to reflect natural pacing (e.g., ~140–160s for a Top 5 ranking). Never force the video into a short format. Always use 2 normal scenes per rank.

For **single AMV**, scene structure follows the analysis:
- `duration_seconds` per scene ≈ clip durations from analysis (compositor auto-extends for TTS)
- `content_type` = `"amv"`
- Omit `search_tags` — frames are already in `frames/`

### AMV Step 8: CHECKPOINT — Approve Script
- Present: title, number of scenes, total duration, narration preview
- User can request tone/topic changes — regenerate narration if needed

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
If the user specifies a date/time, always use `--publish-at` (schedules automatically — no `--privacy` needed):
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --publish-at "YYYY-MM-DD HH:MM" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```
Otherwise publish as private for manual review:
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --privacy "private" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

### AMV Step 14: Post-Publish Steps
After the video is uploaded (still private), do all of these before making it public:

1. **Update description with chapters** — add YouTube chapter timestamps so the progress bar shows named segments:
   ```
   0:00 Intro
   0:15 #5 — [Anime Name]
   0:35 #4 — [Anime Name]
   ...
   ```
   Use the cumulative scene durations from `script.json` to calculate timestamps. Also add hashtags at the end of the description (e.g., `#anime #animerecommendations`).

2. **Update tags** — use the YouTube Data API `videos.update` to push comprehensive tags (series names, year, genre keywords).

3. **Make video public** — only needed if published as `--privacy "private"`. If `--publish-at` was used, the video goes public automatically at the scheduled time — skip this step.

4. **Post engagement comment** — use `commentThreads.insert` to post a pinned comment in English asking viewers to engage (e.g., "Which anime from this list is your favorite? Drop it in the comments! 👇"). Then ask the user to go to YouTube Studio and pin it, as the API cannot pin comments directly.

5. **Generate community post** — run the community post generator and open YouTube Studio:
   ```bash
   python scripts/post_community.py \
     --script-path "{output_dir}/script/script.json" \
     --video-id "{video_id}" \
     --output-dir "{output_dir}" \
     --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
   ```
   This generates an English community post with a poll, prints the text to console, and opens YouTube Studio Community tab. Copy the `post_text` and create the poll manually — the API cannot create community posts directly.

**Note:** OAuth scope `youtube.force-ssl` is required for posting comments. If authentication fails, delete `.youtube_credentials.json` and re-authenticate.

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

### For AMV:
- Narration must match the real visual content of each AMV segment (use the `description` from `amv_analysis.json`)
- Scene durations are a starting point — the compositor auto-extends scenes to fit TTS audio
- Write engaging commentary: power rankings, character analysis, "what if" scenarios, storytelling
- Match narration energy to the scene's mood (intense = fast-paced, emotional = slower)
- Do NOT generate `search_tags` — frames are already split and in `frames/`
- rank_transition scenes MUST have short narration_text (e.g., `"Number five."`) for rank card sync

#### Ranking videos (Top N) — required structure
When the topic is a ranking (Top 5, Top 10, etc.), always generate scenes in this order:

```
Scene 1:    scene_type="intro",           ~7s,  broad tags ("effects animated fighting"), amv=<varied>
Scene 2:    scene_type="normal",          ~5s,  hook narration introducing the list, broad tags, amv=<varied>

For each rank from N down to 1:
  Scene X:    scene_type="rank_transition", ~2.5s, rank=N, name="<rank label>", amv=N, narration_text="Number N."
  Scene X+1:  scene_type="normal",          ~8s,   rank=N, series-specific tags, amv=N, character intro
  Scene X+2:  scene_type="normal",          ~7s,   rank=N, series-specific tags, amv=N, why they rank here

Last scene: scene_type="normal", ~14s, outro narration (CTA overlay auto-added by compositor), amv=<any>
```

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

## Companion Short (Curiosidade) — Default After Every Video

After the main video is approved and published, **always** offer to generate a companion Curiosidade Short — a 40–55s vertical Short about one surprising fact related to one of the anime featured in the main video. This is the standard companion content, not a mini-summary.

### AMV Decision Checkpoint

Before starting, ask the user:
> "Which anime from the main video should the curiosidade Short feature? I can use the existing frames from `amv{N}/frames/`. Would you prefer to use a new AMV for this Short?"

- **Use existing frames** → proceed directly with frames already in `{output_dir}/amvN/frames/`
- **New AMV** (user provides URL) → download and analyze first:
  ```bash
  python scripts/fetch_amv.py --url "{new_amv_url}" --output-dir "{output_dir}/amv_curiosity"
  python scripts/analyze_amv.py --amv-path "{output_dir}/amv_curiosity/amv/amv_source.mp4" --output-dir "{output_dir}/amv_curiosity"
  ```
  Then use `--frames-dir "{output_dir}/amv_curiosity/frames"` and `--amv-base-dir "{output_dir}/amv_curiosity"` in the compose step.

### Curiosidade Pre-Step: Check Existing Channel Videos

Before writing any Curiosidade script, fetch the channel's recent uploads and check for topic overlap:

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

### Curiosidade Step 1: Generate script_curiosity_{anime}.json (YOU do this)
- Write to `{output_dir}/script/script_curiosity_{anime_slug}.json`
- **Structure:** 4–5 scenes, 40–55s total
- **Scene 1** (~5s): hook — one surprising statement about the anime/character
- **Scenes 2–4** (~10s each): explain the curiosidade with details
- **Scene 5** (~5s): outro CTA — ask viewers to comment + follow
- **Same `amv` field** as the main video (pointing to the correct AMV)
- **Title** must contain `#Shorts`
- **No `search_tags`** — frames already extracted
- Pick a genuinely surprising fact (forbidden powers, hidden origins, story backstory, author intent, etc.)

### Curiosidade Step 2: Generate Voice (with timestamps)
```bash
python scripts/generate_voice.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --output-dir "{output_dir}/short_curiosity_{anime}" \
  --timestamps
```

### Curiosidade Step 3: Generate Kinetic Captions
```bash
python scripts/generate_captions.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --audio-dir "{output_dir}/short_curiosity_{anime}/audio" \
  --output-dir "{output_dir}/short_curiosity_{anime}" \
  --shorts \
  --color {chosen_color}
```
Choose `--color` based on the anime mood (see color selection guide above). Default: `yellow`.

### Curiosidade Step 4: Compose Short
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

### Curiosidade Step 5: Publish
```bash
python scripts/publish_youtube.py \
  --script-path "{output_dir}/script/script_curiosity_{anime}.json" \
  --video-path "{output_dir}/short_curiosity_{anime}/final/final_short.mp4" \
  --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" \
  --privacy "public" \
  --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

---

---

## History Workflow (Echoes of History — AI-generated images)

Use this workflow for the **Echoes of History** channel (`content_type: "history"`). Videos are ~40 minutes long, using AI-generated images (no AMV downloads).

### History Step 1: Trend Research
```bash
python scripts/analyze_channel.py --days 90 --output-file output/channel_history.json --channel-id {HISTORY_CHANNEL_ID}
```
```bash
python scripts/analyze_trends.py \
  --queries "history documentary" "ancient civilizations" "world war secrets" "roman empire history" "greatest empires history" "historical mysteries explained" \
  --days 30 \
  --min-duration 300 \
  --channel-cache output/channel_history.json \
  --output-file output/trends_history.json
```

### History Step 2: CHECKPOINT — Suggest Themes
- Read `output/trends_history.json`
- Propose 3–5 topic options (prioritize underserved niches with high views)
- **Wait for user to pick a theme** before generating the script

### History Step 3: Generate Script (YOU do this directly)
Read the trend data and generate `script.json` for the chosen topic.

**Structure for a 40-min documentary (~2400s):**
- Scene 1: `scene_type="intro"`, ~30s — dramatic hook, most gripping moment of the story
- Scenes 2–4: Context (~90s total) — set the stage, time period, geography, key figures
- Main body (~35 min): 30–40 `scene_type="normal"` scenes, 60–90s each — chronological or thematic narrative
- Final 2 scenes: Legacy/conclusion (~60s) + CTA outro (~25s)

**Script rules for history:**
- Narration: documentary style (present tense for drama, vivid sensory details)
- `visual_prompt`: describe a single historically accurate scene for AI image generation (always end with "oil painting style, dramatic chiaroscuro lighting, dark atmospheric")
- Do NOT use `search_tags`, `amv`, `clip_index`, or `rank_transition`
- `content_type` must be `"history"`
- Scene types: `"intro"` (first scene only), `"normal"` (all others)

Write to `{output_dir}/script/script.json`.

### History Step 4: CHECKPOINT — Approve Script
- Present: title, number of scenes, total duration (~40 min), narration preview (first 3 scenes)
- User can request tone/topic adjustments
- Wait for approval before generating images

### History Step 5: Generate Scene Images
```bash
python scripts/generate_scene_images.py \
  --script-path "{output_dir}/script/script.json" \
  --output-dir "{output_dir}" \
  --quality medium
```
- Generates one image per scene using gpt-image-1 via Responses API
- Output: `{output_dir}/frames/scene_01.jpg`, `scene_02.jpg`, etc.
- Estimated cost: ~$1.50–2.00 for 40 scenes (medium quality)
- Can run in parallel with History Step 5b

### History Step 5b: Generate Thumbnail
```bash
python scripts/generate_thumbnail.py \
  --script-path "{output_dir}/script/script.json" \
  --output-dir "{output_dir}"
```
History thumbnails automatically use documentary style (dark atmospheric, oil painting, dramatic lighting).

### History Step 6: Generate Voice Narration
```bash
python scripts/generate_voice.py \
  --script-path "{output_dir}/script/script.json" \
  --output-dir "{output_dir}"
```
Uses `VOICE_ID_HISTORY` from `.env`. A deep, authoritative male voice works best (e.g., ElevenLabs "George" or "Brian").

### History Step 7: Fetch BGM
```bash
python scripts/fetch_bgm.py --query "epic orchestral cinematic documentary" --output-dir "{output_dir}"
```
**BGM query guidelines for history:**
- Ancient civilizations → `"ancient orchestral atmospheric"`
- Wars/battles → `"epic orchestral cinematic"`
- Dark history/crimes → `"dark orchestral suspenseful"`
- General history → `"epic cinematic orchestral documentary"`

### History Step 8: Compose Final Video
```bash
python scripts/compose_video.py \
  --script-path "{output_dir}/script/script.json" \
  --frames-dir "{output_dir}/frames" \
  --audio-dir "{output_dir}/audio" \
  --output-dir "{output_dir}" \
  --bgm-path "{output_dir}/audio/bgm.mp3" \
  --bgm-volume 0.12 \
  --endcard-duration 10
```
- Endcard auto-detected from `channels/echoes-of-history/assets/endcard.png`
- Static images use Ken Burns zoom/pan effect automatically
- BGM volume 0.12 (slightly lower than anime — narration is primary)

### History Step 9: CHECKPOINT — Approve Video
- Report final video path, duration, file size
- Wait for user approval before publishing

### History Step 10: Publish to YouTube
If the user specifies a date/time, always use `--publish-at` (schedules automatically — no `--privacy` needed):
```bash
python scripts/publish_youtube.py \
  --script-path "{output_dir}/script/script.json" \
  --video-path "{output_dir}/final/final_video.mp4" \
  --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" \
  --publish-at "YYYY-MM-DD HH:MM" \
  --channel-id "{HISTORY_CHANNEL_ID}"
```
Otherwise publish as private for manual review:
```bash
python scripts/publish_youtube.py \
  --script-path "{output_dir}/script/script.json" \
  --video-path "{output_dir}/final/final_video.mp4" \
  --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" \
  --privacy "private" \
  --channel-id "{HISTORY_CHANNEL_ID}"
```

### History Step 11: Post-Publish Steps
Same as AMV Step 14:
1. Update description with chapters (use cumulative scene durations to calculate timestamps)
2. Update tags
3. Make video public
4. Post engagement comment (ask viewers which historical era they want next)
5. Generate community post

---

## Rules
- **Output folder naming**: always use `YYYYMMDD-{slug}` format (e.g. `20260603-top5-db-villains`). Date prefix first so folders sort chronologically. Never put the date at the end.
- Scene durations must sum to target_duration_seconds (±5s for short videos; ±5% for long videos)
- Minimum 5 scenes, maximum 60 scenes (history/documentary may use up to 60)
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

## Environment
- Ensure `.env` is configured with API keys before running agent scripts
- FFmpeg must be installed and available in PATH
- Output goes to `output/` directory (gitignored)
- State tracked in `state.json`
