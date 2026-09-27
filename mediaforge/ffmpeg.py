from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


VIDEO_FORMATS = {"original", "mp4", "mkv", "webm", "mov"}
AUDIO_FORMATS = {"mp3", "m4a", "wav"}
ALL_FORMATS = VIDEO_FORMATS | AUDIO_FORMATS


def require_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(f"Missing required media tools: {', '.join(missing)}")


def run(command: list[str], on_line: Callable[[str], None] | None = None) -> None:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert process.stdout is not None
    for line in process.stdout:
        if on_line:
            on_line(line.rstrip())
    code = process.wait()
    if code:
        raise RuntimeError(f"FFmpeg exited with status {code}")


def probe(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"Media file not found: {file_path}")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(file_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    raw = json.loads(result.stdout)
    return summarize_probe(file_path, raw)


def _rate(value: str | None) -> float:
    try:
        numerator, denominator = (value or "0/1").split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 0.0


def summarize_probe(path: Path, raw: dict[str, Any]) -> dict[str, Any]:
    streams = raw.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = raw.get("format", {})
    duration = float(fmt.get("duration") or (video or {}).get("duration") or (audio or {}).get("duration") or 0)
    return {
        "path": str(path),
        "name": path.name,
        "size": path.stat().st_size,
        "duration": duration,
        "bitRate": int(fmt.get("bit_rate") or 0),
        "kind": "video" if video else "audio" if audio else "unknown",
        "format": fmt.get("format_name", ""),
        "video": None if not video else {
            "codec": video.get("codec_name"),
            "profile": video.get("profile"),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": _rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
            "pixelFormat": video.get("pix_fmt"),
            "fieldOrder": video.get("field_order"),
        },
        "audio": None if not audio else {
            "codec": audio.get("codec_name"),
            "profile": audio.get("profile"),
            "channels": int(audio.get("channels") or 0),
            "sampleRate": int(audio.get("sample_rate") or 0),
        },
    }


def x_compatibility(media: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    video = media.get("video")
    audio = media.get("audio")
    format_names = set((media.get("format") or "").split(","))
    video_copy_safe = True

    if not video:
        return {"compatible": False, "issues": ["No video stream"], "videoCopySafe": False}
    if video.get("codec") != "h264":
        issues.append(f"Video is {video.get('codec') or 'unknown'}, not H.264")
        video_copy_safe = False
    if video.get("pixelFormat") != "yuv420p":
        issues.append(f"Pixel format is {video.get('pixelFormat') or 'unknown'}, not yuv420p")
        video_copy_safe = False
    if video.get("fieldOrder") not in (None, "unknown", "progressive"):
        issues.append("Video is interlaced")
        video_copy_safe = False
    if float(video.get("fps") or 0) > 40.01:
        issues.append("Frame rate is above X web upload's 40 FPS limit")
        video_copy_safe = False
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if (width >= height and (width > 1920 or height > 1200)) or (height > width and (width > 1200 or height > 1900)):
        issues.append("Resolution is above X web upload limits")
        video_copy_safe = False
    aspect = width / height if height else 0
    if aspect and not (1 / 2.39 <= aspect <= 2.39):
        issues.append("Aspect ratio is outside X's 1:2.39–2.39:1 range")
        video_copy_safe = False
    if int(media.get("bitRate") or 0) > 25_000_000:
        issues.append("Bit rate is above X web upload's 25 Mbps limit")
        video_copy_safe = False
    if not ({"mov", "mp4"} & format_names):
        issues.append("Container is not MP4/MOV")
    if audio:
        if audio.get("codec") != "aac" or audio.get("profile") not in ("LC", "Low Complexity"):
            issues.append("Audio is not AAC-LC")
        if int(audio.get("channels") or 0) > 2:
            issues.append("Audio has more than two channels")
    if int(media.get("size") or 0) > 512 * 1024 * 1024:
        warnings.append("File exceeds the 512 MB non-Premium upload allowance")
    if float(media.get("duration") or 0) > 140:
        warnings.append("Duration exceeds the 140-second non-Premium upload allowance")
    return {"compatible": not issues, "issues": issues, "warnings": warnings, "videoCopySafe": video_copy_safe}


def unique_output(directory: Path, stem: str, extension: str) -> Path:
    candidate = directory / f"{stem}.{extension}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}).{extension}"
        counter += 1
    return candidate


def convert(
    input_path: str | Path,
    output_path: str | Path,
    target: str,
    *,
    x_compatible: bool = False,
    on_line: Callable[[str], None] | None = None,
) -> Path:
    source = Path(input_path).resolve()
    output = Path(output_path).resolve()
    target = target.lower()
    if target not in ALL_FORMATS - {"original"}:
        raise ValueError(f"Unsupported output format: {target}")

    media = probe(source)
    command = ["ffmpeg", "-hide_banner", "-i", str(source), "-map_metadata", "0"]

    if target == "mp4":
        compat = x_compatibility(media)
        video = media.get("video") or {}
        audio = media.get("audio") or {}
        general_copy_safe = video.get("codec") == "h264" and video.get("pixelFormat") == "yuv420p"
        if (x_compatible and compat["videoCopySafe"]) or (not x_compatible and general_copy_safe):
            command += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy"]
        else:
            command += [
                "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p",
            ]
            if x_compatible:
                command += [
                    "-vf",
                    "fps=min(source_fps\\,40),"
                    "scale=w='if(gte(iw,ih),min(iw,1920),min(iw,1200))':"
                    "h='if(gte(iw,ih),min(ih,1200),min(ih,1900))':"
                    "force_original_aspect_ratio=decrease,"
                    "pad=w='ceil(max(iw,ih/2.39)/2)*2':h='ceil(max(ih,iw/2.39)/2)*2':"
                    "x=(ow-iw)/2:y=(oh-ih)/2:color=black",
                    "-profile:v", "high", "-maxrate", "25M", "-bufsize", "50M",
                ]
        if audio.get("codec") == "aac" and int(audio.get("channels") or 0) <= 2:
            command += ["-c:a", "copy"]
        else:
            command += ["-c:a", "aac", "-profile:a", "aac_low", "-b:a", "192k", "-ac", "2"]
        command += ["-movflags", "+faststart"]
    elif target == "mkv":
        command += ["-map", "0", "-c", "copy"]
    elif target == "webm":
        video_codec = (media.get("video") or {}).get("codec")
        audio_codec = (media.get("audio") or {}).get("codec")
        command += ["-map", "0:v:0", "-map", "0:a:0?"]
        command += ["-c:v", "copy"] if video_codec in {"vp8", "vp9", "av1"} else ["-c:v", "libvpx-vp9", "-crf", "18", "-b:v", "0"]
        command += ["-c:a", "copy"] if audio_codec in {"opus", "vorbis"} else ["-c:a", "libopus", "-b:a", "160k"]
    elif target == "mov":
        command += [
            "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-crf", "17",
            "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        ]
    elif target == "mp3":
        command += ["-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-q:a", "0"]
    elif target == "m4a":
        command += ["-map", "0:a:0", "-vn", "-c:a", "aac", "-b:a", "256k"]
    elif target == "wav":
        command += ["-map", "0:a:0", "-vn", "-c:a", "pcm_s24le"]

    command += ["-y", str(output)]
    run(command, on_line)
    return output


def ensure_x_compatible(
    input_path: str | Path,
    *,
    on_line: Callable[[str], None] | None = None,
) -> tuple[Path, bool, dict[str, Any]]:
    source = Path(input_path).resolve()
    state = x_compatibility(probe(source))
    if state["compatible"]:
        return source, False, state
    output = unique_output(source.parent, f"{source.stem} [X]", "mp4")
    convert(source, output, "mp4", x_compatible=True, on_line=on_line)
    final_state = x_compatibility(probe(output))
    if not final_state["compatible"]:
        raise RuntimeError("X conversion completed but validation still failed: " + "; ".join(final_state["issues"]))
    return output, True, final_state


def atempo_chain(speed: float) -> str:
    if not math.isfinite(speed) or speed <= 0:
        raise ValueError("Speed must be a positive finite number")
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={factor:.8g}" for factor in factors)
