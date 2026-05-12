# YouTube Video Generator Squad

## Role
You (Claude) are the **orchestrator** of this multi-agent pipeline. You generate the video scripts directly (you ARE the LLM) and trigger each agent's Python script in sequence, managing checkpoints and state.

## How to Run a Video Generation

For **anime content**, the **AMV Workflow** is the default. Ask the user for a YouTube AMV URL unless they explicitly want to use Sakugabooru clips instead.

---

### Step 1: Script Generation (YOU do this directly)
1. Ask the user for the **topic** and **content type** (anime, bedtime-story, or amv) if not provided
2. Generate a `script.json` following the schema below
3. Write it to `output/{topic}-{timestamp}/script/script.json`
4. Show the script summary to the user for review

### Step 2: CHECKPOINT — Approve Script
- Present: title, number of scenes, total duration, scene list
- Wait for user approval before proceeding
- User can request changes — regenerate if needed

### Step 3: Fetch Anime Frames/Clips
For **anime content** using real frames:
```bash
python scripts/fetch_frames.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```
This searches Sakugabooru for clips matching each scene's visual description.

For **AI-generated images** (bedtime stories or when preferred):
```bash
python scripts/generate_images.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```

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
```bash
python scripts/fetch_bgm.py --search "{bgm_query}" --output-dir "{output_dir}"
```
This searches YouTube and downloads the top result audio.

**BGM query selection guidelines:**
- Anime action/fighting → `"epic anime orchestra action no copyright"`
- Anime emotional/dramatic → `"emotional anime piano orchestral no copyright"`
- Dragon Ball / power ranking → `"epic dragon ball orchestra no copyright"`
- Naruto → `"naruto epic orchestral no copyright"`
- Demon Slayer → `"demon slayer kimetsu orchestral no copyright"`
- Bedtime story → `"gentle lullaby soft piano children no copyright"`
- General anime → `"epic anime cinematic orchestra no copyright"`

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
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --privacy "private" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

---

## AMV Workflow (YouTube AMV as background)

Use this workflow when the user wants to create an anime video. The full pipeline from trend research to publish.

### AMV Step 1: Trend Research
Run both commands to understand the current landscape:
```bash
python scripts/analyze_trends.py --queries "anime power ranking" "top anime 2026" "hidden gem anime" --days 30 --output-file output/trends_cache.json
```
```bash
python scripts/analyze_channel.py --days 90 --output-file output/channel_analytics.json --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q
```
Read both output files. Use trends to find underserved topics (high views, few recent competitors). Use channel analytics to double-down on formats similar to top-performing videos.

### AMV Step 2: CHECKPOINT — Suggest Themes
- Propose 3–5 topic options based on trend + channel data
- **Wait for user to pick a theme**
- Once theme is chosen, tell the user exactly what AMV(s) to search for on YouTube (one per rank for Top N videos, with suggested search queries)
- **Wait for user to return with AMV URL(s)** before proceeding

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

### AMV Step 6: CHECKPOINT — Show AMV Analysis
- Read all `amv_analysis.json` files
- Present: total duration, number of scenes, brief description of each scene per AMV
- Ask the user for the **video topic/angle** (e.g., "narrate this as a One Piece power ranking")
- Wait for user confirmation before generating the script

### AMV Step 7: Generate Script from AMV Analysis (YOU do this)
Read the analysis file(s) and generate `script.json`. For **multi-AMV**:
- Use the `amv` field (1–N) to route each scene to the correct AMV's clip pool
- Scene durations should match the content rhythm (not necessarily the raw clip durations)
- Narration drives the pacing — the compositor extends scenes to fit TTS audio
- **Optionally** assign `clip_index` to pin specific clips to scenes for precise editing

Write to `{output_dir}/script/script.json` and show the script summary.

For **single AMV**, scene structure follows the analysis:
- `duration_seconds` per scene ≈ clip durations from analysis (compositor auto-extends for TTS)
- `content_type` = `"amv"`
- Omit `search_tags` — frames are already in `frames/`

### AMV Step 8: CHECKPOINT — Approve Script
- Present: title, number of scenes, total duration, narration preview
- User can request tone/topic changes — regenerate narration if needed

