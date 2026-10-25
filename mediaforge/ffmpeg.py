from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable


VIDEO_FORMATS = {"original", "mp4", "mkv", "webm", "mov"}
AUDIO_FORMATS = {"mp3", "m4a", "wav"}
ALL_FORMATS = VIDEO_FORMATS | AUDIO_FORMATS
_media_slot = threading.Lock()
_log = logging.getLogger(__name__)
MEDIA_THREADS = 2
MP4_COPY_CODECS = {"h264", "hevc", "av1", "vp9", "mpeg4"}


def require_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(f"Missing required media tools: {', '.join(missing)}")


def bounded_command(command: list[str]) -> list[str]:
    result = [command[0], "-filter_threads", "1", "-filter_complex_threads", "1"]
    for argument in command[1:-1]:
        if argument == "-i":
            result += ["-threads", str(MEDIA_THREADS)]
        result.append(argument)
    return [*result, "-threads", str(MEDIA_THREADS), command[-1]]


def run(command: list[str], on_line: Callable[[str], None] | None = None, *, check_cancelled=None, cwd=None) -> None:
    command = bounded_command(command)
    if check_cancelled:
        check_cancelled()
    waiting = False
    while not _media_slot.acquire(timeout=.25):
        if check_cancelled:
            check_cancelled()
        if on_line and not waiting:
            on_line("Waiting for another media operation to finish")
            waiting = True
    process = None
    started = time.monotonic()
    try:
        if check_cancelled:
            check_cancelled()
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0),
            cwd=cwd,
        )
        if hasattr(os, "setpriority"):
            try:
                os.setpriority(os.PRIO_PROCESS, process.pid, 10)
            except OSError:
                pass
        _log.info("FFmpeg PID %s started, %s media threads, low priority: %s", process.pid, MEDIA_THREADS, command)
        assert process.stdout is not None
        last_heartbeat = started
        progress = {}
        for line in process.stdout:
            if check_cancelled:
                check_cancelled()
            clean = line.rstrip()
            if "=" in clean:
                key, value = clean.split("=", 1)
                if key in {"out_time", "speed"}:
                    progress[key] = value
            if time.monotonic() - last_heartbeat >= 30:
                _log.info("FFmpeg PID %s still processing: %s", process.pid, progress)
                last_heartbeat = time.monotonic()
            if on_line:
                on_line(clean)
        code = process.wait()
        _log.info("FFmpeg PID %s finished in %.2fs, exit %s", process.pid, time.monotonic() - started, code)
        if code:
            raise RuntimeError(f"FFmpeg exited with status {code}")
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                _log.info("FFmpeg PID %s stopped after interruption in %.2fs", process.pid, time.monotonic() - started)
            if process.stdout:
                process.stdout.close()
        _media_slot.release()


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
        "subtitles": [{"codec": stream.get("codec_name"),
                       "language": (stream.get("tags") or {}).get("language"),
                       "title": (stream.get("tags") or {}).get("title")}
                      for stream in streams if stream.get("codec_type") == "subtitle"],
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
    on_progress: Callable[[float, str], None] | None = None,
    check_cancelled=None,
    subtitle_path: str | Path | None = None,
    burn_size: str = "source",
) -> Path:
    if burn_size not in {"source", "1080"}:
        raise ValueError("Choose source size or 1080p for burned subtitles")
    if subtitle_path:
        if target.lower() in AUDIO_FORMATS:
            raise ValueError("Burned subtitles require video output")
        # A fixed relative name avoids filter parsing of Windows drive letters,
        # apostrophes, commas and other characters in user-selected paths.
        with tempfile.TemporaryDirectory(prefix="clipharbor-captions-") as temporary:
            shutil.copyfile(subtitle_path, Path(temporary) / "captions.srt")
            return _convert(input_path, output_path, target, x_compatible=x_compatible,
                on_line=on_line, on_progress=on_progress, check_cancelled=check_cancelled,
                burn_size=burn_size, caption_cwd=temporary)
    return _convert(input_path, output_path, target, x_compatible=x_compatible,
        on_line=on_line, on_progress=on_progress, check_cancelled=check_cancelled)


