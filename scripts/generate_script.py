"""
Script validation and saving. Can accept script.json directly from Claude (orchestrator mode)
or generate via external LLM (standalone mode).

Usage (orchestrator mode - Claude writes the script):
    python scripts/generate_script.py --from-file script.json --topic "..." --type anime --output-dir output/run-001

Usage (standalone mode - calls external LLM):
    python scripts/generate_script.py --topic "..." --type anime --output-dir output/run-001
"""
import argparse
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, TEMPLATES_DIR
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager

SCRIPT_SCHEMA = {
    "title": "string",
    "description": "string",
    "tags": ["string"],
    "content_type": "anime | amv",
    "target_duration_seconds": 60,
    "scenes": [
        {
            "scene_number": 1,
            "duration_seconds": 8.0,
            "visual_prompt": "Detailed description for image generation",
            "narration_text": "Text to be spoken during this scene",
            "transition": "fade | cut | dissolve",
        }
    ],
}


def parse_args():
    parser = argparse.ArgumentParser(description="Validate and save video script")
    parser.add_argument("--topic", required=True, help="Video topic/theme")
    parser.add_argument("--type", required=True, choices=["anime", "amv", "history"], help="Content type")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--duration", type=int, default=60, help="Target video duration in seconds")
    parser.add_argument("--from-file", default=None, help="Path to pre-generated script.json (orchestrator mode)")
    return parser.parse_args()


def load_prompt_template(content_type: str) -> str:
    template_file = TEMPLATES_DIR / f"{content_type.replace('-', '_')}_script_prompt.md"
    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {template_file}")
    return template_file.read_text(encoding="utf-8")


def build_prompt(topic: str, content_type: str, duration: int, template: str) -> str:
    schema_str = json.dumps(SCRIPT_SCHEMA, indent=2)
    return template.format(topic=topic, duration=duration, schema=schema_str)


def call_llm(prompt: str, config: dict) -> str:
    provider = config["llm_provider"]
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=config["openai_api_key"])
        response = client.chat.completions.create(
            model=config["llm_model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=config["anthropic_api_key"])
        response = client.messages.create(
            model=config["llm_model"],
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def validate_script(script: dict, target_duration: int) -> tuple[bool, list[str]]:
    errors = []
    required_fields = ["title", "description", "tags", "content_type", "scenes"]
    for field in required_fields:
        if field not in script:
            errors.append(f"Missing required field: {field}")

    if "scenes" in script:
        if not script["scenes"]:
            errors.append("Script must have at least 1 scene")
        elif len(script["scenes"]) < 3:
            errors.append("Script should have at least 3 scenes")
        elif len(script["scenes"]) > 60:
            errors.append("Script should have at most 60 scenes")

        total_duration = sum(s.get("duration_seconds", 0) for s in script["scenes"])
        tolerance = max(30, target_duration * 0.05)
        if abs(total_duration - target_duration) > tolerance:
            errors.append(f"Total duration {total_duration}s deviates more than {tolerance:.0f}s from target {target_duration}s")

        for i, scene in enumerate(script["scenes"]):
            for field in ["visual_prompt", "narration_text", "duration_seconds"]:
                if not scene.get(field):
                    errors.append(f"Scene {i+1} missing field: {field}")

    if "title" in script and len(script.get("title", "")) > 100:
        errors.append("Title must be under 100 characters")

    return (len(errors) == 0, errors)


def main():
    args = parse_args()
    config = load_config()

    output_dir = Path(args.output_dir)
    script_dir = ensure_dir(output_dir / "script")

    state = StateManager()
    state.initialize_run(args.topic, args.type, str(output_dir))
    state.update_step("step-01-script-generation", "running")

    if args.from_file:
        # Orchestrator mode: Claude already generated the script, just validate and save
        from_path = Path(args.from_file)
        if not from_path.exists():
            print(f"ERROR: Script file not found: {from_path}")
            sys.exit(1)
        script = json.loads(from_path.read_text(encoding="utf-8"))
        is_valid, errors = validate_script(script, args.duration)
        if not is_valid:
            print(f"Validation errors: {errors}")
            state.update_step("step-01-script-generation", "failed")
            sys.exit(1)
    else:
        # Standalone mode: call external LLM
        template = load_prompt_template(args.type)
        prompt = build_prompt(args.topic, args.type, args.duration, template)

        max_retries = 3
        script = None
        for attempt in range(max_retries):
            try:
                raw_response = call_llm(prompt, config)
                script = json.loads(raw_response)
                is_valid, errors = validate_script(script, args.duration)
                if is_valid:
                    break
                print(f"Attempt {attempt + 1}: Validation errors: {errors}")
                if attempt < max_retries - 1:
                    prompt += f"\n\nPrevious attempt had errors: {errors}. Please fix and regenerate."
            except json.JSONDecodeError as e:
                print(f"Attempt {attempt + 1}: Invalid JSON response: {e}")
                if attempt < max_retries - 1:
                    prompt += "\n\nIMPORTANT: You must return ONLY valid JSON. No markdown, no explanation."

        if script is None:
            state.update_step("step-01-script-generation", "failed")
            print("ERROR: Failed to generate valid script after all retries")
            sys.exit(1)

    script["content_type"] = args.type
    script["target_duration_seconds"] = args.duration

    script_path = script_dir / "script.json"
    script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    state.update_step("step-01-script-generation", "completed", {"script_path": str(script_path)})
    print(f"Script saved successfully: {script_path}")
    print(f"Title: {script.get('title')}")
    print(f"Scenes: {len(script.get('scenes', []))}")
    total_dur = sum(s.get("duration_seconds", 0) for s in script.get("scenes", []))
    print(f"Total duration: {total_dur}s")


if __name__ == "__main__":
    main()
