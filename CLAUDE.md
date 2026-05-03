# YouTube Video Generator Squad

## Role
You (Claude) are the **orchestrator** of this multi-agent pipeline. You generate the video scripts directly (you ARE the LLM) and trigger each agent's Python script in sequence, managing checkpoints and state.

## How to Run a Video Generation

When the user asks to generate a video (e.g., "create a video about...", "generate a video on..."), follow this pipeline:

For **anime content**, the **AMV Workflow** is the default. Ask the user for a YouTube AMV URL unless they explicitly want to use Sakugabooru clips instead.

If the user provides a **YouTube AMV URL** (or for anime by default), use the **AMV Workflow** below instead of the standard pipeline.

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
python scripts/fetch_bgm.py --query "{bgm_query}" --output-dir "{output_dir}"
```

**BGM query selection guidelines:**
- Anime action/fighting → `"epic anime orchestra action royalty free"`
- Anime emotional/dramatic → `"emotional anime piano orchestral royalty free"`
- Dragon Ball / power ranking → `"epic dragon ball orchestra royalty free"`
- Naruto → `"naruto epic orchestral royalty free"`
- Demon Slayer → `"demon slayer kimetsu orchestral royalty free"`
- Bedtime story → `"gentle lullaby soft piano children royalty free"`
- General anime → `"epic anime cinematic orchestra royalty free"`

### Step 6: Compose Final Video
```bash
python scripts/compose_video.py --script-path "{output_dir}/script/script.json" --frames-dir "{output_dir}/frames" --audio-dir "{output_dir}/audio" --output-dir "{output_dir}" --bgm-path "{output_dir}/audio/bgm.mp3" --bgm-volume 0.20
```

The compositor handles:
- Video clips (mp4, webm): trims or loops to scene duration
- GIFs: loops to fill duration
- Static images: applies Ken Burns zoom/pan effect
- All clips normalized to 1920x1080 @ 24fps

### Step 6: Generate Thumbnail
```bash
python scripts/generate_thumbnail.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```

### Step 7: CHECKPOINT — Approve Video
- Report final video path, duration, file size
- Wait for user approval before publishing

### Step 8: Publish to YouTube
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --privacy "private" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

---

## AMV Workflow (YouTube AMV as background)

Use this workflow when the user provides a YouTube AMV URL. The pipeline is **inverted**: download and analyze first, then generate a script that fits the AMV's actual scene structure.

### AMV Step 1: Download AMV
```bash
python scripts/fetch_amv.py --url "{youtube_url}" --output-dir "{output_dir}"
```
Creates: `{output_dir}/amv/amv_source.mp4` and `amv/amv_metadata.json`

### AMV Step 2: Analyze AMV
```bash
python scripts/analyze_amv.py --amv-path "{output_dir}/amv/amv_source.mp4" --output-dir "{output_dir}"
```
- Detects natural scene cuts via ffmpeg
- Extracts a keyframe per scene
- Describes each scene using Claude Vision (Haiku)
- Splits the AMV into `frames/scene_01.mp4`, `frames/scene_02.mp4`, etc.
- Creates: `{output_dir}/amv/amv_analysis.json`

Optional flags: `--max-scenes 12` (default), `--min-scene-duration 3.0` (default, seconds)

### AMV Step 3: CHECKPOINT — Show AMV Analysis
- Read `{output_dir}/amv/amv_analysis.json`
- Present: total duration, number of scenes, brief description of each scene
- Ask the user for the **video topic/angle** (e.g., "narrate this as a Dragon Ball power ranking")
- Wait for user confirmation before generating the script

### AMV Step 4: Generate Script from AMV Analysis (YOU do this)
Read `amv_analysis.json` and generate `script.json` where:
- **`scenes` count** = `amv_analysis.scene_count` (do NOT invent extra scenes)
- **`duration_seconds`** per scene = `amv_analysis.scenes[i].duration_seconds` (taken directly from the analysis)
- **`target_duration_seconds`** = `amv_analysis.total_duration`
- **`narration_text`** = engaging commentary/narration that fits the scene's mood and visual description
- **`visual_prompt`** = reuse or rephrase the scene's `description` from the analysis
- **`content_type`** = `"anime"` (AMV content is always anime)
- **Omit `search_tags`** — frames are already in `frames/`, no clip fetching needed

Write to `{output_dir}/script/script.json` and show the script summary.

### AMV Step 5: CHECKPOINT — Approve Script
- Present: title, number of scenes, total duration, narration preview
- User can request tone/topic changes — regenerate narration if needed
- Do NOT change scene durations (they come from the AMV)

### AMV Step 6: Generate Voice Narration
```bash
python scripts/generate_voice.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```

### AMV Step 7: Fetch BGM (YOU choose the query)
Based on the video topic and AMV mood, choose a search query and run:
```bash
python scripts/fetch_bgm.py --query "{bgm_query}" --output-dir "{output_dir}"
```
Use the same BGM query guidelines from the standard workflow above.

### AMV Step 8: Compose Final Video
```bash
python scripts/compose_video.py --script-path "{output_dir}/script/script.json" --frames-dir "{output_dir}/frames" --audio-dir "{output_dir}/audio" --output-dir "{output_dir}" --bgm-path "{output_dir}/audio/bgm.mp3" --bgm-volume 0.20 --zoom-crop --amv-base-dir "{output_dir}"
```

**Multi-AMV workflow (per-anime clip routing):**
- When the video covers multiple anime series (e.g. "Top 5"), download each AMV into its own subdirectory: `{output_dir}/amv1/`, `amv2/`, etc. Analyze each AMV separately so frames land in `amv1/frames/`, `amv2/frames/`, etc.
- Add an `"amv": N` field to each scene in `script.json` to declare which AMV's clips to use for that scene.
- Pass `--amv-base-dir "{output_dir}"` to `compose_video.py` — it will automatically route each scene to the correct `amvN/frames/` pool and cycle through that AMV's clips in order.
- `--zoom-crop` scales clips 12% larger and crops from the top-left corner, removing bottom-right watermarks.
- The global `--frames-dir` is still required as a fallback for scenes without an `amv` field.

### AMV Step 9: Generate Thumbnail
```bash
python scripts/generate_thumbnail.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}" --highlight-frame "{output_dir}/amvN/frames/scene_07.mp4"
```
Use `--highlight-frame` to select a specific AMV scene that has strong visual impact. Scene 7 at second 5 is a good default — adjust based on the AMV content.

### AMV Step 10: CHECKPOINT — Approve Video
- Report final video path, duration, file size
- Wait for user approval before publishing

### AMV Step 11: Publish to YouTube
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" --privacy "private" --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

### AMV Step 12: Post-Publish Steps
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
- Scene durations are fixed — taken directly from the AMV's natural cuts
- Write engaging commentary: power rankings, character analysis, "what if" scenarios, storytelling
- Match narration energy to the scene's mood (intense = fast-paced, emotional = slower)
- Do NOT generate `search_tags` — frames are already split and in `frames/`

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
  Scene X:    scene_type="rank_transition", ~2.5s, rank=N, name="<Anime Title>"
  Scene X+1:  scene_type="normal",          ~8s,   rank=N, series-specific tags, amv=N, character intro
  Scene X+2:  scene_type="normal",          ~7s,   rank=N, series-specific tags, amv=N, why they rank here

Last scene: scene_type="normal", ~14s, outro narration (CTA overlay auto-added by compositor), amv=<any>
```

