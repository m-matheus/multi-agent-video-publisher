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


def get_scene_overlay(scene: dict, scene_idx: int, total_scenes: int, title: str) -> dict | None:
    """Determine what text overlay to apply based on scene position and narration."""
    import re
    narration = scene.get("narration_text", "")

    if scene_idx == total_scenes - 1:
        return {"style": "cta", "start": 4.0, "duration": 8.0}

    # re.search (not match) so it finds "number" mid-sentence (e.g. "Starting at number five: Saitama")
    m = re.search(
        r"[Nn]umber (\w+)\s*[—\-,:]\s*([^,\n]+)",
        narration,
    )
    if m:
        word = m.group(1).lower()
        rank = _WORD_TO_NUM.get(word, word)
        words = m.group(2).strip().split()[:4]
        name = " ".join(words).rstrip(".,!").upper()
        return {"style": "rank", "rank": rank, "name": name, "start": 1.0, "duration": 5.5}

    return None


def parse_args():
    parser = argparse.ArgumentParser(description="Compose final video with FFmpeg")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--frames-dir", required=True, help="Path to anime frames/clips directory")
    parser.add_argument("--audio-dir", required=True, help="Path to audio directory")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--bgm-path", default=None, help="Optional background music path")
    parser.add_argument("--bgm-volume", type=float, default=0.15, help="BGM volume (0-1)")
    parser.add_argument("--srt-path", default=None, help="Optional SRT subtitle file to embed as a soft track")
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
    input_path: Path,
    output_path: Path,
    target_duration: float,
    effect: str = "kenburns",
    text_overlay: dict | None = None,
) -> Path:
    """
    Create a scene clip from input media with effects applied.
    Handles: video clips (trim/loop), static images (ken burns), gifs (loop).
    Optionally burns in a text overlay (title card, character name, CTA).
    """
    ext = input_path.suffix.lower()
    is_image = ext in (".png", ".jpg", ".jpeg", ".bmp")
    is_gif = ext == ".gif"

    # Build optional drawtext suffix
    drawtext = ""
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
            f"zoompan=z='min(zoom+0.0008,1.2)':d={int(target_duration*24)}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080,fps=24{drawtext}"
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
        vf = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=24{drawtext}"
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

        vf = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=24{drawtext}"

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


def build_final_video(
    scene_clips: list[Path],
    audio_path: Path,
    output_path: Path,
    transitions: list[str],
    bgm_path: Path = None,
    bgm_volume: float = 0.15,
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
        filter_parts.append("[v0]copy[vout]")
    else:
        concat_inputs = "".join(f"[v{i}]" for i in range(n_clips))
        filter_parts.append(f"{concat_inputs}concat=n={n_clips}:v=1:a=0[vout]")

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

    if not source_dir.exists():
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)
    if not audio_path.exists():
        print(f"ERROR: narration_full.mp3 not found in {args.audio_dir}")
        sys.exit(1)

    source_files = find_scene_files(source_dir)
    if not source_files:
        print(f"ERROR: No media files found in {source_dir}")
        sys.exit(1)

    scenes = script["scenes"]
    transitions = [scene.get("transition", "cut") for scene in scenes]

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

    for i, scene in enumerate(scenes):
        target_duration = scene.get("duration_seconds", 5)

        if i < len(source_files):
            source = source_files[i]
        else:
            # Reuse last available clip if not enough
            source = source_files[-1]

        clip_path = temp_dir / f"processed_{i+1:02d}.mp4"
        overlay = get_scene_overlay(scene, i, total_scenes, title) if font_available else None
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
        print(f"  Processing scene {i+1}: {source.name} -> {target_duration}s{overlay_label}")

        try:
            create_scene_clip(source, clip_path, target_duration, text_overlay=overlay)
            scene_clips.append(clip_path)
        except subprocess.CalledProcessError as e:
            print(f"  ERROR processing scene {i+1}: {e}")
            # Create a black frame fallback
            cmd = [
                _ffmpeg(), "-y",
                "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={target_duration}:r=24",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(clip_path),
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            scene_clips.append(clip_path)

    # Build and execute final composition
    output_path = final_dir / "final_video.mp4"
    bgm_path = Path(args.bgm_path) if args.bgm_path else None
    srt_path = Path(args.srt_path) if args.srt_path else None

    print(f"  Composing final video...")
    # If SRT will be embedded, encode to a temp file first, then add subtitles on top
    encode_output = final_dir / "final_nosub_tmp.mp4" if (srt_path and srt_path.exists()) else output_path
    cmd = build_final_video(scene_clips, audio_path, encode_output, transitions, bgm_path, args.bgm_volume)

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
