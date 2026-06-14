import os
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_BASE = PROJECT_ROOT / "output"
TEMPLATES_DIR = PROJECT_ROOT / "templates"


def get_ffmpeg_path() -> str:
    """Find FFmpeg executable. Checks PATH first, then imageio-ffmpeg fallback."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    raise FileNotFoundError("FFmpeg not found. Install it or run: pip install imageio-ffmpeg")


def get_ffprobe_path() -> str:
    """Find FFprobe executable."""
    path = shutil.which("ffprobe")
    if path:
        return path
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe = Path(ffmpeg_path).parent / "ffprobe.exe"
        if ffprobe.exists():
            return str(ffprobe)
        ffprobe = Path(ffmpeg_path).parent / "ffprobe"
        if ffprobe.exists():
            return str(ffprobe)
    except ImportError:
        pass
    raise FileNotFoundError("FFprobe not found.")


def load_config() -> dict:
    load_dotenv(PROJECT_ROOT / ".env")
    return {
        # ElevenLabs
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
        "elevenlabs_model": os.getenv("ELEVENLABS_MODEL", "eleven_v3"),
        "voice_id_anime": os.getenv("VOICE_ID_ANIME", "JBFqnCBsd6RMkjVDRZzb"),
        # YouTube
        "youtube_client_id": os.getenv("YOUTUBE_CLIENT_ID"),
        "youtube_client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
        "youtube_credentials_path": os.getenv("YOUTUBE_CREDENTIALS_PATH", ".youtube_credentials.json"),
        "youtube_channel_id": os.getenv("YOUTUBE_CHANNEL_ID"),
        "max_parallel_image_requests": int(os.getenv("MAX_PARALLEL_IMAGE_REQUESTS", "5")),
        "max_parallel_video_requests": int(os.getenv("MAX_PARALLEL_VIDEO_REQUESTS", "3")),
        "output_base_dir": os.getenv("OUTPUT_BASE_DIR", "output"),
        # Durations per content type (seconds)
        "duration_anime_short": int(os.getenv("DURATION_ANIME_SHORT", "60")),
        "duration_anime_normal": int(os.getenv("DURATION_ANIME_NORMAL", "300")),
        # Freesound (background music search — free key at freesound.org/apiv2/apply/)
        "freesound_api_key": os.getenv("FREESOUND_API_KEY"),
        # OpenAI (thumbnail generation via Responses API)
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        # Anthropic (community posts, comment replies, AMV analysis)
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
        "anthropic_model_haiku": os.getenv("ANTHROPIC_MODEL_HAIKU", "claude-haiku-4-5-20251001"),
        "analyze_amv_model": os.getenv("ANALYZE_AMV_MODEL", "claude-haiku-4-5-20251001"),
    }


def get_output_dir(topic: str) -> Path:
    sanitized = "".join(c if c.isalnum() or c in "-_ " else "" for c in topic)
    sanitized = sanitized.strip().replace(" ", "-").lower()[:50]
    date_prefix = datetime.now().strftime("%Y%m%d")
    output_dir = OUTPUT_BASE / f"{date_prefix}-{sanitized}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_duration(content_type: str, video_format: str = "normal") -> int:
    """
    Get target video duration in seconds.

    Args:
        content_type: "anime" or "amv"
        video_format: "short" (YouTube Shorts) or "normal" (regular video)

    Returns:
        Duration in seconds.
    """
    config = load_config()
    if video_format == "short":
        return config["duration_anime_short"]
    else:
        return config["duration_anime_normal"]