### AMV Step 9: Generate Voice Narration
```bash
python scripts/generate_voice.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```

### AMV Step 10: Fetch BGM (YouTube only)
```bash
python scripts/fetch_bgm.py --search "{bgm_query}" --output-dir "{output_dir}"
```
Use the BGM query guidelines from the standard workflow above. Always use `--search` (YouTube).

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
  --zoom-crop
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
  --zoom-crop \
  --amv-base-dir "{output_dir}"
```

The compositor automatically:
- Routes scenes to `amvN/frames/` based on the `amv` field in script.json
- Uses `clip_index` if specified, otherwise cycles clips in order
- **Never cuts narration** — extends scene duration to fit full TTS audio
- **Always appends end card** (auto-detected from `channels/hakase-anime/assets/endcard.png`)
- Applies `--zoom-crop` (12% scale + crop to remove watermarks)

### AMV Step 12: CHECKPOINT — Approve Video
- Report final video path, duration, file size
- Wait for user approval before publishing

### AMV Step 13: Publish to YouTube
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

3. **Make video public** — call `videos.update` with `status.privacyStatus = "public"`.

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
  "content_type": "anime | bedtime-story | amv",
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
      "search_tags": "sakugabooru tags for this scene (e.g., 'fighting animated naruto')"
    }
  ]
}
```

- `scene_type`: `"intro"` (opening scene), `"normal"` (default), `"rank_transition"` (animated rank reveal)
- `rank`: integer, used on `rank_transition` scenes and on character scenes to indicate which rank is being narrated
- `name`: **required on `rank_transition` scenes** — the anime title to display on the rank card (e.g., `"Jujutsu Kaisen"`). The compositor renders it above the gold rank number.
- `amv`: integer (1–N), used in multi-AMV videos to route this scene's clips to the correct `amvN/frames/` pool
- `clip_index`: 0-based index into the sorted list of available clips for that AMV. Use to pin specific clips to a scene. Wraps via modulo if index exceeds clip count.
- All fields except `scene_number`, `duration_seconds`, `narration_text` are optional

### The `search_tags` field
When content_type is "anime", include Sakugabooru-compatible tags for each scene.
When content_type is "amv", **omit `search_tags`** — frames are already extracted from the AMV.

**IMPORTANT — Sakugabooru tag conventions (only these work):**
- Series names (NOT character names): `naruto`, `dragon_ball`, `dragon_ball_super`, `hellsing`, `one-punch_man` (note hyphen-underscore), `demon_slayer`, `jujutsu_kaisen`, `one_piece`, `bleach`, `attack_on_titan`, `fullmetal_alchemist`
- Action tags: `fighting`, `running`, `effects`, `explosions`, `smears`
- Character names only rarely work: `saitama` works; most others like `goku`, `madara`, `alucard` do NOT
- Combine 2-3 tags max: `naruto fighting`, `dragon_ball_super effects`, `hellsing animated`
- When no specific series fits, use: `fighting animated`, `effects animated`, `explosions`

---

## Script Generation Guidelines

### For AMV:
- Narration must match the real visual content of each AMV segment (use the `description` from `amv_analysis.json`)
- Scene durations are a starting point — the compositor auto-extends scenes to fit TTS audio
- Write engaging commentary: power rankings, character analysis, "what if" scenarios, storytelling
- Match narration energy to the scene's mood (intense = fast-paced, emotional = slower)
- Do NOT generate `search_tags` — frames are already split and in `frames/`
- rank_transition scenes MUST have short narration_text (e.g., `"Number five."`) for rank card sync

### For Anime:
- Dramatic, cinematic narratives with strong visual hooks
- Narration should be engaging like a storyteller/narrator
- Visual prompts should describe the ACTION and MOOD (for clip search)
- Include `search_tags` with Sakugabooru-compatible tags per scene
- Think about pacing: action scenes = shorter clips, emotional = longer holds

#### Ranking videos (Top N) — required structure
When the topic is a ranking (Top 5, Top 10, etc.), always generate scenes in this order:

