#!/usr/bin/env python3
"""Remove watermarks from video clips by cropping the edge that contains the watermark.

The script automatically picks the least-destructive cut direction:
  - If the watermark is wider than it is tall  → horizontal crop (thin top/bottom strip)
  - If the watermark is taller than it is wide → vertical crop   (thin left/right strip)

Usage examples:
  # Watermark occupies ~15% of width and ~8% of height in top-left corner
  # → auto picks horizontal crop (8% strip from top, scale back)
  python scripts/remove_watermark.py \\
      --frames-dir output/myvideo/amv1/frames \\
      --corner top-left \\
      --crop-w 0.15 --crop-h 0.08

  # Single --crop-percent sets equal w/h (auto-detection still applies, tie → horizontal)
  python scripts/remove_watermark.py \\
      --frames-dir output/myvideo/amv1/frames \\
      --corner top-left \\
      --crop-percent 0.08
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_dimensions(path: str) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    w, h = result.stdout.strip().split(",")
    return int(w), int(h)


def build_vf(corner: str, crop_w: float, crop_h: float, W: int, H: int) -> tuple[str, str]:
    """Return (vf_string, direction) where direction is 'horizontal' or 'vertical'."""
    cw = int(W * crop_w)   # pixels to strip from the side
    ch = int(H * crop_h)   # pixels to strip from the top/bottom

    # Choose direction that removes the smaller fraction of total frame area
    if crop_h <= crop_w:
        direction = "horizontal"   # strip a thin band from top or bottom
        if corner in ("top-left", "top-right"):
            # crop away top `ch` rows: output starts at y=ch
            vf = f"crop={W}:{H - ch}:0:{ch},scale={W}:{H}"
        else:  # bottom-left, bottom-right
            # crop away bottom `ch` rows: output starts at y=0
            vf = f"crop={W}:{H - ch}:0:0,scale={W}:{H}"
    else:
        direction = "vertical"     # strip a thin band from left or right
        if corner in ("top-left", "bottom-left"):
            # crop away left `cw` columns: output starts at x=cw
            vf = f"crop={W - cw}:{H}:{cw}:0,scale={W}:{H}"
        else:  # top-right, bottom-right
            # crop away right `cw` columns: output starts at x=0
            vf = f"crop={W - cw}:{H}:0:0,scale={W}:{H}"

    return vf, direction


def process_clip(input_path: str, output_path: str, corner: str,
                 crop_w: float, crop_h: float) -> tuple[bool, str]:
    W, H = get_dimensions(input_path)
    vf, direction = build_vf(corner, crop_w, crop_h, W, H)

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path,
         "-vf", vf,
         "-c:v", "libx264", "-preset", "fast", "-crf", "18",
         "-c:a", "copy",
         output_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"    ffmpeg error: {result.stderr[-400:]}", file=sys.stderr)
    return result.returncode == 0, direction


def main():
    parser = argparse.ArgumentParser(
        description="Remove watermark by cropping the least-destructive edge and scaling back."
    )
    parser.add_argument("--frames-dir", required=True,
                        help="Directory containing clip files to process")
    parser.add_argument("--corner", required=True,
                        choices=["top-left", "top-right", "bottom-left", "bottom-right"],
                        help="Corner where the watermark is located")

    size_group = parser.add_mutually_exclusive_group(required=True)
    size_group.add_argument("--crop-percent", type=float,
                            help="Single fraction for both width and height (square watermark region)")
    size_group.add_argument("--crop-w", type=float,
                            help="Fraction of frame WIDTH the watermark occupies (use with --crop-h)")
    parser.add_argument("--crop-h", type=float,
                        help="Fraction of frame HEIGHT the watermark occupies (use with --crop-w)")

    args = parser.parse_args()

    if args.crop_w is not None and args.crop_h is None:
        parser.error("--crop-w requires --crop-h")

    if args.crop_percent is not None:
        crop_w = crop_h = args.crop_percent
    else:
        crop_w = args.crop_w
        crop_h = args.crop_h

    frames_dir = Path(args.frames_dir)
    if not frames_dir.exists():
        print(f"Error: directory not found: {frames_dir}", file=sys.stderr)
        sys.exit(1)

    clips = sorted(frames_dir.glob("*.mp4")) + sorted(frames_dir.glob("*.webm"))
    if not clips:
        print("No .mp4 or .webm clips found.", file=sys.stderr)
        sys.exit(1)

    direction = "horizontal" if crop_h <= crop_w else "vertical"
    print(f"Removing watermark from {args.corner} corner")
    print(f"  crop-w={crop_w:.0%}  crop-h={crop_h:.0%}  -> auto direction: {direction} crop")
    print(f"Processing {len(clips)} clip(s) in {frames_dir}...\n")

    ok_count = 0
    for clip in clips:
        tmp = clip.with_suffix(".wm_tmp.mp4")
        success, _ = process_clip(str(clip), str(tmp), args.corner, crop_w, crop_h)
        if success:
            tmp.replace(clip)
            print(f"  OK    {clip.name}")
            ok_count += 1
        else:
            tmp.unlink(missing_ok=True)
            print(f"  FAIL  {clip.name}", file=sys.stderr)

    print(f"\nDone. {ok_count}/{len(clips)} clips processed.")


if __name__ == "__main__":
    main()
