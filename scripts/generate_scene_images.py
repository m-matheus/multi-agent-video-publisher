"""
Scene image generator for history/documentary content.
Generates one AI image per scene using the OpenAI Responses API (gpt-image-1).

Usage:
    python scripts/generate_scene_images.py \
        --script-path output/run-001/script/script.json \
        --output-dir output/run-001
"""
import argparse
import base64
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.file_helpers import ensure_dir
from scripts.utils.state_manager import StateManager


def parse_args():
    parser = argparse.ArgumentParser(description="Generate scene images via Responses API")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip scenes that already have an image file")
    parser.add_argument("--size", default="1536x1024",
                        help="Image size (default: 1536x1024 for landscape videos)")
    parser.add_argument("--quality", default="medium",
                        choices=["low", "medium", "high"],
                        help="Image quality (default: medium — faster and cheaper)")
    return parser.parse_args()


def build_image_request(scene: dict) -> str:
    visual_prompt = scene.get("visual_prompt", "")
    narration = scene.get("narration_text", "")
    scene_type = scene.get("scene_type", "normal")

    style_suffix = (
        "Oil painting style, dramatic chiaroscuro lighting, dark atmospheric, "
        "cinematic composition, highly detailed, 16:9 aspect ratio. "
        "No text, no watermarks, no UI elements."
    )

    if scene_type == "intro":
        return (
            f"Create a dramatic establishing scene for a history documentary. "
            f"{visual_prompt}. {style_suffix}"
        )

    return (
        f"Create a historically accurate documentary scene illustration. "
        f"Scene: {visual_prompt}. "
        f"Context: {narration[:120] if narration else ''}. "
        f"{style_suffix}"
    )


def generate_image(request: str, out_path: Path, config: dict,
                   size: str = "1536x1024", quality: str = "medium") -> Path | None:
    api_key = config.get("openai_api_key")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set in .env")
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        response = client.responses.create(
            model="gpt-4o",
            input=request,
            tools=[{
                "type": "image_generation",
                "quality": quality,
                "size": size,
            }],
        )

        image_data = next(
            (item.result for item in response.output
             if item.type == "image_generation_call"),
            None,
        )
        if not image_data:
            print("  ERROR: No image in response")
            return None

        out_path.write_bytes(base64.b64decode(image_data))
        return out_path

    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def main():
    args = parse_args()
    config = load_config()
    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    frames_dir = ensure_dir(output_dir / "frames")

    scenes = script.get("scenes", [])
    total = len(scenes)

    state = StateManager()
    state.update_step("step-03-scene-images", "running")

    print(f"Generating {total} scene images (quality={args.quality}, size={args.size})...")
    print(f"Estimated cost: ~${total * 0.04:.2f} (gpt-image-1 medium)")

    generated = []
    failed = []

    for i, scene in enumerate(scenes):
        scene_num = scene.get("scene_number", i + 1)
        out_path = frames_dir / f"scene_{scene_num:02d}.jpg"

        if args.skip_existing and out_path.exists():
            print(f"  Scene {scene_num}/{total}: skipped (already exists)")
            generated.append(str(out_path))
            continue

        request = build_image_request(scene)
        print(f"  Scene {scene_num}/{total}: {scene.get('visual_prompt', '')[:80]}...")

        max_retries = 3
        result = None
        for attempt in range(max_retries):
            raw_path = frames_dir / f"scene_{scene_num:02d}_raw.png"
            result = generate_image(request, raw_path, config, args.size, args.quality)
            if result:
                break
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    Retry {attempt + 1} in {wait}s...")
                time.sleep(wait)

        if result:
            from PIL import Image
            img = Image.open(result).convert("RGB")
            img.save(str(out_path), "JPEG", quality=92)
            result.unlink(missing_ok=True)
            size_kb = out_path.stat().st_size // 1024
            print(f"    Saved: {out_path.name} ({size_kb} KB)")
            generated.append(str(out_path))
        else:
            print(f"    FAILED: scene {scene_num}")
            failed.append(scene_num)

        # Brief pause to avoid rate limiting
        if i < total - 1:
            time.sleep(0.5)

    print(f"\nDone: {len(generated)} generated, {len(failed)} failed")
    if failed:
        print(f"Failed scenes: {failed}")

    status = "completed" if not failed else "completed_with_errors"
    state.update_step("step-03-scene-images", status, {
        "frames_dir": str(frames_dir),
        "generated": len(generated),
        "failed": failed,
    })

    if len(generated) == 0:
        print("ERROR: No images generated")
        sys.exit(1)


if __name__ == "__main__":
    main()