```
Scene 1:    scene_type="intro",           ~7s,  broad tags ("effects animated fighting"), amv=<varied>
Scene 2:    scene_type="normal",          ~5s,  hook narration introducing the list, broad tags, amv=<varied>

For each rank from N down to 1:
  Scene X:    scene_type="rank_transition", ~2.5s, rank=N, name="<Anime Title>", narration_text="Number N."
  Scene X+1:  scene_type="normal",          ~8s,   rank=N, series-specific tags, amv=N, character intro
  Scene X+2:  scene_type="normal",          ~7s,   rank=N, series-specific tags, amv=N, why they rank here

Last scene: scene_type="normal", ~14s, outro narration (CTA overlay auto-added by compositor), amv=<any>
```

**Multi-AMV intro/hook**: For intro and hook scenes, assign `amv` values that span multiple different series (e.g., `amv=4` for intro, `amv=2` for scene 2) to give visual variety before the ranking begins. Avoid using `amv=1` for both.

**Last scene duration**: Set the last scene's `duration_seconds` to at least the TTS narration length + 2s buffer. A safe default is 14s.

**`name` field on rank transitions**: Always include `"name": "<Anime Title>"` on every `rank_transition` scene. The compositor renders the anime title above the gold rank number on the black card.

**Rank transition narration sync**: Every `rank_transition` scene MUST have a short `narration_text` (e.g., `"Number five."`, `"Number one."`) so the rank card reveal syncs with the audio announcement. The compositor holds the rank card until TTS finishes.

**Per-rank `search_tags` rule**: Every normal scene narrating a character MUST use that character's series-specific tags. All scenes within the same rank must share the same series tags. Examples:
- Rank about Alucard (Hellsing) → `hellsing animated` for all scenes in that rank
- Rank about Saitama (One Punch Man) → `one-punch_man effects` for all scenes in that rank
- Rank about Goku (Dragon Ball) → `dragon_ball_super effects` for all scenes in that rank

### For Bedtime Stories:
- Gentle, calming narratives suitable for ages 3-8
- Soothing narration with repetitive comforting phrases
- Uses AI-generated images (soft watercolor style) instead of anime frames
- Story should gradually calm toward sleep

---

## Content Strategy

### AMV Videos (alternative workflow)
- Use YouTube AMVs as background (yt-dlp download)
- Script scenes align with the AMV's natural cut points
- Heavy narration overlay on top of AMV visual
- Accept Content ID claims (not strikes) — same as anime workflow
- Topics: power rankings, character analysis, lore, "what if" scenarios

### Anime Videos (main content)
- Use real anime clips from Sakugabooru (accepts Content ID claims)
- Heavy narration overlay (transformative content)
- Ken Burns/zoom effects on frames
- Topics: anime lore, character stories, "what if" scenarios, power rankings

### Bedtime Stories (secondary content)
- 100% AI-generated images (no copyright issues, monetizable)
- Soft narration, calming music
- Topics: gentle adventures, magical creatures, nature stories

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
  --zoom-crop \
  --shorts \
  --amv-base-dir "{output_dir}" \
  --captions-path "{output_dir}/short_curiosity_{anime}/audio/captions.ass"
```

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

## Rules
- Scene durations must sum to target_duration_seconds (±5s)
- Minimum 5 scenes, maximum 20 scenes
- First scene must hook the viewer
- Always show the user the script before proceeding
- Report progress after each step completes
- If a step fails, inform the user and offer to retry or skip
- For anime content: accept that Content ID claims may occur (not strikes)
- **NEVER cut narration** — if TTS is longer than scene duration, the compositor extends the scene automatically
- **ALWAYS include end card** — auto-detected from `channels/hakase-anime/assets/endcard.png` (use `--no-endcard` only if explicitly requested)
- **ALWAYS sync rank card with audio** — rank_transition scenes must have narration_text so the card reveal syncs with the spoken announcement
- **BGM from YouTube only** — always use `--search` flag with `fetch_bgm.py`, never `--query` (Freesound deprecated)

## Environment
- Ensure `.env` is configured with API keys before running agent scripts
- FFmpeg must be installed and available in PATH
- Output goes to `output/` directory (gitignored)
- State tracked in `state.json`
