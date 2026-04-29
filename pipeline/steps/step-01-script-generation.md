# Step 01: Script Generation

## Agent
Script Scribe 📝

## Objective
Generate a structured video script based on the provided topic and content type.

## Inputs
- `topic`: The video topic/theme (provided by user)
- `content_type`: "anime" or "bedtime-story"
- `output_dir`: The run-specific output directory
- `duration`: Target video duration (default: 60s)

## Process
1. Create output directory: `{output_dir}/script/`
2. Load prompt template from `templates/{content_type}_script_prompt.md`
3. Call LLM with the structured prompt
4. Parse and validate the JSON response
5. Retry up to 3 times on invalid JSON or failed validation
6. Write `script.json` to output directory
7. Update state.json with step completion

## Expected Output
- `{output_dir}/script/script.json` — Structured script with scenes, prompts, narration

## Validation Rules
- Total scene durations sum to target_duration (±10s)
- Each scene has non-empty visual_prompt and narration_text
- Minimum 3 scenes, maximum 20 scenes
- Title under 100 characters
- Valid JSON structure

## Command
```bash
python scripts/generate_script.py --topic "{topic}" --type "{content_type}" --output-dir "{output_dir}" --duration {duration}
```
