"""
YouTube thumbnail generation via fal.ai.

Usage:
    python scripts/generate_thumbnail.py --script-path output/run-001/script/script.json --output-dir output/run-001
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, TEMPLATES_DIR
from scripts.utils.file_helpers import ensure_dir, download_file
from scripts.utils.state_manager import StateManager


def parse_args():
    parser = argparse.ArgumentParser(description="Generate YouTube thumbnail via fal.ai")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    return parser.parse_args()


def select_hero_scene(scenes: list[dict]) -> dict:
    dramatic_keywords = ["epic", "dramatic", "battle", "reveal", "confrontation", "climax", "powerful", "final"]
    best_score = -1
    best_scene = scenes[len(scenes) * 2 // 3] if scenes else scenes[0]

    for scene in scenes:
        prompt = scene.get("visual_prompt", "").lower()
        score = sum(1 for kw in dramatic_keywords if kw in prompt)
        if score > best_score:
            best_score = score
            best_scene = scene
    return best_scene


def build_thumbnail_prompt(scene: dict, title: str, content_type: str) -> str:
    base = scene["visual_prompt"]
    if content_type == "anime":
        style = "anime YouTube thumbnail, extremely vibrant colors, dramatic lighting, close-up composition, high contrast, cinematic, eye-catching, professional quality"
    else:
        style = "children's storybook YouTube thumbnail, warm inviting colors, magical atmosphere, close-up of main character, soft glow, enchanting, professional quality"
    return f"{base}, {style}, no text, no watermark, sharp focus, 1280x720"


def main():
    args = parse_args()
    config = load_config()
    os.environ["FAL_KEY"] = config["fal_key"]

    import fal_client

    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    thumbnail_dir = ensure_dir(output_dir / "thumbnail")

    content_type = script.get("content_type", "anime")
    scenes = script["scenes"]
    title = script.get("title", "")

    state = StateManager()
    state.update_step("step-06-thumbnail-creation", "running")

    hero_scene = select_hero_scene(scenes)
    prompt = build_thumbnail_prompt(hero_scene, title, content_type)

    print(f"Generating thumbnail for: {title}")
    print(f"  Using scene {hero_scene.get('scene_number', '?')} as hero scene")

    model = "fal-ai/flux/dev"
    max_retries = 3
    image_url = None

    for attempt in range(max_retries):
        try:
            result = fal_client.run(
                model,
                arguments={
                    "prompt": prompt,
                    "negative_prompt": "blurry, low quality, text, watermark, logo, ugly, distorted",
                    "image_size": {"width": 1280, "height": 720},
                    "num_images": 1,
                },
            )
            image_url = result["images"][0]["url"]
            break
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                print("ERROR: Failed to generate thumbnail")
                state.update_step("step-06-thumbnail-creation", "failed")
                sys.exit(1)

    thumbnail_path = thumbnail_dir / "thumbnail.png"
    download_file(image_url, thumbnail_path)
    print(f"  Thumbnail saved: {thumbnail_path.name}")

    state.update_step("step-06-thumbnail-creation", "completed", {"thumbnail_path": str(thumbnail_path)})


if __name__ == "__main__":
    main()
