"""
Kinetic caption generation for YouTube Shorts.
Reads word-level alignment JSONs (produced by generate_voice.py --timestamps)
and generates a burned-in ASS subtitle file with MrBeast-style pop-in captions.

Usage:
    python scripts/generate_captions.py \
        --script-path output/run-001/script/script_short.json \
        --audio-dir output/run-001/short/audio \
        --output-dir output/run-001/short \
        --shorts \
        --color yellow
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.file_helpers import ensure_dir

# narration_synced.mp3 pads each segment to max(script_dur, tts_dur) with no gaps.
# This must mirror build_synced_narration in compose_video.py.

# Named color presets (ASS format: &H00BBGGRR)
_COLOR_PRESETS = {
    "yellow": "&H0000FFFF",
    "white":  "&H00FFFFFF",
    "cyan":   "&H00FFFF00",
    "red":    "&H000000FF",
    "orange": "&H000080FF",
}


def hex_to_ass(color_str: str) -> str:
    """Convert a color name or #RRGGBB hex string to ASS &H00BBGGRR format."""
    c = color_str.strip().lower()
    if c in _COLOR_PRESETS:
        return _COLOR_PRESETS[c]
    # Handle #RRGGBB
    c = c.lstrip("#")
    if len(c) == 6:
        r, g, b = c[0:2], c[2:4], c[4:6]
        return f"&H00{b.upper()}{g.upper()}{r.upper()}"
    raise ValueError(f"Unknown color: {color_str!r}. Use a name (yellow/white/cyan/red/orange) or #RRGGBB hex.")


def get_mp3_duration(path: Path) -> float:
    try:
        from mutagen.mp3 import MP3
        return MP3(str(path)).info.length
    except Exception:
        pass
    import subprocess
    import re
    from scripts.utils.config import get_ffmpeg_path
    result = subprocess.run(
        [get_ffmpeg_path(), "-i", str(path)],
        capture_output=True, text=True,
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
    if m:
        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mn * 60 + s
    raise RuntimeError(f"Could not determine duration of {path}")


def seconds_to_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = round((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def chunk_words(words: list[dict], n: int) -> list[list[dict]]:
    return [words[i:i + n] for i in range(0, len(words), n)]


def build_ass(events: list[dict], shorts: bool, color: str = "yellow") -> str:
    play_res_y = 1920 if shorts else 1080
    play_res_x = 1080 if shorts else 1920
    font_size = 120 if shorts else 96
    cx = 540 if shorts else 960
    cy = 960 if shorts else 540

    # Resolve font — prefer Montserrat ExtraBold → Arial Black → Arial → ASS default
    if os.path.exists(r"C:\Windows\Fonts\Montserrat-ExtraBold.ttf"):
        font_name = "Montserrat ExtraBold"
    elif os.path.exists(r"C:\Windows\Fonts\ariblk.ttf"):
        font_name = "Arial Black"
    elif os.path.exists(r"C:\Windows\Fonts\arial.ttf"):
        font_name = "Arial"
        print("WARNING: Montserrat ExtraBold and Arial Black not found — using Arial for captions")
    else:
        font_name = "Arial"
        print("WARNING: No preferred caption font found — ASS renderer will use its default")

    ass_color = hex_to_ass(color)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kinetic,{font_name},{font_size},{ass_color},&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,0,5,0,0,0,0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    lines = [header]
    pop_tag = f"{{\\an5\\pos({cx},{cy})\\fscx130\\fscy130\\t(0,150,\\fscx100\\fscy100)}}"
    for ev in events:
        start = seconds_to_ass_time(ev["start"])
        end = seconds_to_ass_time(ev["end"])
        text = ev["text"].upper()
        lines.append(f"Dialogue: 0,{start},{end},Kinetic,,0,0,0,,{pop_tag}{text}")

    return "\n".join(lines) + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate kinetic ASS captions for Shorts")
    parser.add_argument("--script-path", required=True, help="Path to script.json")
    parser.add_argument("--audio-dir", required=True, help="Path to audio directory (contains narration_segments/)")
    parser.add_argument("--output-dir", required=True, help="Output directory for this run")
    parser.add_argument("--words-per-chunk", type=int, default=1, help="Words per caption block (default: 1)")
    parser.add_argument("--shorts", action="store_true", help="Use 1080x1920 vertical dimensions")
    parser.add_argument("--color", default="yellow",
                        help="Caption color: yellow, white, cyan, red, orange, or #RRGGBB (default: yellow)")
    return parser.parse_args()


def main():
    args = parse_args()
    script = json.loads(Path(args.script_path).read_text(encoding="utf-8"))
    audio_dir = Path(args.audio_dir)
    segments_dir = audio_dir / "narration_segments"
    output_dir = Path(args.output_dir)

    scenes = script["scenes"]
    events = []
    current_time = 0.0

    if not segments_dir.exists():
        print(f"WARNING: narration_segments/ not found at {segments_dir}. "
              "Run generate_voice.py --timestamps first for word-level captions. "
              "Falling back to evenly-spaced captions from narration_text.")

    for i, scene in enumerate(scenes):
        seg_path = segments_dir / f"segment_{i+1:02d}.mp3"
        alignment_path = segments_dir / f"segment_{i+1:02d}_alignment.json"

        if not seg_path.exists():
            current_time += float(scene.get("duration_seconds", 0))
            continue

        tts_dur = get_mp3_duration(seg_path)
        script_dur = float(scene.get("duration_seconds", tts_dur))
        effective_dur = max(script_dur, tts_dur)
        scene_start = current_time
        scene_end = current_time + tts_dur  # captions end when speech ends

        if alignment_path.exists():
            data = json.loads(alignment_path.read_text(encoding="utf-8"))
            words = data.get("words", [])
            if words:
                chunks = chunk_words(words, args.words_per_chunk)
                for j, chunk in enumerate(chunks):
                    chunk_start = scene_start + chunk[0]["start"]
                    if j + 1 < len(chunks):
                        chunk_end = scene_start + chunks[j + 1][0]["start"]
                    else:
                        chunk_end = scene_end
                    chunk_text = " ".join(w["word"] for w in chunk)
                    events.append({"start": chunk_start, "end": chunk_end, "text": chunk_text})
        else:
            # Fallback: split narration_text evenly across scene duration when no alignment data
            text = scene.get("narration_text", "").strip()
            if text:
                words_list = text.split()
                n = args.words_per_chunk
                chunks = [words_list[k:k + n] for k in range(0, len(words_list), n)]
                chunk_dur = tts_dur / len(chunks) if chunks else tts_dur
                for j, chunk in enumerate(chunks):
                    chunk_start = scene_start + j * chunk_dur
                    chunk_end = scene_start + (j + 1) * chunk_dur
                    events.append({"start": chunk_start, "end": chunk_end, "text": " ".join(chunk)})

        current_time += effective_dur

    ensure_dir(audio_dir)
    ass_path = audio_dir / "captions.ass"
    ass_path.write_text(build_ass(events, args.shorts, args.color), encoding="utf-8")
    print(f"Captions saved: {ass_path} ({len(events)} blocks, color={args.color})")


if __name__ == "__main__":
    main()