**Multi-AMV intro/hook**: For intro and hook scenes, assign `amv` values that span multiple different series (e.g., `amv=4` for intro, `amv=2` for scene 2) to give visual variety before the ranking begins. Avoid using `amv=1` for both.

**Last scene duration**: Set the last scene's `duration_seconds` to at least the TTS narration length + 2s buffer. A safe default is 14s.

**`name` field on rank transitions**: Always include `"name": "<Anime Title>"` on every `rank_transition` scene. The compositor renders the anime title above the gold rank number on the black card.

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

## Shorts Workflow (companion Short for any video)

After the main video is approved, always offer to generate a companion YouTube Short (30s vertical). The Short reuses the same AMV frames already downloaded — no extra downloads needed.

### Shorts Step 1: Generate script_short.json (YOU do this)
- Write to `{output_dir}/script/script_short.json`
- **Structure:** 1 intro scene (~4s) + 1 rank_transition + 1 normal per rank + 1 outro with CTA (~5s)
- **Total:** ≤ 30s
- **Narration:** Very short, punchy — 1–2 sentences max per scene
- **Same `amv` routing** as the main video
- **Title** must contain `#Shorts` (YouTube detection)
- **No `search_tags`** — frames already extracted

### Shorts Step 2: Generate Voice
```bash
python scripts/generate_voice.py --script-path "{output_dir}/script/script_short.json" --output-dir "{output_dir}/short"
```

### Shorts Step 3: Compose Short (vertical 1080×1920)
```bash
python scripts/compose_video.py \
  --script-path "{output_dir}/script/script_short.json" \
  --frames-dir "{output_dir}/amv1/frames" \
  --audio-dir "{output_dir}/short/audio" \
  --output-dir "{output_dir}/short" \
  --bgm-path "{output_dir}/audio/bgm.mp3" \
  --bgm-volume 0.15 \
  --zoom-crop \
  --shorts \
  --amv-base-dir "{output_dir}"
```
Output: `{output_dir}/short/final/final_short.mp4`

### Shorts Step 4: Publish
```bash
python scripts/publish_youtube.py \
  --script-path "{output_dir}/script/script_short.json" \
  --video-path "{output_dir}/short/final/final_short.mp4" \
  --thumbnail-path "{output_dir}/thumbnail/thumbnail.jpg" \
  --privacy "public" \
  --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```
Shorts can go public immediately (no endcard, no chapter timestamps needed).

---

## Rules
- Scene durations must sum to target_duration_seconds (±5s)
- Minimum 5 scenes, maximum 20 scenes
- First scene must hook the viewer
- Always show the user the script before proceeding
- Report progress after each step completes
- If a step fails, inform the user and offer to retry or skip
- For anime content: accept that Content ID claims may occur (not strikes)

## Environment
- Ensure `.env` is configured with API keys before running agent scripts
- FFmpeg must be installed and available in PATH
- Output goes to `output/` directory (gitignored)
- State tracked in `state.json`
