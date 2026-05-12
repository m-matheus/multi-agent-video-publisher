"""
Video composition via FFmpeg for anime frame/clip based videos.
Combines anime clips + narration + effects (zoom, pan, transitions, overlays).

Usage:
    python scripts/compose_video.py --script-path output/run-001/script/script.json --frames-dir output/run-001/frames --audio-dir output/run-001/audio --output-dir output/run-001
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.config import load_config, get_ffmpeg_path
from scripts.utils.file_helpers import ensure_dir, get_scene_files
from scripts.utils.state_manager import StateManager

FFMPEG = None
FFPROBE = None


def _ffmpeg():
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = get_ffmpeg_path()
        # ffprobe lives next to ffmpeg when installed system-wide; use ffmpeg as fallback
    return FFMPEG


def _ffprobe():
    global FFPROBE
    if FFPROBE is None:
        import shutil
        p = shutil.which("ffprobe")
        if p:
            FFPROBE = p
        else:
            # Try sibling of the imageio-ffmpeg binary
            from pathlib import Path as _Path
            ffmpeg_bin = _Path(get_ffmpeg_path())
            for name in ("ffprobe.exe", "ffprobe"):
                candidate = ffmpeg_bin.parent / name
                if candidate.exists():
                    FFPROBE = str(candidate)
                    break
            if not FFPROBE:
                # Fall back to ffmpeg itself (it can read duration via -i + stderr parse)
                FFPROBE = get_ffmpeg_path()
    return FFPROBE


def find_system_font() -> str | None:
    """Find a bold/impact font file for text overlays."""
    import platform
    if platform.system() == "Windows":
        candidates = [
            "C:/Windows/Fonts/impact.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _pillow_available() -> bool:
    try:
        import PIL
        return True
    except ImportError:
        return False


_WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def make_drawtext_filter(text: str, font_path: str, position: str = "bottom",
                         start: float = 1.0, duration: float = 4.0,
                         fontsize: int = 72) -> str:
    """Build an FFmpeg drawtext filter string (legacy / generic use)."""
    esc_font = font_path.replace(":", "\\:")
    safe_text = text.replace("'", "").replace(":", " ").replace("\\", "")
    y_map = {"top": "120", "bottom": "h-170", "center": "(h-text_h)/2"}
    y_pos = y_map.get(position, "h-170")
    enable = f"between(t\\,{start}\\,{start + duration})"
    return (
        f"drawtext=fontfile='{esc_font}'"
        f":text='{safe_text}'"
        f":fontcolor=white"
        f":fontsize={fontsize}"
        f":x=(w-text_w)/2"
        f":y={y_pos}"
        f":shadowx=4:shadowy=4:shadowcolor=black@0.9"
        f":enable='{enable}'"
    )


def make_rank_badge_filters(rank: int, name: str, font_path: str,
                             start: float, duration: float) -> str:
    """Two stacked drawtext filters: gold rank number + white character name, bottom-left badge."""
    esc_font = font_path.replace(":", "\\:")
    safe_name = name.replace("'", "").replace(":", " ").replace("\\", "")
    enable = f"between(t\\,{start}\\,{start + duration})"
    rank_f = (
        f"drawtext=fontfile='{esc_font}'"
        f":text='#{rank}'"
        f":fontcolor=0xFFD700"
        f":fontsize=130"
        f":x=50"
        f":y=h-260"
        f":box=1:boxcolor=0x00000088:boxborderw=22"
        f":shadowx=4:shadowy=4:shadowcolor=black@1.0"
        f":enable='{enable}'"
    )
    name_f = (
        f"drawtext=fontfile='{esc_font}'"
        f":text='{safe_name}'"
        f":fontcolor=white"
        f":fontsize=76"
        f":x=50"
        f":y=h-130"
        f":box=1:boxcolor=0x00000077:boxborderw=16"
        f":shadowx=3:shadowy=3:shadowcolor=black@0.9"
        f":enable='{enable}'"
    )
    return rank_f + "," + name_f


def make_intro_overlay_filters(font_path: str,
                                q_start: float = 1.0, q_dur: float = 6.5) -> str:
    """'CANT WAIT FOR / SOLO LEVELING S3?' centered on the intro scene."""
    esc_font = font_path.replace(":", "\\:")
    eq = f"between(t\\,{q_start}\\,{q_start + q_dur})"
    line1 = (
        f"drawtext=fontfile='{esc_font}':text='CANT WAIT FOR'"
        f":fontcolor=white:fontsize=90"
        f":x=(w-text_w)/2:y=(h/2-110)"
        f":box=1:boxcolor=0x000000AA:boxborderw=22"
        f":shadowx=4:shadowy=4:shadowcolor=black@0.9:enable='{eq}'"
    )
    line2 = (
        f"drawtext=fontfile='{esc_font}':text='SOLO LEVELING S3?'"
        f":fontcolor=0xFF3333:fontsize=114"
        f":x=(w-text_w)/2:y=(h/2+20)"
        f":box=1:boxcolor=0x000000AA:boxborderw=22"
        f":shadowx=5:shadowy=5:shadowcolor=black@1.0:enable='{eq}'"
    )
    return line1 + "," + line2


def make_intro_hook_filter(font_path: str, text: str, start: float = 0.5, duration: float = 7.5) -> str:
    """Large centered hook text for the intro scene (generic single-line hook)."""
    esc_font = font_path.replace(":", "\\:")
    safe_text = text.replace("'", "").replace(":", " ").replace("\\", "") if text else "WATCH TILL THE END"
    enable = f"between(t\\,{start}\\,{start + duration})"
    return (
        f"drawtext=fontfile='{esc_font}':text='{safe_text}'"
        f":fontcolor=white:fontsize=100"
        f":x=(w-text_w)/2:y=(h/2-60)"
        f":box=1:boxcolor=0x000000AA:boxborderw=22"
        f":shadowx=5:shadowy=5:shadowcolor=black@1.0:enable='{enable}'"
    )


def make_cta_filter(font_path: str, start: float, duration: float) -> str:
    """Red 'LIKE & SUBSCRIBE' banner centered at the bottom."""
    esc_font = font_path.replace(":", "\\:")
    enable = f"between(t\\,{start}\\,{start + duration})"
    return (
        f"drawtext=fontfile='{esc_font}'"
        f":text='LIKE  &  SUBSCRIBE'"
        f":fontcolor=white"
        f":fontsize=82"
        f":x=(w-text_w)/2"
        f":y=h-140"
        f":box=1:boxcolor=0xFF0000CC:boxborderw=28"
        f":shadowx=3:shadowy=3:shadowcolor=black@0.8"
        f":enable='{enable}'"
    )


def create_rank_card_image(
    scene: dict,
    background_clip: "Path",
    output_png: "Path",
    width: int = 1920,
    height: int = 1080,
) -> "Path | None":
    """
    Generate a rank card PNG using Pillow:
    - Extracts a frame from background_clip (the AMV for this rank)
    - Applies heavy blur + dark overlay + radial vignette
    - Draws rank number (gold, glow) and anime name (white, bold) centered
    Returns output_png or None on any failure.
    """
    try:
        from PIL import Image, ImageFilter, ImageDraw, ImageFont
    except ImportError:
        return None

    rank = scene.get("rank", "?")
    anime_name = scene.get("name", "")

    # --- Extract frame at 1s from the AMV clip ---
    frame_tmp = output_png.parent / f"_rankframe_{output_png.stem}.png"
    cmd = [
        _ffmpeg(), "-y", "-ss", "1", "-i", str(background_clip), "-vframes", "1",
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
        str(frame_tmp),
    ]
    if subprocess.run(cmd, capture_output=True).returncode != 0 or not frame_tmp.exists():
        return None

    img = Image.open(frame_tmp).convert("RGBA")
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    frame_tmp.unlink(missing_ok=True)

    # --- Heavy blur ---
    img = img.filter(ImageFilter.GaussianBlur(radius=22))

    # --- Dark overlay ---
    img = Image.alpha_composite(img, Image.new("RGBA", (width, height), (0, 0, 0, 155)))

    # --- Radial vignette (dark edges) ---
    try:
        import numpy as np
        Y, X = np.ogrid[0:height, 0:width]
        dist = np.sqrt(((X - width / 2) / (width / 2)) ** 2 + ((Y - height / 2) / (height / 2)) ** 2)
        alpha = np.clip(dist * 195, 0, 195).astype(np.uint8)
        vig = np.zeros((height, width, 4), dtype=np.uint8)
        vig[:, :, 3] = alpha
        img = Image.alpha_composite(img, Image.fromarray(vig))
    except ImportError:
        draw_vig = ImageDraw.Draw(img)
        for i in range(80):
            a = int(180 * (1 - i / 80) ** 2)
            draw_vig.rectangle([i, i, width - i, height - i], outline=(0, 0, 0, a), width=2)

    # --- Fonts ---
    font_file = find_system_font()
    try:
        font_rank = ImageFont.truetype(font_file, 300) if font_file else ImageFont.load_default()
        font_name = ImageFont.truetype(font_file, 90) if font_file else ImageFont.load_default()
    except Exception:
        font_rank = ImageFont.load_default()
        font_name = ImageFont.load_default()

    rank_text = f"#{rank}"
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def measure(text, font):
        try:
            b = dummy_draw.textbbox((0, 0), text, font=font)
            return b[2] - b[0], b[3] - b[1]
        except AttributeError:
            return font.getsize(text)

    rw, rh = measure(rank_text, font_rank)
    nw, nh = measure(anime_name, font_name) if anime_name else (0, 0)

    total_h = rh + (24 + nh if anime_name else 0)
    rank_x = (width - rw) // 2
    rank_y = (height - total_h) // 2 - 20

    # --- Glow layer ---
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for dx in range(-18, 19, 6):
        for dy in range(-18, 19, 6):
            gd.text((rank_x + dx, rank_y + dy), rank_text, font=font_rank, fill=(255, 210, 0, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=14))
    img = Image.alpha_composite(img, glow)

    # --- Sharp text ---
    txt = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    td = ImageDraw.Draw(txt)
    td.text((rank_x + 7, rank_y + 7), rank_text, font=font_rank, fill=(0, 0, 0, 210))
    td.text((rank_x, rank_y), rank_text, font=font_rank, fill=(255, 215, 0, 255))
    if anime_name:
        nx = (width - nw) // 2
        ny = rank_y + rh + 24
        td.text((nx + 4, ny + 4), anime_name, font=font_name, fill=(0, 0, 0, 200))
        td.text((nx, ny), anime_name, font=font_name, fill=(255, 255, 255, 255))
    img = Image.alpha_composite(img, txt)

    img.convert("RGB").save(str(output_png))
    return output_png


def create_rank_transition_clip(scene: dict, output_path: Path, font_path: str | None, shorts: bool = False, background_clip: "Path | None" = None) -> Path:
    """Generate an animated rank reveal with blurred AMV background (Pillow) or black card fallback."""
    duration = scene.get("duration_seconds", 2.5)
    rank = scene.get("rank", "?")
    anime_name = scene.get("name", "")
    fade_out_start = max(0.0, duration - 0.3)
    canvas = "1080x1920" if shorts else "1920x1080"
    out_w, out_h = (1080, 1920) if shorts else (1920, 1080)

    # --- Pillow path: blurred AMV frame background ---
    if background_clip and Path(background_clip).exists() and _pillow_available():
        bg_png = output_path.parent / f"_rankbg_{output_path.stem}.png"
        bg_image = create_rank_card_image(scene, Path(background_clip), bg_png, out_w, out_h)
        if bg_image and bg_image.exists():
            vf = (
                f"scale={out_w}:{out_h},"
                f"fade=t=in:st=0:d=0.2,"
                f"fade=t=out:st={fade_out_start:.2f}:d=0.3"
            )
            cmd = [
                _ffmpeg(), "-y",
                "-loop", "1", "-i", str(bg_image),
                "-vf", vf,
                "-t", str(duration),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True)
            bg_png.unlink(missing_ok=True)
            if result.returncode == 0:
                return output_path

    # --- Fallback: black card with FFmpeg drawtext ---
    vf_parts = []
    if font_path:
        esc_font = font_path.replace(":", "\\:")
        # Anime name at top (white, smaller)
        if anime_name:
            safe_name = anime_name.replace("'", "").replace(":", " ")
            vf_parts.append(
                f"drawtext=fontfile='{esc_font}':text='{safe_name}'"
                f":fontcolor=white@0.9:fontsize=72"
                f":x=(w-text_w)/2:y=(h/2-260)"
                f":shadowx=4:shadowy=4:shadowcolor=black@0.9"
            )
        # Rank number in gold (large, center)
        vf_parts.append(
            f"drawtext=fontfile='{esc_font}':text='#{rank}'"
            f":fontcolor=#FFD700:fontsize=280"
            f":x=(w-text_w)/2:y=(h/2-140)"
            f":shadowx=8:shadowy=8:shadowcolor=black@0.8"
        )
    vf_parts.append("fade=t=in:st=0:d=0.2")
    vf_parts.append(f"fade=t=out:st={fade_out_start:.2f}:d=0.3")

    cmd = [
        _ffmpeg(), "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={canvas}:d={duration}:r=24",
        "-vf", ",".join(vf_parts),
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def create_shorts_cta_clip(scene: dict, output_path: Path, font_path: str | None) -> Path:
    """Generate a Shorts CTA card: dark background + 'FULL VIDEO ON THE CHANNEL' text."""
    duration = scene.get("duration_seconds", 3.0)
    cta_text = scene.get("cta_text", "FULL VIDEO ON THE CHANNEL")
    fade_out_start = max(0.0, duration - 0.3)

    vf_parts = []
    if font_path:
        esc_font = font_path.replace(":", "\\:")
        safe_text = cta_text.replace("'", "").replace(":", " ")
        vf_parts.append(
            f"drawtext=fontfile='{esc_font}':text='{safe_text}'"
            f":fontcolor=white:fontsize=68"
            f":x=(w-text_w)/2:y=(h/2-60)"
            f":box=1:boxcolor=0xCC0000BB:boxborderw=24"
            f":shadowx=4:shadowy=4:shadowcolor=black@0.9"
        )
        vf_parts.append(
            f"drawtext=fontfile='{esc_font}':text='Check description below!'"
            f":fontcolor=white@0.85:fontsize=44"
            f":x=(w-text_w)/2:y=(h/2+60)"
            f":shadowx=3:shadowy=3:shadowcolor=black@0.8"
        )
    vf_parts.append("fade=t=in:st=0:d=0.2")
    vf_parts.append(f"fade=t=out:st={fade_out_start:.2f}:d=0.3")

    cmd = [
        _ffmpeg(), "-y",
        "-f", "lavfi", "-i", "color=c=0x0d0d0d:s=1080x1920:d={dur}:r=24".format(dur=duration),
        "-vf", ",".join(vf_parts),
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def get_scene_overlay(scene: dict, scene_idx: int, total_scenes: int, title: str, shorts: bool = False) -> dict | None:
    """Determine what text overlay to apply based on scene position and narration."""
    if scene.get("scene_type") == "rank_transition":
        return None
    # No CTA overlay for Shorts — YouTube adds its own UI elements
    if shorts:
        return None
    if scene_idx == total_scenes - 1:
        return {"style": "cta", "start": 4.0, "duration": 8.0}
    return None


def concat_clips_for_scene(clips: list, output_path, ffmpeg_path: str) -> "Path":
    """Concatenate multiple video clips into one file using ffmpeg concat demuxer."""
    from pathlib import Path
    output_path = Path(output_path)
    if len(clips) == 1:
        return Path(clips[0])
    list_path = output_path.with_suffix(".concat.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{Path(c).resolve().as_posix()}'\n")
    cmd = [ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_path), "-c", "copy", str(output_path)]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    list_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed: {result.stderr.decode(errors='replace')[-400:]}")
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(description="Compose final video with FFmpeg")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--frames-dir", required=True, help="Path to anime frames/clips directory")
    parser.add_argument("--audio-dir", required=True, help="Path to audio directory")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--bgm-path", default=None, help="Optional background music path")
    parser.add_argument("--bgm-volume", type=float, default=0.15, help="BGM volume (0-1)")
    parser.add_argument("--srt-path", default=None, help="Optional SRT subtitle file to embed as a soft track")
    parser.add_argument("--endcard-path", default=None,
                        help="Endcard image to append (auto-detected from channels/ if not set)")
    parser.add_argument("--no-endcard", action="store_true",
                        help="Disable endcard even if auto-detected")
    parser.add_argument("--endcard-duration", type=float, default=20.0,
                        help="Duration in seconds for the endcard clip (default: 20s)")
    parser.add_argument("--zoom-crop", action="store_true",
                        help="Apply 7%% zoom + center crop on video clips to remove edge watermarks")
    parser.add_argument("--shorts", action="store_true",
                        help="Output vertical 1080x1920 format for YouTube Shorts")
    parser.add_argument("--captions-path", default=None,
                        help="Path to ASS subtitle file to burn into the final video (kinetic captions)")
    parser.add_argument("--amv-base-dir", default=None,
                        help="Base directory containing amv1/, amv2/, ... subdirs. "
                             "When set, scenes with an 'amv' field pull clips from amvN/frames/ "
                             "instead of the global --frames-dir.")
    # Legacy support for AI-generated video clips
    parser.add_argument("--videos-dir", default=None, help="Path to AI-generated video clips (legacy mode)")
    return parser.parse_args()


def get_video_duration(video_path: Path) -> float:
    import shutil
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    else:
        # Use ffmpeg -i and parse duration from stderr
        result = subprocess.run(
            [_ffmpeg(), "-i", str(video_path)],
            capture_output=True, text=True,
        )
        import re
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if m:
            h, m2, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + m2 * 60 + s
        raise RuntimeError(f"Could not determine duration of {video_path}")


def get_media_info(file_path: Path) -> dict:
    """Get media info (duration, width, height, has_video, has_audio)."""
    import shutil
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(file_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
    else:
        result = subprocess.run([_ffmpeg(), "-i", str(file_path)], capture_output=True, text=True)
        import re
        duration = 0.0
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if m:
            h, m2, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            duration = h * 3600 + m2 * 60 + s
        wh = re.search(r"(\d{2,5})x(\d{2,5})", result.stderr)
        width = int(wh.group(1)) if wh else 1920
        height = int(wh.group(2)) if wh else 1080
        has_video = "Video:" in result.stderr
        has_audio = "Audio:" in result.stderr
        return {"duration": duration, "width": width, "height": height, "has_video": has_video, "has_audio": has_audio}

    has_video = any(s["codec_type"] == "video" for s in info.get("streams", []))
    has_audio = any(s["codec_type"] == "audio" for s in info.get("streams", []))
    duration = float(info.get("format", {}).get("duration", 0))

    video_stream = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), None)
    width = int(video_stream.get("width", 1920)) if video_stream else 1920
    height = int(video_stream.get("height", 1080)) if video_stream else 1080

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_video": has_video,
        "has_audio": has_audio,
    }


def create_scene_clip(
    input_path: Path | None,
    output_path: Path,
    target_duration: float,
    effect: str = "kenburns",
    text_overlay: dict | None = None,
    scene_type: str = "normal",
    scene: dict | None = None,
    zoom_crop: bool = False,
    shorts: bool = False,
    background_clip: "Path | None" = None,
) -> Path:
    """
    Create a scene clip from input media with effects applied.
    Handles: video clips (trim/loop), static images (ken burns), gifs (loop).
    For rank_transition scenes, generates an animated rank reveal (no input_path needed).
    Intro scenes use a more aggressive Ken Burns zoom.
    Optionally burns in a text overlay (title card, character name, CTA).
    """
    font_path = find_system_font()

    # Rank transition: generated clip — no source media required
    if scene_type == "rank_transition":
        return create_rank_transition_clip(scene or {}, output_path, font_path,
                                            shorts=shorts, background_clip=background_clip)

    # Shorts CTA: generated clip — no source media required
    if scene_type == "shorts_cta":
        return create_shorts_cta_clip(scene or {}, output_path, font_path)

    out_w, out_h = (1080, 1920) if shorts else (1920, 1080)

    # Intro scenes get a faster, more dramatic Ken Burns zoom
    zoom_speed = 0.002 if scene_type == "intro" else 0.0008
    zoom_max = 1.5 if scene_type == "intro" else 1.2

    ext = input_path.suffix.lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp")
    is_gif = ext == ".gif"

    # Build optional drawtext suffix
    drawtext = ""
    # Scene-level overlay_text: explicit text burned into the clip (works in shorts too)
    if scene and scene.get("overlay_text") and font_path:
        esc_font = font_path.replace(":", "\\:")
        safe_overlay = scene["overlay_text"].replace("'", "").replace(":", " ").replace("\\", "")
        drawtext += (
            f",drawtext=fontfile='{esc_font}'"
            f":text='{safe_overlay}'"
            f":fontcolor=white"
            f":fontsize=80"
            f":x=(w-text_w)/2"
            f":y=h*2/3"
            f":box=1:boxcolor=0xCC0000CC:boxborderw=26"
            f":shadowx=4:shadowy=4:shadowcolor=black@0.9"
            f":enable='between(t\\,0.5\\,{target_duration})'"
        )
    if text_overlay:
        font_path = find_system_font()
        if font_path:
            style = text_overlay.get("style", "basic")
            if style == "rank":
                drawtext = "," + make_rank_badge_filters(
                    text_overlay["rank"], text_overlay["name"], font_path,
                    text_overlay.get("start", 1.0), text_overlay.get("duration", 5.5),
                )
            elif style == "cta":
                drawtext = "," + make_cta_filter(
                    font_path,
                    text_overlay.get("start", 4.0), text_overlay.get("duration", 8.0),
                )
            elif style == "intro_question":
                drawtext = "," + make_intro_overlay_filters(font_path)
            elif style == "intro_hook":
                drawtext = "," + make_intro_hook_filter(
                    font_path,
                    text_overlay.get("text", ""),
                    text_overlay.get("start", 0.5), text_overlay.get("duration", 7.5),
                )
            else:
                drawtext = "," + make_drawtext_filter(
                    text=text_overlay["text"],
                    font_path=font_path,
                    position=text_overlay.get("position", "bottom"),
                    start=text_overlay.get("start", 1.0),
                    duration=text_overlay.get("duration", 4.0),
                    fontsize=text_overlay.get("fontsize", 72),
                )

    if is_image:
        vf = (
            f"zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d={int(target_duration*24)}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={out_w}x{out_h},fps=24{drawtext}"
        )
        cmd = [
            _ffmpeg(), "-y",
            "-loop", "1", "-i", str(input_path),
            "-vf", vf,
            "-t", str(target_duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            str(output_path),
        ]
    elif is_gif or ext == ".webm":
        if shorts:
            # Letterbox: fit full 16:9 frame inside 9:16 with black bars
            vf = f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black,fps=24{drawtext}"
        else:
            if zoom_crop:
                base_scale = f"scale=2150:1210:force_original_aspect_ratio=increase,crop=1920:1080:0:0"
            else:
                base_scale = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
            vf = f"{base_scale},fps=24{drawtext}"
        cmd = [
            _ffmpeg(), "-y",
            "-stream_loop", "-1", "-i", str(input_path),
            "-t", str(target_duration),
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            "-an",
            str(output_path),
        ]
    else:
        # Video clip: trim or loop to target duration
        try:
            clip_duration = get_video_duration(input_path)
        except Exception:
            clip_duration = target_duration

        if shorts:
            # Letterbox: fit full 16:9 frame inside 9:16 with black bars
            vf = f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black,fps=24{drawtext}"
        else:
            if zoom_crop:
                base_scale = f"scale=2150:1210:force_original_aspect_ratio=increase,crop=1920:1080:0:0"
            else:
                base_scale = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
            vf = f"{base_scale},fps=24{drawtext}"

        if clip_duration >= target_duration:
            cmd = [
                _ffmpeg(), "-y",
                "-i", str(input_path),
                "-t", str(target_duration),
                "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                "-an",
                str(output_path),
            ]
        else:
            cmd = [
                _ffmpeg(), "-y",
                "-stream_loop", "-1", "-i", str(input_path),
                "-t", str(target_duration),
                "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                "-an",
                str(output_path),
            ]

    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def build_synced_narration(segments_dir: Path, scenes: list[dict], output_path: Path) -> tuple:
    """
    Rebuild narration audio locked to each scene's effective duration.

    rank_transition scenes: instead of silence, play the opening of the NEXT scene's
    narration so the rank announcement ("Number 5 — My Hero Academia") is heard while
    the black card is visible. The following scene's audio then skips the borrowed portion.

    Effective duration = max(script duration_seconds, remaining TTS audio length),
    so speech is never cut short when TTS runs longer than the script estimate.
    Returns (audio_path, effective_durations_list).
    """
    tmp_dir = output_path.parent / "_narr_tmp"
    tmp_dir.mkdir(exist_ok=True)

    # Seconds of silence added before the rank announcement ("Number X.") on the rank card.
    PRE_RANK_SILENCE = 0.3
    # Seconds of trailing silence added to the last normal scene before each rank card.
    POST_RANK_SILENCE = 0.5

    # Identify normal scenes immediately preceding a rank_transition.
    pre_transition_indices: set[int] = set()
    for i, scene in enumerate(scenes):
        if scene.get("scene_type") == "rank_transition" and i > 0:
            if scenes[i - 1].get("scene_type") != "rank_transition":
                pre_transition_indices.add(i - 1)

    padded_files = []
    effective_durations = []

    for i, scene in enumerate(scenes):
        seg_path = segments_dir / f"segment_{i+1:02d}.mp3"
        script_dur = float(scene["duration_seconds"])
        padded_path = tmp_dir / f"padded_{i+1:02d}.mp3"

        if scene.get("scene_type") == "rank_transition":
            # Play PRE_RANK_SILENCE then the rank card's own announcement segment.
            effective_dur = script_dur
            if seg_path.exists():
                ann_dur = max(0.0, effective_dur - PRE_RANK_SILENCE)
                cmd = [
                    _ffmpeg(), "-y",
                    "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
                    "-i", str(seg_path),
                    "-filter_complex", (
                        f"[0:a]atrim=end={PRE_RANK_SILENCE}[pre];"
                        f"[1:a]atrim=end={ann_dur}[ann];"
                        f"[pre][ann]concat=n=2:v=0:a=1[combined];"
                        f"[combined]apad=whole_dur={effective_dur},atrim=end={effective_dur}[out]"
                    ),
                    "-map", "[out]",
                    "-c:a", "libmp3lame", "-ar", "24000", "-ac", "1", "-q:a", "4",
                    str(padded_path),
                ]
            else:
                cmd = [
                    _ffmpeg(), "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", str(effective_dur),
                    "-c:a", "libmp3lame", "-ar", "24000", "-ac", "1", "-q:a", "4",
                    str(padded_path),
                ]
        else:
            if seg_path.exists():
                try:
                    actual_dur = get_video_duration(seg_path)
                except Exception:
                    actual_dur = script_dur
                trailing = POST_RANK_SILENCE if i in pre_transition_indices else 0.0
                effective_dur = max(script_dur, actual_dur) + trailing
                af = f"apad=whole_dur={effective_dur},atrim=end={effective_dur},aresample=24000"
                cmd = [
                    _ffmpeg(), "-y", "-i", str(seg_path),
                    "-af", af,
                    "-c:a", "libmp3lame", "-ar", "24000", "-ac", "1", "-q:a", "4",
                    str(padded_path),
                ]
            else:
                effective_dur = script_dur
                cmd = [
                    _ffmpeg(), "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", str(effective_dur),
                    "-c:a", "libmp3lame", "-ar", "24000", "-ac", "1", "-q:a", "4",
                    str(padded_path),
                ]

        effective_durations.append(effective_dur)
        subprocess.run(cmd, capture_output=True, check=True)
        padded_files.append(padded_path)

    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{str(f.absolute())}'" for f in padded_files) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c:a", "copy", str(output_path)],
        capture_output=True, check=True,
    )
    import shutil as _sh
    _sh.rmtree(tmp_dir, ignore_errors=True)
    return output_path, effective_durations


def build_final_video(
    scene_clips: list[Path],
    audio_path: Path,
    output_path: Path,
    transitions: list[str],
    bgm_path: Path = None,
    bgm_volume: float = 0.15,
    captions_path: Path = None,
) -> list[str]:
    """Build FFmpeg command to concatenate scene clips with audio."""
    cmd = [_ffmpeg(), "-y"]

    for clip in scene_clips:
        cmd.extend(["-i", str(clip)])
    cmd.extend(["-i", str(audio_path)])
    if bgm_path:
        # -stream_loop -1 loops the BGM infinitely so it never becomes the shortest stream
        cmd.extend(["-stream_loop", "-1", "-i", str(bgm_path)])

    n_clips = len(scene_clips)
    audio_idx = n_clips
    bgm_idx = n_clips + 1 if bgm_path else None

    filter_parts = []

    # Clips are already normalized to 1920x1080@24fps by create_scene_clip — skip redundant rescaling.
    # Just setsar=1 to guarantee SAR consistency before concat.
    for i in range(n_clips):
        filter_parts.append(f"[{i}:v]setsar=1[v{i}]")

    # Concatenate
    if n_clips == 1:
        filter_parts.append("[v0]copy[vconcat]")
    else:
        concat_inputs = "".join(f"[v{i}]" for i in range(n_clips))
        filter_parts.append(f"{concat_inputs}concat=n={n_clips}:v=1:a=0[vconcat]")

    # Burn kinetic captions if provided
    if captions_path:
        ass_path = Path(captions_path).resolve().as_posix()
        # FFmpeg ass filter requires colon after drive letter to be escaped on Windows
        import re
        ass_path = re.sub(r"^([A-Za-z]):/", r"\1\\:/", ass_path)
        filter_parts.append(f"[vconcat]ass='{ass_path}'[vout]")
    else:
        filter_parts.append("[vconcat]copy[vout]")

    # Audio mixing
    if bgm_path:
        filter_parts.append(f"[{audio_idx}:a]volume=1.0[narration]")
        filter_parts.append(f"[{bgm_idx}:a]volume={bgm_volume}[music]")
        filter_parts.append("[narration][music]amix=inputs=2:duration=shortest[aout]")
    else:
        filter_parts.append(f"[{audio_idx}:a]acopy[aout]")

    filter_complex = ";\n".join(filter_parts)
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", "[vout]", "-map", "[aout]"])
    cmd.extend([
        "-c:v", "libx264", "-preset", "superfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k",
        "-r", "24",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ])
    return cmd


def validate_output(output_path: Path) -> bool:
    if not output_path.exists():
        return False
    if output_path.stat().st_size < 1000:
        return False
    try:
        get_video_duration(output_path)
        return True
    except Exception:
        return False


def find_scene_files(frames_dir: Path) -> list[Path]:
    """Find all scene files in frames directory, sorted by name."""
    extensions = (".mp4", ".webm", ".gif", ".png", ".jpg", ".jpeg", ".mkv")
    files = []
    for f in sorted(frames_dir.iterdir()):
        if f.suffix.lower() in extensions:
            files.append(f)
    return files


def main():
    args = parse_args()

    # Auto-detect endcard if not explicitly provided
    if not args.endcard_path and not args.no_endcard:
        project_root = Path(__file__).parent.parent
        default_endcard = project_root / "channels" / "hakase-anime" / "assets" / "endcard.png"
        if default_endcard.exists():
            args.endcard_path = str(default_endcard)

    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    final_dir = ensure_dir(output_dir / "final")
    temp_dir = ensure_dir(output_dir / "temp_clips")

    # Determine source: frames (anime clips) or videos (AI-generated)
    if args.frames_dir:
        source_dir = Path(args.frames_dir)
    elif args.videos_dir:
        source_dir = Path(args.videos_dir)
    else:
        # Auto-detect
        frames_path = output_dir / "frames"
        videos_path = output_dir / "videos"
        source_dir = frames_path if frames_path.exists() else videos_path

    audio_path = Path(args.audio_dir) / "narration_full.mp3"

    # If per-scene segments exist, rebuild a synced narration track so each
    # scene's narration is locked to its video cut (padded with silence to duration).
    segments_dir = Path(args.audio_dir) / "narration_segments"
    if segments_dir.exists() and any(segments_dir.iterdir()):
        synced_path = Path(args.audio_dir) / "narration_synced.mp3"
        print("Building synced narration from per-scene segments...")
        audio_path, effective_durations = build_synced_narration(segments_dir, script["scenes"], synced_path)
        print(f"  Synced narration: {synced_path.name}")
        # Extend scene durations to match actual TTS so video clips are never shorter than the speech
        for scene, eff_dur in zip(script["scenes"], effective_durations):
            if eff_dur > scene["duration_seconds"]:
                scene["duration_seconds"] = eff_dur

    if not source_dir.exists():
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)
    if not audio_path.exists():
        print(f"ERROR: narration_full.mp3 not found in {args.audio_dir}")
        sys.exit(1)

    source_files = find_scene_files(source_dir)
    scenes = script["scenes"]
    transitions = [scene.get("transition", "cut") for scene in scenes]
    non_transition_count = sum(1 for s in scenes if s.get("scene_type") != "rank_transition")
    if not source_files and non_transition_count > 0:
        print(f"ERROR: No media files found in {source_dir}")
        sys.exit(1)

    # Per-AMV clip routing: if --amv-base-dir is set, load clip lists per amv number
    amv_files: dict[int, list[Path]] = {}
    amv_idx: dict[int, int] = {}
    amv_clip_durations: dict[int, list[float]] = {}
    if args.amv_base_dir:
        amv_base = Path(args.amv_base_dir)
        for n in range(1, 20):
            amv_frames = amv_base / f"amv{n}" / "frames"
            if amv_frames.exists():
                clips = find_scene_files(amv_frames)
                if clips:
                    amv_files[n] = clips
                    amv_idx[n] = 0
        if amv_files:
            print(f"Per-AMV routing enabled: " + ", ".join(f"amv{n}={len(v)} clips" for n, v in sorted(amv_files.items())))
            # Pre-load clip durations so we can consume the right number per scene
            amv_clip_durations: dict[int, list[float]] = {}
            for n, clips in amv_files.items():
                amv_clip_durations[n] = []
                for c in clips:
                    try:
                        amv_clip_durations[n].append(get_video_duration(c))
                    except Exception:
                        amv_clip_durations[n].append(10.0)

    state = StateManager()
    state.update_step("step-05-video-composition", "running")

    print(f"Composing video from {len(source_files)} clips + narration...")

    # Process each scene clip (normalize duration and resolution)
    scene_clips = []
    title = script.get("title", "")
    total_scenes = len(scenes)
    font_available = find_system_font() is not None
    if not font_available:
        print("  WARNING: No system font found — text overlays disabled")

    file_idx = 0
    for i, scene in enumerate(scenes):
        target_duration = scene.get("duration_seconds", 5)
        scene_type = scene.get("scene_type", "normal")
        amv_num = scene.get("amv")

        if scene_type in ("rank_transition", "shorts_cta"):
            source = None
            # For rank_transition, pick background from the scene's AMV pool (first clip)
            bg_clip = None
            if scene_type == "rank_transition":
                if amv_num and amv_num in amv_files:
                    bg_clip = amv_files[amv_num][0]
                elif source_files:
                    bg_clip = source_files[0]
        elif "clip_index" in scene and amv_num and amv_num in amv_files:
            bg_clip = None
            # Manual clip pin: use exact index from this AMV's pool
            clips = amv_files[amv_num]
            source = clips[scene["clip_index"] % len(clips)]
        elif amv_num and amv_num in amv_files:
            bg_clip = None
            # Per-AMV routing: consume enough clips to fill target_duration without looping
            clips = amv_files[amv_num]
            durations = amv_clip_durations.get(amv_num, [])
            idx = amv_idx[amv_num]
            selected, accumulated = [], 0.0
            j = idx
            while accumulated < target_duration and j < len(clips):
                selected.append(clips[j])
                accumulated += durations[j] if j < len(durations) else 10.0
                j += 1
            if not selected:
                selected = [clips[min(idx, len(clips) - 1)]]
                j = idx + 1
            amv_idx[amv_num] = j
            if len(selected) > 1:
                concat_out = temp_dir / f"concat_amv{amv_num}_{i:02d}.mp4"
                source = concat_clips_for_scene(selected, concat_out, _ffmpeg())
            else:
                source = selected[0]
        elif source_files:
            bg_clip = None
            source = source_files[min(file_idx, len(source_files) - 1)]
            file_idx += 1
        else:
            bg_clip = None
            source = None

        clip_path = temp_dir / f"processed_{i+1:02d}.mp4"
        overlay = get_scene_overlay(scene, i, total_scenes, title, shorts=args.shorts) if font_available else None
        if overlay:
            style = overlay.get("style", "basic")
            if style == "rank":
                overlay_label = f" [#{overlay['rank']} {overlay['name']}]"
            elif style == "cta":
                overlay_label = " [LIKE & SUBSCRIBE]"
            else:
                overlay_label = f" [{overlay.get('text', '')}]"
        else:
            overlay_label = ""

        if scene_type == "rank_transition":
            source_name = f"[RANK TRANSITION #{scene.get('rank', '?')}]"
        elif scene_type == "shorts_cta":
            source_name = "[SHORTS CTA]"
        else:
            source_name = source.name if source else "[none]"
        print(f"  Processing scene {i+1}: {source_name} -> {target_duration}s{overlay_label}")

        try:
            create_scene_clip(
                source, clip_path, target_duration,
                text_overlay=overlay, scene_type=scene_type, scene=scene,
                zoom_crop=args.zoom_crop, shorts=args.shorts,
                background_clip=bg_clip,
            )
            scene_clips.append(clip_path)
        except subprocess.CalledProcessError as e:
            print(f"  ERROR processing scene {i+1}: {e}")
            # Create a black frame fallback
            canvas = "1080x1920" if args.shorts else "1920x1080"
            cmd = [
                _ffmpeg(), "-y",
                "-f", "lavfi", "-i", f"color=c=black:s={canvas}:d={target_duration}:r=24",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(clip_path),
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            scene_clips.append(clip_path)

    # Append endcard if provided (skipped for Shorts)
    if args.endcard_path and not args.shorts:
        endcard_src = Path(args.endcard_path)
        if endcard_src.exists():
            endcard_clip_path = temp_dir / "endcard.mp4"
            print(f"  Processing endcard: {endcard_src.name} -> {args.endcard_duration}s")
            try:
                create_scene_clip(
                    endcard_src, endcard_clip_path, args.endcard_duration,
                    scene_type="normal", zoom_crop=False,
                )
                scene_clips.append(endcard_clip_path)
                # Extend narration with silence so audio covers the endcard
                extended_audio_path = Path(args.audio_dir) / "narration_extended.mp3"
                subprocess.run([
                    _ffmpeg(), "-y",
                    "-i", str(audio_path),
                    "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-filter_complex",
                    f"[1:a]atrim=end={args.endcard_duration}[silence];[0:a][silence]concat=n=2:v=0:a=1[aout]",
                    "-map", "[aout]",
                    "-c:a", "libmp3lame", "-ar", "24000", "-q:a", "4",
                    str(extended_audio_path),
                ], capture_output=True, check=True)
                audio_path = extended_audio_path
            except Exception as e:
                print(f"  WARNING: Could not process endcard: {e}")
        else:
            print(f"  WARNING: Endcard image not found: {endcard_src}")

    # Build and execute final composition
    output_path = final_dir / ("final_short.mp4" if args.shorts else "final_video.mp4")
    bgm_path = Path(args.bgm_path) if args.bgm_path else None
    srt_path = Path(args.srt_path) if args.srt_path else None

    print(f"  Composing final video...")
    # If SRT will be embedded, encode to a temp file first, then add subtitles on top
    encode_output = final_dir / "final_nosub_tmp.mp4" if (srt_path and srt_path.exists()) else output_path
    captions_path = Path(args.captions_path) if getattr(args, "captions_path", None) else None
    cmd = build_final_video(scene_clips, audio_path, encode_output, transitions, bgm_path, args.bgm_volume, captions_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            print(f"FFmpeg error:\n{result.stderr[-2000:]}")
            state.update_step("step-05-video-composition", "failed")
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: FFmpeg timed out after 60 minutes")
        state.update_step("step-05-video-composition", "failed")
        sys.exit(1)

    # Add soft subtitle track if requested
    if srt_path and srt_path.exists():
        sub_cmd = [
            _ffmpeg(), "-y",
            "-i", str(encode_output),
            "-i", str(srt_path),
            "-c", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=por",
            str(output_path),
        ]
        subprocess.run(sub_cmd, capture_output=True, check=True)
        encode_output.unlink(missing_ok=True)
        print(f"  Subtitles embedded from {srt_path.name}")

    if validate_output(output_path):
        duration = get_video_duration(output_path)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\nFinal video: {output_path.name} ({duration:.1f}s, {size_mb:.1f}MB)")
        state.update_step("step-05-video-composition", "completed", {
            "video_path": str(output_path),
            "duration": duration,
            "size_mb": round(size_mb, 2),
        })
    else:
        print("ERROR: Output video validation failed")
        state.update_step("step-05-video-composition", "failed")
        sys.exit(1)

    # Cleanup temp clips
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