def _convert(input_path, output_path, target, *, x_compatible=False, on_line=None,
             on_progress=None, check_cancelled=None, burn_size="source", caption_cwd=None):
    source = Path(input_path).resolve()
    output = Path(output_path).resolve()
    target = target.lower()
    if target not in ALL_FORMATS - {"original"}:
        raise ValueError(f"Unsupported output format: {target}")

    media = probe(source)
    command = ["ffmpeg", "-hide_banner", "-nostats", "-progress", "pipe:1", "-i", str(source), "-map_metadata", "0"]
    mode = "Preparing output"
    filters = []

    if target == "mp4":
        compat = x_compatibility(media)
        video = media.get("video") or {}
        audio = media.get("audio") or {}
        general_copy_safe = video.get("codec") in MP4_COPY_CODECS
        if not caption_cwd and ((x_compatible and compat["videoCopySafe"]) or (not x_compatible and general_copy_safe)):
            command += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy"]
            mode = "Saving MP4 without re-encoding video"
            if video.get("codec") == "hevc":
                command += ["-tag:v", "hvc1"]
        else:
            command += [
                "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
            ]
            mode = "Converting video to H.264"
            if x_compatible:
                filters.append(
                    "fps=min(source_fps\\,40),"
                    "scale=w='if(gte(iw,ih),min(iw,1920),min(iw,1200))':"
                    "h='if(gte(iw,ih),min(ih,1200),min(ih,1900))':"
                    "force_original_aspect_ratio=decrease,"
                    "pad=w='ceil(max(iw,ih/2.39)/2)*2':h='ceil(max(ih,iw/2.39)/2)*2':"
                    "x=(ow-iw)/2:y=(oh-ih)/2:color=black")
                command += ["-profile:v", "high", "-maxrate", "25M", "-bufsize", "50M"]
        if audio.get("codec") == "aac" and int(audio.get("channels") or 0) <= 2:
            command += ["-c:a", "copy"]
        else:
            command += ["-c:a", "aac", "-profile:a", "aac_low", "-b:a", "192k", "-ac", "2"]
        command += ["-movflags", "+faststart"]
    elif target == "mkv":
        if caption_cwd:
            command += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy"]
        else:
            command += ["-map", "0", "-c", "copy"]
            mode = "Saving MKV without re-encoding"
    elif target == "webm":
        video_codec = (media.get("video") or {}).get("codec")
        audio_codec = (media.get("audio") or {}).get("codec")
        command += ["-map", "0:v:0", "-map", "0:a:0?"]
        command += ["-c:v", "copy"] if not caption_cwd and video_codec in {"vp8", "vp9", "av1"} else ["-c:v", "libvpx-vp9", "-crf", "18", "-b:v", "0"]
        if caption_cwd:
            command += ["-deadline", "realtime", "-cpu-used", "6"]
        command += ["-c:a", "copy"] if audio_codec in {"opus", "vorbis"} else ["-c:a", "libopus", "-b:a", "160k"]
    elif target == "mov":
        command += [
            "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-crf", "17",
            "-preset", "veryfast" if caption_cwd else "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        ]
    elif target == "mp3":
        command += ["-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-q:a", "0"]
    elif target == "m4a":
        command += ["-map", "0:a:0", "-vn", "-c:a", "aac", "-b:a", "256k"]
    elif target == "wav":
        command += ["-map", "0:a:0", "-vn", "-c:a", "pcm_s24le"]

    if caption_cwd:
        if "libx264" in command:
            # Avoid holding a 4K lookahead/B-frame queue merely to overlay text.
            # Keep the requested canvas, frame rate and CRF while bounding RAM.
            command += ["-tune", "zerolatency"]
        if burn_size == "1080":
            filters.append("fps=min(source_fps\\,30),"
                "scale=w='if(gte(iw,ih),min(iw,1920),min(iw,1080))':"
                "h='if(gte(iw,ih),min(ih,1080),min(ih,1920))':"
                "force_original_aspect_ratio=decrease:force_divisible_by=2")
        filters.append("subtitles=filename=captions.srt:charenc=UTF-8:force_style='FontName=Arial,FontSize=16,Outline=1.2,Shadow=0,MarginV=12,Alignment=2'")
        mode = "Burning subtitles into video" + (" · 1080p/30 max" if burn_size == "1080" else " · source size")
    if filters:
        command += ["-vf", ",".join(filters)]
    command += ["-y", str(output)]
    _log.info("%s: input codec=%s, canvas=%sx%s, fps=%s, duration=%ss", mode,
              (media.get("video") or {}).get("codec"), (media.get("video") or {}).get("width"),
              (media.get("video") or {}).get("height"), (media.get("video") or {}).get("fps"), media.get("duration"))
    def report(line):
        if on_line:
            on_line(line)
        if on_progress and line.startswith("Waiting for another media operation"):
            on_progress(0., line)
        if on_progress and line.startswith("out_time_us="):
            try:
                ratio = float(line.split("=", 1)[1]) / 1_000_000 / max(float(media["duration"]), .01)
                on_progress(max(0., min(.99, ratio)), mode)
            except (ValueError, KeyError):
                pass
        elif on_progress and line == "progress=end":
            on_progress(1., mode)
    if on_progress:
        on_progress(0., mode)
    run(command, report, check_cancelled=check_cancelled, cwd=caption_cwd)
    return output


def embed_subtitle(input_path, subtitle_path, output_path, *, language, title, on_line=None, check_cancelled=None) -> Path:
    """Remux one switchable caption track; copy the video and audio verbatim."""
    from yt_dlp.utils import ISO639Utils

    output = Path(output_path)
    codec = {"mp4": "mov_text", "mov": "mov_text", "mkv": "srt", "webm": "webvtt"}[output.suffix.lstrip(".").lower()]
    base_language = re.split(r"[-_]", language)[0].lower()
    language_code = ISO639Utils.short2long(base_language) or base_language
    command = ["ffmpeg", "-hide_banner", "-i", str(input_path), "-i", str(subtitle_path),
               "-map", "0:v:0", "-map", "0:a:0?", "-map", "1:0", "-map_metadata", "0",
               "-c", "copy", "-c:s", codec, "-metadata:s:s:0", f"language={language_code}",
               "-metadata:s:s:0", f"title={title}", "-disposition:s:0", "default"]
    if output.suffix.lower() in {".mp4", ".mov"}:
        command += ["-movflags", "+faststart"]
    run([*command, "-y", str(output)], on_line, check_cancelled=check_cancelled)
    if len(probe(output)["subtitles"]) != 1:
        raise RuntimeError("The downloaded video could not be verified with the selected subtitles")
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
