from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

import yt_dlp

from .ffmpeg import ALL_FORMATS, convert, ensure_x_compatible, probe, unique_output
from .jobs import JobContext


def _safe_title(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return cleaned[:160] or "download"


def audio_tracks_from_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse yt-dlp's codec/bitrate variants into human-selectable audio tracks."""
    tracks: dict[tuple[str, str], tuple[tuple[float, ...], dict[str, Any]]] = {}
    quality_words = {"default", "low", "medium", "high", "audio", "audio only", "premium"}
    for item in formats:
        if item.get("acodec") in (None, "none"):
            continue
        format_id = str(item.get("format_id") or "")
        language = str(item.get("language") or "").strip()
        if not language or language == "und" or not re.fullmatch(r"[A-Za-z0-9._+-]+", format_id):
            continue
        note = " ".join(str(item.get("format_note") or "").split())
        first_note = note.split(",", 1)[0].strip()
        role = next((name for name in ("original", "dubbed", "descriptive") if name in note.lower()), "")
        if not first_note or first_note.lower() in quality_words:
            first_note = language
        if role and role not in first_note.lower():
            first_note = f"{first_note} ({role})"
        label = first_note
        key = (language.lower(), re.sub(r"\s*\(default\)\s*", "", label, flags=re.I).lower())
        preference = float(item.get("language_preference") or -1)
        score = (
            1.0 if item.get("vcodec") in (None, "none") else 0.0,
            0.0 if "drc" in note.lower() else 1.0,
            float(item.get("abr") or item.get("tbr") or 0),
            float(item.get("asr") or 0),
            float(item.get("filesize") or item.get("filesize_approx") or 0),
        )
        track = {
            "formatId": format_id,
            "language": language,
            "label": label,
            "original": "original" in note.lower(),
            "dubbed": "dubbed" in note.lower(),
            "default": "default" in note.lower() or preference >= 0,
        }
        if key not in tracks or score > tracks[key][0]:
            tracks[key] = (score, track)
    return sorted(
        (value[1] for value in tracks.values()),
        key=lambda track: (not track["original"], not track["default"], track["label"].lower()),
    )


def download_format_selector(target_format: str, audio_format_id: str | None = None) -> str:
    if not audio_format_id:
        return "bestaudio/best" if target_format in {"mp3", "m4a", "wav"} else "bestvideo*+bestaudio/best"
    if not re.fullmatch(r"[A-Za-z0-9._+-]+", audio_format_id):
        raise ValueError("The selected audio track identifier is invalid")
    if target_format in {"mp3", "m4a", "wav"}:
        return audio_format_id
    return f"bestvideo+{audio_format_id}/bestvideo*+{audio_format_id}"


def inspect_url(url: str, cookie_file: str | None = None) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        raise ValueError("Enter a complete http:// or https:// media URL")
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
    if cookie_file:
        cookie_path = Path(cookie_file).expanduser().resolve()
        if not cookie_path.is_file():
            raise FileNotFoundError(f"Cookies file not found: {cookie_path}")
        options["cookiefile"] = str(cookie_path)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("entries"):
        info = next((entry for entry in info["entries"] if entry), info)
    formats = info.get("formats") or []
    heights = sorted({int(f["height"]) for f in formats if f.get("height")}, reverse=True)
    return {
        "title": info.get("title") or "Untitled media",
        "site": info.get("extractor_key") or info.get("extractor") or "Website",
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpageUrl": info.get("webpage_url") or url,
        "maxHeight": heights[0] if heights else None,
        "formatCount": len(formats),
        "hasVideo": any(f.get("vcodec") not in (None, "none") for f in formats),
        "hasAudio": any(f.get("acodec") not in (None, "none") for f in formats),
        "audioTracks": audio_tracks_from_formats(formats),
    }


def download(
    context: JobContext,
    *,
    url: str,
    output_directory: str,
    output_format: str,
    x_compatible: bool = False,
    audio_format_id: str | None = None,
    audio_track_label: str | None = None,
    cookie_file: str | None = None,
    register: Callable[[Path], str],
) -> dict[str, Any]:
    target_format = output_format.lower()
    if target_format not in ALL_FORMATS:
        raise ValueError(f"Unsupported output format: {target_format}")
    if x_compatible and target_format != "mp4":
        raise ValueError("X compatibility can only be requested for MP4 video")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Enter a complete media URL")

    destination = Path(output_directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    started = time.time()
    context.update(1, "Reading source metadata")
    observed: list[Path] = []

    def progress_hook(data: dict[str, Any]) -> None:
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            pct = (downloaded / total * 78) if total else 8
            speed = data.get("_speed_str", "").strip()
            eta = data.get("_eta_str", "").strip()
            context.update(max(2, min(78, pct)), f"Downloading {speed} · ETA {eta}".strip(" ·"))
        elif status == "finished":
            filename = data.get("filename")
            if filename:
                observed.append(Path(filename))
            context.update(80, "Download complete; preparing output")

    def post_hook(data: dict[str, Any]) -> None:
        info = data.get("info_dict") or {}
        filename = info.get("filepath") or info.get("_filename")
        if filename:
            observed.append(Path(filename))

    options: dict[str, Any] = {
        "format": download_format_selector(target_format, audio_format_id),
        "outtmpl": str(destination / "%(title).160B [source].%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mkv",
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 8,
        "socket_timeout": 30,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [post_hook],
        "windowsfilenames": True,
    }
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
    if cookie_file:
        cookie_path = Path(cookie_file).expanduser().resolve()
        if not cookie_path.is_file():
            raise FileNotFoundError(f"Cookies file not found: {cookie_path}")
        options["cookiefile"] = str(cookie_path)

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    candidates = [p.resolve() for p in observed if p.exists() and p.is_file()]
    if not candidates:
        candidates = [
            p for p in destination.iterdir()
            if p.is_file() and p.stat().st_mtime >= started - 2 and p.suffix not in {".part", ".ytdl"}
        ]
    if not candidates:
        raise RuntimeError("yt-dlp completed but the downloaded file could not be located")
    source = max(candidates, key=lambda p: p.stat().st_mtime)
    title = _safe_title(info.get("title") or source.stem.replace(" [source]", ""))
    final_path = source
    converted = False
    skipped_x_conversion = False

    if target_format != "original":
        output = unique_output(destination, title, target_format)
        context.update(82, f"Rendering {target_format.upper()} output")
        convert(source, output, target_format, x_compatible=x_compatible, on_line=context.write)
        final_path = output
        converted = True
        if source != final_path and source.name.endswith(f"[source]{source.suffix}"):
            try:
                source.unlink()
            except OSError:
                pass

    if x_compatible:
        context.update(96, "Checking X compatibility")
        checked_path, changed, _ = ensure_x_compatible(final_path, on_line=context.write)
        if changed and checked_path != final_path:
            try:
                final_path.unlink()
            except OSError:
                pass
            final_path = checked_path
        skipped_x_conversion = not changed

    media = probe(final_path)
    return {
        "path": str(final_path),
        "token": register(final_path),
        "media": media,
        "converted": converted,
        "xCompatible": x_compatible,
        "xConversionSkipped": skipped_x_conversion,
        "audioTrack": audio_track_label or None,
    }
