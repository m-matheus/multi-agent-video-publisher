"""
Video clip generation via fal.ai image-to-video. Animates each scene image.

Usage:
    python scripts/generate_videos.py --script-path output/run-001/script/script.json --images-dir output/run-001/images --output-dir output/run-001
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config
from scripts.utils.file_helpers import ensure_dir, download_file, get_scene_files
from scripts.utils.state_manager import StateManager


def parse_args():
    parser = argparse.ArgumentParser(description="Generate video clips via fal.ai")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--images-dir", required=True, help="Path to scene images directory")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--model", default=None, help="Override video model")
    parser.add_argument("--max-parallel", type=int, default=3, help="Max parallel requests")
    return parser.parse_args()


def build_motion_prompt(scene: dict) -> str:
    narration = scene.get("narration_text", "")
    visual = scene.get("visual_prompt", "")
    return f"Smooth cinematic motion. Scene context: {visual[:100]}. Subtle camera movement, gentle animation."


async def generate_single_video(
    image_url: str,
    motion_prompt: str,
    duration_seconds: float,
    model: str,
    semaphore: asyncio.Semaphore,
) -> str:
    import fal_client

    async with semaphore:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = await fal_client.run_async(
                    model,
                    arguments={
                        "image_url": image_url,
                        "prompt": motion_prompt,
                        "num_frames": min(int(duration_seconds * 8), 48),
                    },
                )
                return result["video"]["url"]
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 5 * (attempt + 1)
                    print(f"  Retry {attempt + 1} after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    raise


async def upload_image_to_fal(image_path: Path) -> str:
    import fal_client
    url = await fal_client.upload_file_async(image_path)
    return url


async def generate_all_videos(
    scenes: list[dict],
    image_files: list[Path],
    model: str,
    max_parallel: int,
) -> list[str]:
    semaphore = asyncio.Semaphore(max_parallel)

    print("  Uploading images to fal.ai...")
    upload_tasks = [upload_image_to_fal(img) for img in image_files]
    image_urls = await asyncio.gather(*upload_tasks, return_exceptions=True)

    tasks = []
    for i, (scene, image_url) in enumerate(zip(scenes, image_urls)):
        if isinstance(image_url, Exception):
            print(f"  ERROR uploading image for scene {i+1}: {image_url}")
            tasks.append(asyncio.coroutine(lambda: None)())
            continue
        motion_prompt = build_motion_prompt(scene)
        duration = scene.get("duration_seconds", 5)
        task = generate_single_video(image_url, motion_prompt, duration, model, semaphore)
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    urls = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  ERROR generating video for scene {i+1}: {result}")
            urls.append(None)
        else:
            urls.append(result)
    return urls


def create_fallback_clip(image_path: Path, duration: float, output_path: Path) -> Path:
    """Ken Burns effect fallback using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", f"zoompan=z='min(zoom+0.001,1.3)':d={int(duration*24)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def main():
    args = parse_args()
    config = load_config()
    os.environ["FAL_KEY"] = config["fal_key"]

    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    images_dir = Path(args.images_dir)
    output_dir = Path(args.output_dir)
    videos_dir = ensure_dir(output_dir / "videos")

    model = args.model or config["default_video_model"]
    scenes = script["scenes"]
    image_files = get_scene_files(images_dir, "scene", "png")

    if len(image_files) != len(scenes):
        print(f"WARNING: {len(image_files)} images for {len(scenes)} scenes")

    state = StateManager()
    state.update_step("step-03-video-animation", "running")

    print(f"Generating {len(image_files)} video clips using {model}...")
    start_time = time.time()

    video_urls = asyncio.run(generate_all_videos(scenes, image_files, model, args.max_parallel))

    video_paths = []
    for i, (url, scene) in enumerate(zip(video_urls, scenes)):
        clip_path = videos_dir / f"clip_{i+1:02d}.mp4"
        if url:
            download_file(url, clip_path)
            video_paths.append(str(clip_path))
            print(f"  Clip {i+1}: saved to {clip_path.name}")
        else:
            print(f"  Clip {i+1}: generation failed, creating fallback...")
            if i < len(image_files):
                create_fallback_clip(image_files[i], scene.get("duration_seconds", 5), clip_path)
                video_paths.append(str(clip_path))
                print(f"  Clip {i+1}: fallback saved to {clip_path.name}")
            else:
                video_paths.append(None)

    elapsed = time.time() - start_time
    successful = sum(1 for p in video_paths if p)
    print(f"\nCompleted: {successful}/{len(scenes)} video clips in {elapsed:.1f}s")

    state.update_step("step-03-video-animation", "completed", {"video_paths": video_paths})


if __name__ == "__main__":
    main()
