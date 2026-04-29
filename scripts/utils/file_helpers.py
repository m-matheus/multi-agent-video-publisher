import re
from pathlib import Path
import httpx


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_file(url: str, destination: Path, timeout: int = 120) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        destination.write_bytes(response.content)
    return destination


def sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\-.]', '_', name).strip('_')[:100]


def get_scene_files(directory: Path, prefix: str, extension: str) -> list[Path]:
    pattern = f"{prefix}_*.{extension}"
    files = sorted(directory.glob(pattern))
    return files
