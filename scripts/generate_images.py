"""
Scene image generation via fal.ai. Generates one image per scene.

Usage:
    python scripts/generate_images.py --script-path output/run-001/script/script.json --output-dir output/run-001
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.file_helpers import ensure_dir, download_file
from scripts.utils.state_manager import StateManager

STYLE_MODIFIERS = {
    "anime": "anime style, vibrant colors, detailed illustration, studio quality, cinematic lighting, 16:9 aspect ratio, high detail",
    "bedtime-story": "children's storybook illustration, soft watercolor, warm lighting, gentle colors, dreamy atmosphere, 16:9 aspect ratio, cozy",
}

NEGATIVE_PROMPT = "blurry, low quality, distorted, watermark, text, logo, signature, ugly, deformed, extra limbs"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate scene images via fal.ai")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--model", default=None, help="Override image model")
    parser.add_argument("--max-parallel", type=int, default=5, help="Max parallel requests")
    return parser.parse_args()


def build_image_prompt(visual_prompt: str, content_type: str) -> str:
    modifier = STYLE_MODIFIERS.get(content_type, STYLE_MODIFIERS["anime"])
    return f"{visual_prompt}, {modifier}"


async def generate_single_image(prompt: str, negative_prompt: str, model: str, semaphore: asyncio.Semaphore) -> str:
    import fal_client

    async with semaphore:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await fal_client.run_async(
                    model,
                    arguments={
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "image_size": {"width": 1344, "height": 768},
                        "num_images": 1,
                    },
                )
                return result["images"][0]["url"]
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  Retry {attempt + 1} after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    raise


async def generate_all_images(scenes: list[dict], content_type: str, model: str, max_parallel: int) -> list[str]:
    semaphore = asyncio.Semaphore(max_parallel)
    tasks = []
    for scene in scenes:
        prompt = build_image_prompt(scene["visual_prompt"], content_type)
        task = generate_single_image(prompt, NEGATIVE_PROMPT, model, semaphore)
        tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    urls = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  ERROR generating image for scene {i+1}: {result}")
            urls.append(None)
        else:
            urls.append(result)
    return urls


def main():
    args = parse_args()
    config = load_config()
    os.environ["FAL_KEY"] = config["fal_key"]

    script_path = Path(args.script_path)
    script = json.loads(script_path.read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    images_dir = ensure_dir(output_dir / "images")

    model = args.model or config["default_image_model"]
    content_type = script.get("content_type", "anime")
    scenes = script["scenes"]

    state = StateManager()
    state.update_step("step-02-image-generation", "running")

    print(f"Generating {len(scenes)} scene images using {model}...")
    start_time = time.time()

    image_urls = asyncio.run(generate_all_images(scenes, content_type, model, args.max_parallel))

    image_paths = []
    for i, url in enumerate(image_urls):
        if url:
            dest = images_dir / f"scene_{i+1:02d}.png"
            download_file(url, dest)
            image_paths.append(str(dest))
            print(f"  Scene {i+1}: saved to {dest.name}")
        else:
            image_paths.append(None)
            print(f"  Scene {i+1}: FAILED")

    elapsed = time.time() - start_time
    successful = sum(1 for p in image_paths if p)
    print(f"\nCompleted: {successful}/{len(scenes)} images in {elapsed:.1f}s")

    state.update_step("step-02-image-generation", "completed", {"image_paths": image_paths})


if __name__ == "__main__":
    main()
