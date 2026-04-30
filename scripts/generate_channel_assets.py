"""
YouTube channel asset generator — profile picture and banner via DALL-E 3.

Reads brand config from channels/{slug}/channel.json and generates:
  - assets/profile.jpg  (1024×1024)
  - assets/banner.jpg   (2560×1440, upscaled from 1792×1024)

Bio texts are printed to console for copy-paste into YouTube Studio.

Usage:
    python scripts/generate_channel_assets.py --channel hakase-anime
    python scripts/generate_channel_assets.py --channel hakase-anime --regenerate
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, PROJECT_ROOT


def parse_args():
    parser = argparse.ArgumentParser(description="Generate YouTube channel assets via DALL-E 3")
    parser.add_argument("--channel", required=True, help="Channel slug (folder name under channels/)")
    parser.add_argument("--regenerate", action="store_true",
                        help="Regenerate even if assets already exist")
    return parser.parse_args()


def generate_image(client: OpenAI, prompt: str, size: str, quality: str, out_path: Path) -> Path:
    print(f"  Generating {out_path.name} ({size})...")
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt[:4000],
        size=size,
        quality=quality,
        n=1,
    )
    url = response.data[0].url
    urllib.request.urlretrieve(url, str(out_path))
    return out_path


def main():
    args = parse_args()
    config = load_config()

    api_key = config.get("openai_api_key")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        sys.exit(1)

    channel_dir = PROJECT_ROOT / "channels" / args.channel
    if not channel_dir.exists():
        print(f"ERROR: Channel folder not found: {channel_dir}")
        sys.exit(1)

    channel = json.loads((channel_dir / "channel.json").read_text(encoding="utf-8"))
    assets_dir = channel_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    prompts = channel.get("dalle_prompts", {})
    client = OpenAI(api_key=api_key)

    # --- Profile picture (1024×1024) ---
    profile_path = assets_dir / "profile.jpg"
    if not profile_path.exists() or args.regenerate:
        prompt = prompts.get("profile", f"Anime channel logo for {channel['name']}")
        try:
            tmp = assets_dir / "_profile_tmp.png"
            generate_image(client, prompt, "1024x1024", "standard", tmp)
            # Convert to JPEG
            from PIL import Image
            Image.open(tmp).convert("RGB").save(str(profile_path), "JPEG", quality=92, optimize=True)
            tmp.unlink(missing_ok=True)
            size_kb = profile_path.stat().st_size // 1024
            print(f"  Saved: {profile_path.name} ({size_kb} KB, 1024×1024)")
        except Exception as e:
            print(f"  ERROR generating profile: {e}")
    else:
        print(f"  Profile already exists (use --regenerate to overwrite)")

    # --- Banner (1792×1024 from DALL-E, upscaled to 2560×1440) ---
    banner_path = assets_dir / "banner.jpg"
    if not banner_path.exists() or args.regenerate:
        prompt = prompts.get("banner", f"YouTube channel banner for {channel['name']}, anime style")
        try:
            tmp = assets_dir / "_banner_tmp.png"
            generate_image(client, prompt, "1792x1024", "standard", tmp)
            from PIL import Image
            img = Image.open(tmp).convert("RGB")
            img = img.resize((2560, 1440), Image.LANCZOS)
            img.save(str(banner_path), "JPEG", quality=95, optimize=True)
            tmp.unlink(missing_ok=True)
            size_kb = banner_path.stat().st_size // 1024
            print(f"  Saved: {banner_path.name} ({size_kb} KB, 2560×1440)")
        except Exception as e:
            print(f"  ERROR generating banner: {e}")
    else:
        print(f"  Banner already exists (use --regenerate to overwrite)")

    # --- Print bio texts ---
    def _print(text: str):
        print(text.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))

    _print("\n" + "=" * 60)
    _print(f"Channel: {channel['name']}")
    _print("=" * 60)
    _print("\n[SHORT BIO — paste in YouTube Studio > Customization > Basic info]")
    _print(channel.get("bio_short", ""))
    _print("\n[LONG BIO — paste in the Description field]")
    _print(channel.get("bio_long", ""))
    _print("\n" + "=" * 60)
    _print(f"Assets saved to: {assets_dir}")


if __name__ == "__main__":
    main()
