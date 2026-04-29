# Step 02: Image Generation

## Agent
Image Illustrator 🎨

## Objective
Generate anime-style or storybook illustrations for each scene defined in the script.

## Inputs
- `script_path`: Path to `{output_dir}/script/script.json`
- `output_dir`: The run-specific output directory

## Dependencies
- Step 01 (script.json must exist)

## Process
1. Read and parse script.json
2. Create `{output_dir}/images/` directory
3. For each scene, construct enhanced prompt with style modifiers
4. Submit all image generation requests to fal.ai (max 5 parallel)
5. Download generated images from returned URLs
6. Save as `scene_XX.png`
7. Update state.json

## Expected Output
- `{output_dir}/images/scene_01.png` through `scene_XX.png`

## API Configuration
- Model: `fal-ai/fast-sdxl` or `fal-ai/flux/dev`
- Resolution: 1344x768 (16:9)
- Retries: 3 per image with exponential backoff

## Command
```bash
python scripts/generate_images.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```
