# Step 02: Fetch Anime Frames

## Agent
Frame Fetcher 🎞️

## Objective
Fetch anime video clips from Sakugabooru matching each scene's visual description and mood.

## Inputs
- `script_path`: Path to `{output_dir}/script/script.json`
- `output_dir`: The run-specific output directory

## Dependencies
- Step 01 (script.json must exist and be approved)

## Process
1. Read script.json for `search_tags` and `visual_prompt` per scene
2. For each scene, search Sakugabooru API with tags
3. Download the best matching clip (prioritize: good animation quality, matching mood)
4. Save as `scene_XX.{mp4|webm|gif}` in `{output_dir}/frames/`
5. If no results: try broader tags, then fallback to generic "animated effects"
6. Rate limit: 1 second between API calls

## Sakugabooru API
```
GET https://www.sakugabooru.com/post.json?tags={tags}&limit=20
```
Returns array of posts with `file_url` field (direct link to clip).

## Tag Strategy
- Use `search_tags` field from script if available
- Otherwise, extract keywords from `visual_prompt`
- Always include "animated" tag for video clips
- Combine with anime-specific tags when the story references a specific anime

## Expected Output
- `{output_dir}/frames/scene_01_01.mp4` (or .webm/.gif)
- One file per scene minimum

## Alternative: Local Source
```bash
python scripts/fetch_frames.py --source local --local-dir "/path/to/my/clips" --output-dir "{output_dir}"
```

## Command
```bash
python scripts/fetch_frames.py --script-path "{output_dir}/script/script.json" --output-dir "{output_dir}"
```
