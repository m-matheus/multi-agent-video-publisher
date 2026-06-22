# Pipeline Manual — AMV Ranking Video

Complete walkthrough for running the full pipeline from the terminal, without Claude.

> **Note:** Step 6 (script generation) requires Claude — it reads the AMV analyses and writes `script.json`. Every other step is a Python script you run directly.

---

## Setup

```bash
# All commands run from the project root
cd /path/to/multi-agent-video-publisher

# Confirm .env has the required keys
cat .env
# Required: ANTHROPIC_API_KEY, OPENAI_API_KEY, ELEVENLABS_API_KEY
# Optional: FREESOUND_API_KEY, TIKTOK_CLIENT_KEY
```

---

## Step 1 — Analyze Channel (optional but recommended)

Fetches your channel's upload history so the trends script can avoid suggesting topics you've already covered.

```bash
python scripts/analyze_channel.py \
  --days 90 \
  --output-file output/channel_analytics.json \
  --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q
```

Output: `output/channel_analytics.json`

---

## Step 2 — Analyze Trends

Finds what's trending on YouTube right now. Prints a Top 10 table with suggested topics.

```bash
python scripts/analyze_trends.py \
  --days 30 \
  --min-duration 60 \
  --channel-cache output/channel_analytics.json \
  --output-file output/trends_cache.json
```

If specific anime are trending due to news or new seasons, boost them:

```bash
python scripts/analyze_trends.py \
  --days 30 \
  --min-duration 60 \
  --channel-cache output/channel_analytics.json \
  --output-file output/trends_cache.json \
  --boost-anime "Solo Leveling" "Dandadan"
```

Output: printed table + `output/trends_cache.json`

---

## Step 3 — Create Output Folder

Pick a topic slug and create the folder. Format: `YYYYMMDD-{slug}`.

```bash
OUTPUT_DIR="output/20260621-top5-naruto-villains"
mkdir -p "$OUTPUT_DIR"
```

---

## Step 4 — Download AMV(s)

### Single AMV

```bash
python scripts/fetch_amv.py \
  --url "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
  --output-dir "$OUTPUT_DIR"
```

Output: `$OUTPUT_DIR/amv/amv_source.mp4` and `amv/amv_metadata.json`

### Multi-AMV (one per rank — Top 5 example)

```bash
python scripts/fetch_amv.py --url "https://youtu.be/AMV1" --output-dir "$OUTPUT_DIR/amv1"
python scripts/fetch_amv.py --url "https://youtu.be/AMV2" --output-dir "$OUTPUT_DIR/amv2"
python scripts/fetch_amv.py --url "https://youtu.be/AMV3" --output-dir "$OUTPUT_DIR/amv3"
python scripts/fetch_amv.py --url "https://youtu.be/AMV4" --output-dir "$OUTPUT_DIR/amv4"
python scripts/fetch_amv.py --url "https://youtu.be/AMV5" --output-dir "$OUTPUT_DIR/amv5"
```

---

## Step 5 — Analyze AMV(s)

Detects scene cuts, extracts keyframes, describes each scene via Claude Vision, and splits the AMV into individual clips.

### Single AMV

```bash
python scripts/analyze_amv.py \
  --amv-path "$OUTPUT_DIR/amv/amv_source.mp4" \
  --output-dir "$OUTPUT_DIR"
```

### Multi-AMV

```bash
python scripts/analyze_amv.py --amv-path "$OUTPUT_DIR/amv1/amv/amv_source.mp4" --output-dir "$OUTPUT_DIR/amv1"
python scripts/analyze_amv.py --amv-path "$OUTPUT_DIR/amv2/amv/amv_source.mp4" --output-dir "$OUTPUT_DIR/amv2"
python scripts/analyze_amv.py --amv-path "$OUTPUT_DIR/amv3/amv/amv_source.mp4" --output-dir "$OUTPUT_DIR/amv3"
python scripts/analyze_amv.py --amv-path "$OUTPUT_DIR/amv4/amv/amv_source.mp4" --output-dir "$OUTPUT_DIR/amv4"
python scripts/analyze_amv.py --amv-path "$OUTPUT_DIR/amv5/amv/amv_source.mp4" --output-dir "$OUTPUT_DIR/amv5"
```

