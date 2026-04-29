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
        # fal.ai
        "fal_key": os.getenv("FAL_KEY"),
        "default_image_model": os.getenv("DEFAULT_IMAGE_MODEL", "fal-ai/fast-sdxl"),
        "default_video_model": os.getenv("DEFAULT_VIDEO_MODEL", "fal-ai/wan-2.1/image-to-video"),
        # ElevenLabs
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
        "elevenlabs_model": os.getenv("ELEVENLABS_MODEL", "eleven_v3"),
        "voice_id_anime": os.getenv("VOICE_ID_ANIME", "JBFqnCBsd6RMkjVDRZzb"),
        "voice_id_bedtime": os.getenv("VOICE_ID_BEDTIME", "EXAVITQu4vr4xnSDxMaL"),
        # YouTube
        "youtube_client_id": os.getenv("YOUTUBE_CLIENT_ID"),
        "youtube_client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
        "youtube_credentials_path": os.getenv("YOUTUBE_CREDENTIALS_PATH", ".youtube_credentials.json"),
        "youtube_channel_id": os.getenv("YOUTUBE_CHANNEL_ID"),
        # Tenor (anime GIF/clip search)
        "tenor_api_key": os.getenv("TENOR_API_KEY", "LIVDSRZULELA"),
        "max_parallel_image_requests": int(os.getenv("MAX_PARALLEL_IMAGE_REQUESTS", "5")),
        "max_parallel_video_requests": int(os.getenv("MAX_PARALLEL_VIDEO_REQUESTS", "3")),
        "output_base_dir": os.getenv("OUTPUT_BASE_DIR", "output"),
        # Durations per content type (seconds)
        "duration_anime_short": int(os.getenv("DURATION_ANIME_SHORT", "60")),
        "duration_anime_normal": int(os.getenv("DURATION_ANIME_NORMAL", "300")),
        "duration_bedtime": int(os.getenv("DURATION_BEDTIME", "900")),
        # Pixabay (music API restricted — use Freesound or YouTube URL mode instead)
        "pixabay_api_key": os.getenv("PIXABAY_API_KEY"),
        # Freesound (background music search — free key at freesound.org/apiv2/apply/)
        "freesound_api_key": os.getenv("FREESOUND_API_KEY"),
        "llm_provider": os.getenv("LLM_PROVIDER"),
        "llm_model": os.getenv("LLM_MODEL"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    }


def get_output_dir(topic: str) -> Path:
    sanitized = "".join(c if c.isalnum() or c in "-_ " else "" for c in topic)
    sanitized = sanitized.strip().replace(" ", "-").lower()[:50]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = OUTPUT_BASE / f"{sanitized}-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_duration(content_type: str, video_format: str = "normal") -> int:
    """
    Get target video duration in seconds.

    Args:
        content_type: "anime" or "bedtime-story"
        video_format: "short" (YouTube Shorts) or "normal" (regular video)

    Returns:
        Duration in seconds.
    """
    config = load_config()
    if content_type == "bedtime-story":
        return config["duration_bedtime"]
    elif video_format == "short":
        return config["duration_anime_short"]
    else:
        return config["duration_anime_normal"]
