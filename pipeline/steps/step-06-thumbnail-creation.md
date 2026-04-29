# Step 06: Thumbnail Creation

## Agent
Thumbnail Tactician 🖼️

## Objective
Generate an eye-catching YouTube thumbnail optimized for click-through rate.

## Inputs
- `script_path`: Path to `{output_dir}/script/script.json`
- `output_dir`: The run-specific output directory

## Dependencies
- Step 01 (script.json must exist)

## Process
1. Read script.json to analyze all scenes
2. Select the most dramatic scene (hero scene)
3. Craft thumbnail-optimized prompt (close-up, vibrant, high contrast)
4. Generate via fal.ai at 1280x720
5. Download and save to `thumbnail/thumbnail.png`

## Expected Output
- `{output_dir}/thumbnail/thumbnail.png`

## API Configuration
- Model: `fal-ai/flux/dev` (higher quality)
- Resolution: 1280x720
- Retries: 3

## Hero Scene Selection
- Keywords: "epic", "dramatic", "battle", "reveal", "climax"
- Default: scene at 2/3 mark of story

## Command
```bash
python scripts/generate_thumbnail.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```
