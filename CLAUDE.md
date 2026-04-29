# YouTube Video Generator Squad

## Role
You (Claude) are the **orchestrator** of this multi-agent pipeline. You generate the video scripts directly (you ARE the LLM) and trigger each agent's Python script in sequence, managing checkpoints and state.

## How to Run a Video Generation

When the user asks to generate a video (e.g., "create a video about...", "generate a video on..."), follow this pipeline:

If the user provides a **YouTube AMV URL**, use the **AMV Workflow** below instead of the standard pipeline.

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

### Step 5: Compose Final Video
```bash
python scripts/compose_video.py --script-path "{output_dir}/script/script.json" --frames-dir "{output_dir}/frames" --audio-dir "{output_dir}/audio" --output-dir "{output_dir}"
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
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.png" --privacy "private"
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

### AMV Step 7: Compose Final Video
```bash
python scripts/compose_video.py --script-path "{output_dir}/script/script.json" --frames-dir "{output_dir}/frames" --audio-dir "{output_dir}/audio" --output-dir "{output_dir}"
```
The compositor automatically uses the pre-split AMV segments from `frames/`.

### AMV Step 8: Generate Thumbnail
```bash
python scripts/generate_thumbnail.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```

### AMV Step 9: CHECKPOINT — Approve Video
- Report final video path, duration, file size
- Wait for user approval before publishing

### AMV Step 10: Publish to YouTube
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.png" --privacy "private"
```

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
      "duration_seconds": 8.0,
      "visual_prompt": "Detailed scene description for image/clip search",
      "narration_text": "Text spoken aloud during this scene",
      "transition": "fade | cut | dissolve",
      "search_tags": "sakugabooru tags for this scene (e.g., 'fighting animated naruto')"
    }
  ]
}
```

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

## Rules
- Scene durations must sum to target_duration_seconds (±5s)
- Minimum 5 scenes, maximum 15 scenes
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
