# Step 03: Video Animation

## Agent
Video Virtuoso 🎬

## Objective
Animate each scene image into a short video clip using fal.ai image-to-video models.

## Inputs
- `script_path`: Path to `{output_dir}/script/script.json`
- `images_dir`: Path to `{output_dir}/images/`
- `output_dir`: The run-specific output directory

## Dependencies
- Step 02 (scene images must exist)

## Process
1. Read script.json for scene durations and context
2. Upload scene images to fal.ai
3. For each image, submit image-to-video request with motion prompt
4. Wait for generation completion (up to 5 min per clip)
5. Download video clips
6. For failures, create Ken Burns fallback via FFmpeg
7. Save as `clip_XX.mp4`

## Expected Output
- `{output_dir}/videos/clip_01.mp4` through `clip_XX.mp4`

## API Configuration
- Model: `fal-ai/wan-2.1/image-to-video`
- Max parallel: 3
- Timeout: 5 minutes per clip
- Fallback: Ken Burns zoom/pan effect

## Cost Considerations
- ~$0.05-0.10 per second of video
- Target 4-6 seconds per clip
- Total budget: <$5 per video

## Command
```bash
python scripts/generate_videos.py --script-path "{output_dir}/script/script.json" --images-dir "{output_dir}/images" --output-dir "{output_dir}"
```