Optional flags:
- `--max-scenes 12` (default: 12)
- `--min-scene-duration 3.0` (default: 3.0s)

Output: `amvN/frames/scene_01.mp4`, `scene_02.mp4`, ... and `amvN/amv/amv_analysis.json`

---

## Step 5b — Review Clips (manual)

Open each `amvN/frames/` folder and watch the clips. Delete any you don't want in the video.

```
$OUTPUT_DIR/amv1/frames/
$OUTPUT_DIR/amv2/frames/
...
```

After deleting unwanted clips, count what remains:

```bash
ls "$OUTPUT_DIR/amv1/frames/" | wc -l
ls "$OUTPUT_DIR/amv2/frames/" | wc -l
```

---

## Step 6 — Generate Script

**Novo fluxo: script-first.** O script é gerado com base no tópico, independente dos AMVs. Os AMVs são background — buscados depois que o ranking está decidido.

### 6a — Gerar outline + queries de busca

```bash
python scripts/generate_script.py \
  --output-dir "$OUTPUT_DIR" \
  --topic "Top 5 Strongest Hunters in Solo Leveling" \
  --outline
```

Imprime:
- Ranking completo (rank 1–5 com nomes)
- Momentos visuais chave por rank
- Query de busca do YouTube por rank (ex: `"sung jinwoo shadow monarch amv 4k"`)

Salva: `$OUTPUT_DIR/script/outline.json`

### 6b — Baixar os AMVs (usando as queries do outline)

```bash
python scripts/fetch_amv.py --url "https://youtu.be/..." --output-dir "$OUTPUT_DIR/amv1"
python scripts/fetch_amv.py --url "https://youtu.be/..." --output-dir "$OUTPUT_DIR/amv2"
# ...um por rank
```

### 6c — Dividir os AMVs em clips

```bash
python scripts/analyze_amv.py --amv-path "$OUTPUT_DIR/amv1/amv/amv_source.mp4" --output-dir "$OUTPUT_DIR/amv1"
python scripts/analyze_amv.py --amv-path "$OUTPUT_DIR/amv2/amv/amv_source.mp4" --output-dir "$OUTPUT_DIR/amv2"
# ...um por AMV
```

### 6d — (manual) Revisar e curar clips

Abra cada `amvN/frames/` e delete os clips que não quer usar.

### 6e — Gerar script completo

```bash
python scripts/generate_script.py \
  --output-dir "$OUTPUT_DIR" \
  --topic "Top 5 Strongest Hunters in Solo Leveling"
```

Usa o `outline.json` existente automaticamente para manter o ranking aprovado. Salva `script.json`.

Preview sem salvar:
```bash
python scripts/generate_script.py \
  --output-dir "$OUTPUT_DIR" \
  --topic "Top 5 Strongest Hunters in Solo Leveling" \
  --dry-run
```

Output: `$OUTPUT_DIR/script/script.json`

---

## Step 7 — Generate Thumbnail

```bash
python scripts/generate_thumbnail.py \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --output-dir "$OUTPUT_DIR"
```

Output: `$OUTPUT_DIR/thumbnail/thumbnail.jpg` (1280×720 JPEG)

Can run in parallel with Step 8.

---

## Step 8 — Generate Voice Narration

```bash
python scripts/generate_voice.py \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --output-dir "$OUTPUT_DIR"
```

Output: `$OUTPUT_DIR/audio/scene_01.mp3`, `scene_02.mp3`, ...

---

## Step 9 — Fetch BGM

Always try Freesound CC0 first (zero Content ID risk). Fall back to YouTube only if Freesound returns nothing.

