# Step 04: Voice Narration

## Agent
Vocal Vanguard 🎙️

## Objective
Generate voice narration audio for all scene narration text using ElevenLabs.

## Inputs
- `script_path`: Path to `{output_dir}/script/script.json`
- `output_dir`: The run-specific output directory

## Dependencies
- Step 01 (script.json must exist)
- **CHECKPOINT**: User must approve script before this step executes

## Process
1. Read script.json for narration text per scene
2. Select voice_id based on content type
3. Generate audio for each segment sequentially
4. Save individual segments as `segment_XX.mp3`
5. Concatenate into `narration_full.mp3` with 0.3s gaps
6. Record actual durations for timing sync
7. Update state.json with duration data

## Expected Output
- `{output_dir}/audio/narration_segments/segment_01.mp3` through `segment_XX.mp3`
- `{output_dir}/audio/narration_full.mp3`

## API Configuration
- Model: `eleven_v3`
- Format: `mp3_44100_128`
- Voice: VOICE_ID_ANIME or VOICE_ID_BEDTIME from .env
- Sequential execution (rate limit friendly)

## Command
```bash
python scripts/generate_voice.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```
