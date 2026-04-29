# Step 05: Video Composition

## Agent
Composite Conductor 🎵

## Objective
Combine video clips and narration audio into a polished final video using FFmpeg.

## Inputs
- `script_path`: Path to `{output_dir}/script/script.json`
- `videos_dir`: Path to `{output_dir}/videos/`
- `audio_dir`: Path to `{output_dir}/audio/`
- `output_dir`: The run-specific output directory
- `bgm_path`: Optional background music file

## Dependencies
- Step 03 (video clips must exist)
- Step 04 (narration audio must exist)

## Process
1. Read script.json for scene ordering and transitions
2. Verify all video clips and audio exist
3. Scale/pad all clips to 1920x1080
4. Build FFmpeg filter complex (concatenation + transitions)
5. Mix narration audio (+ optional BGM at 15% volume)
6. Execute FFmpeg command (timeout: 5 minutes)
7. Validate output (file exists, duration correct, playable)
8. Save to `final/final_video.mp4`

## Expected Output
- `{output_dir}/final/final_video.mp4`

## FFmpeg Settings
- Resolution: 1920x1080
- Codec: libx264, CRF 18, medium preset
- Audio: AAC 192kbps
- Frame rate: 24fps
- Flags: faststart, shortest

## Command
```bash
python scripts/compose_video.py --script-path "{output_dir}/script/script.json" --videos-dir "{output_dir}/videos" --audio-dir "{output_dir}/audio" --output-dir "{output_dir}"
```