**Freesound (preferred):**
```bash
python scripts/fetch_bgm.py \
  --query "epic orchestral cinematic" \
  --output-dir "$OUTPUT_DIR"
```

**YouTube fallback:**
```bash
python scripts/fetch_bgm.py \
  --search "epic orchestral cinematic" \
  --output-dir "$OUTPUT_DIR"
```

BGM query cheatsheet:
| Content | Query |
|---------|-------|
| Action / fighting | `"epic orchestral cinematic"` |
| Emotional / dramatic | `"emotional piano orchestral"` |
| Dragon Ball | `"epic orchestral cinematic"` |
| Demon Slayer | `"dark orchestral epic"` |
| Default anime | `"epic cinematic orchestral"` |

Output: `$OUTPUT_DIR/audio/bgm.mp3`

---

## Step 10 — Compose Final Video

### Single AMV

```bash
python scripts/compose_video.py \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --frames-dir "$OUTPUT_DIR/frames" \
  --audio-dir "$OUTPUT_DIR/audio" \
  --output-dir "$OUTPUT_DIR" \
  --bgm-path "$OUTPUT_DIR/audio/bgm.mp3" \
  --bgm-volume 0.15 \
  --endcard-path "channels/hakase-anime/assets/endcard.png" \
  --endcard-duration 10
```

### Multi-AMV

```bash
python scripts/compose_video.py \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --frames-dir "$OUTPUT_DIR/amv1/frames" \
  --audio-dir "$OUTPUT_DIR/audio" \
  --output-dir "$OUTPUT_DIR" \
  --bgm-path "$OUTPUT_DIR/audio/bgm.mp3" \
  --bgm-volume 0.15 \
  --amv-base-dir "$OUTPUT_DIR" \
  --endcard-path "channels/hakase-anime/assets/endcard.png" \
  --endcard-duration 10
```

> Add `--zoom-crop` only if a specific AMV has a watermark that needs cropping. Never by default.

Output: `$OUTPUT_DIR/final/final_video.mp4`

---

## Step 11 — Publish to YouTube

Review the video first, then publish as private:

```bash
python scripts/publish_youtube.py \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --video-path "$OUTPUT_DIR/final/final_video.mp4" \
  --thumbnail-path "$OUTPUT_DIR/thumbnail/thumbnail.jpg" \
  --privacy "private" \
  --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

To schedule a public publish time:
```bash
python scripts/publish_youtube.py \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --video-path "$OUTPUT_DIR/final/final_video.mp4" \
  --thumbnail-path "$OUTPUT_DIR/thumbnail/thumbnail.jpg" \
  --publish-at "2026-06-22 18:00" \
  --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

Note the `VIDEO_ID` from the output — you'll need it for the next steps.

---

## Step 12 — Post-Publish Updates

### Update description, chapters, tags, and make public

```bash
# Dry-run first to preview
python scripts/update_video.py \
  --video-id "VIDEO_ID" \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --dry-run

# Apply and make public
python scripts/update_video.py \
  --video-id "VIDEO_ID" \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --make-public
```

> Skip `--make-public` if you used `--publish-at` (video goes public automatically at scheduled time).

### Generate community post text

```bash
python scripts/post_community.py \
  --script-path "$OUTPUT_DIR/script/script.json" \
  --video-id "VIDEO_ID" \
  --output-dir "$OUTPUT_DIR" \
  --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"
```

Copy the printed `post_text` and paste it manually in YouTube Studio → Community tab.

---

## Step 13 — Reply to Comments

Always run after publishing. Scans the full channel (not just recent videos).

```bash
# Dry-run first — review generated replies
python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q

# Post the replies
python scripts/reply_comments.py --channel-id UCyRJuLu9xr7mrRh-j52RQ9Q --post
```

---

## Companion Short (optional)

After the main video is published, you can generate a Short (40–55s).

> The Short script is generated with `generate_script.py --short`, same as Step 6.

### Short pipeline (Curiosidade format)

```bash
# 1. Generate Short script
python scripts/generate_script.py \
  --output-dir "$OUTPUT_DIR" \
  --topic "Itachi's forbidden jutsu was never meant to exist" \
  --short curiosity \
  --anime naruto

# 2. Generate cover (1080x1920)
python scripts/generate_thumbnail.py \
  --script-path "$OUTPUT_DIR/script/script_curiosity_{anime}.json" \
  --output-dir "$OUTPUT_DIR" \
  --shorts

# 3. Generate voice with timestamps
python scripts/generate_voice.py \
  --script-path "$OUTPUT_DIR/script/script_curiosity_{anime}.json" \
  --output-dir "$OUTPUT_DIR/short_curiosity_{anime}" \
  --timestamps

# 4. Generate captions
python scripts/generate_captions.py \
  --script-path "$OUTPUT_DIR/script/script_curiosity_{anime}.json" \
  --audio-dir "$OUTPUT_DIR/short_curiosity_{anime}/audio" \
  --output-dir "$OUTPUT_DIR/short_curiosity_{anime}" \
  --shorts \
  --color yellow

# 5. Compose
python scripts/compose_video.py \
  --script-path "$OUTPUT_DIR/script/script_curiosity_{anime}.json" \
  --frames-dir "$OUTPUT_DIR/amv1/frames" \
  --audio-dir "$OUTPUT_DIR/short_curiosity_{anime}/audio" \
  --output-dir "$OUTPUT_DIR/short_curiosity_{anime}" \
  --bgm-path "$OUTPUT_DIR/audio/bgm.mp3" \
  --bgm-volume 0.15 \
  --shorts \
  --amv-base-dir "$OUTPUT_DIR" \
  --endcard-path "channels/hakase-anime/assets/endcard.png" \
  --endcard-duration 10 \
  --captions-path "$OUTPUT_DIR/short_curiosity_{anime}/audio/captions.ass"

# 6. Publish to YouTube
python scripts/publish_youtube.py \
  --script-path "$OUTPUT_DIR/script/script_curiosity_{anime}.json" \
  --video-path "$OUTPUT_DIR/short_curiosity_{anime}/final/final_short.mp4" \
  --thumbnail-path "$OUTPUT_DIR/thumbnail/cover.jpg" \
  --privacy "public" \
  --channel-id "UCyRJuLu9xr7mrRh-j52RQ9Q"

# 7. Publish to TikTok (skip if TIKTOK_CLIENT_KEY not in .env)
python scripts/publish_tiktok.py \
  --script-path "$OUTPUT_DIR/script/script_curiosity_{anime}.json" \
  --video-path "$OUTPUT_DIR/short_curiosity_{anime}/final/final_short.mp4" \
  --privacy SELF_ONLY
```

Caption color guide:
| Mood | Color |
|------|-------|
| Action / fighting | `yellow` or `orange` |
| Dramatic / emotional | `white` |
| Sci-fi / futuristic | `cyan` |
| Horror / dark | `red` |

---

## Quick Reference — All Steps Are Terminal-Only

Every step in the pipeline runs as a Python script. No step requires opening Claude manually.

| Step | Script |
|------|--------|
| 1 | `analyze_channel.py` |
| 2 | `analyze_trends.py` |
| 4 | `fetch_amv.py` |
| 5 | `analyze_amv.py` |
| 6 | `generate_script.py` ← calls Claude API internally |
| 7 | `generate_thumbnail.py` |
| 8 | `generate_voice.py` |
| 9 | `fetch_bgm.py` |
| 10 | `compose_video.py` |
| 11 | `publish_youtube.py` |
| 12 | `update_video.py` + `post_community.py` |
| 13 | `reply_comments.py` |
| Short | `generate_script.py --short` → `generate_thumbnail.py --shorts` → `generate_voice.py` → `generate_captions.py` → `compose_video.py --shorts` → `publish_youtube.py` → `publish_tiktok.py` |
