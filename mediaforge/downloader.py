from __future__ import annotations

import math
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

import yt_dlp

from .ffmpeg import ALL_FORMATS, AUDIO_FORMATS, convert, embed_subtitle, ensure_x_compatible, probe, unique_output
from .jobs import JobContext


_output_lock = threading.Lock()
_SUBTITLE_EXTS = {"srt", "vtt", "ass", "ssa", "ttml", "dfxp", "tt"}
YOUTUBE_TRANSLATION_WAIT = 65


def wait_for_youtube_translation(context, info, selected_subtitle, *, clock=None, sleep=None):
    """YouTube translated captions need the extraction session to age first.

    Waiting between separate Download clicks does not help: each extraction
    creates another fresh session. Keep this session alive and remain cancellable.
    See yt-dlp issue #13831 and maintainer PR #15709.
    """
    if not selected_subtitle or not selected_subtitle.get("translated"):
        return
    if str(info.get("extractor_key") or info.get("extractor") or "").lower() != "youtube":
        return
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    deadline = clock() + YOUTUBE_TRANSLATION_WAIT
    context.write("Allowing the YouTube translation session to age before fetching the selected captions.")
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            break
        context.update(1, f"Preparing YouTube translation · {math.ceil(remaining)} s remaining")
        sleep(min(1, remaining))
    context.update(2, "Downloading the selected subtitles")


def validate_subtitle_selection(language: str | None, source: str, output_format: str, *, mode="embed", burn_size="source") -> None:
    if not isinstance(source, str) or source not in {"manual", "automatic"}:
        raise ValueError("Choose creator subtitles or automatic captions")
    if not isinstance(mode, str) or mode not in {"embed", "burn"}:
        raise ValueError("Choose burned-in or switchable subtitles")
    if not isinstance(burn_size, str) or burn_size not in {"source", "1080"}:
        raise ValueError("Choose source size or 1080p for burned subtitles")
    if language is None:
        return
    if (not isinstance(language, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", language)
            or language in {"all", "live_chat"}):
        raise ValueError("The selected subtitle language is invalid")
    if output_format in AUDIO_FORMATS:
        raise ValueError("Subtitles require a video output format")


def _caption_query(entry):
    return parse_qs(urlsplit(entry.get("url") or "").query)


def _base_language(language):
    base = str(language or "").replace("_", "-").split("-", 1)[0].lower()
    return {"iw": "he", "in": "id", "ji": "yi"}.get(base, base)


def normalise_caption_sources(info):
    """Avoid translating from an arbitrary dub when original-audio subs exist.

    yt-dlp can group translations from every ASR audio language under one key.
    Its last VTT otherwise wins, which need not be the original video language.
    """
    audio = audio_tracks_from_formats(info.get("formats") or [])
    original = next((track for track in audio if track["original"]), None)
    original = original or next((track for track in audio if track["default"]), None)
    original_language = _base_language(original["language"] if original else info.get("language"))
    captions = {}
    for language, entries in (info.get("automatic_captions") or {}).items():
        native, from_original = [], []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            query = _caption_query(entry)
            source = _base_language((query.get("lang") or [""])[0])
            translated = bool(query.get("tlang"))
            if source and source == _base_language(language) and not translated:
                native.append(entry)
            if source and source == original_language:
                from_original.append(entry)
        if language.endswith("-orig"):
            captions[language] = native or entries
        else:
            captions[language] = from_original or native or entries
    info["automatic_captions"] = captions
    return info


def _preferred_subtitle(entries):
    for extension in ("srt", "vtt", "ttml", "dfxp"):
        matches = [entry for entry in entries if entry.get("ext") == extension]
        if matches:
            return matches[-1]
    return entries[-1]


def subtitle_tracks_from_info(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose actual downloadable tracks, never invent a translation language."""
    normalise_caption_sources(info)
    tracks = []
    for source, key in (("manual", "subtitles"), ("automatic", "automatic_captions")):
        for language, entries in (info.get(key) or {}).items():
            try:
                validate_subtitle_selection(language, source, "mp4")
            except ValueError:
                continue
            usable = [entry for entry in entries if isinstance(entry, dict)
                      and (entry.get("url") or entry.get("data"))
                      and (not entry.get("ext") or entry["ext"] in _SUBTITLE_EXTS)]
            if not usable:
                continue
            selected = _preferred_subtitle(usable)
            query = _caption_query(selected)
            source_language = (query.get("lang") or [None])[0]
            translated = bool(query.get("tlang"))
            label = str(selected.get("name") or language)
            original_caption = source == "automatic" and language.endswith("-orig") and not translated
            if original_caption:
                label = re.sub(r"\s*\(Original\)\s*$", "", label, flags=re.I)
            tracks.append({
                "language": language,
                "source": source,
                "label": label,
                "automatic": source == "automatic",
                "translated": translated,
                "sourceLanguage": source_language,
                "originalCaption": original_caption,
            })
    return sorted(tracks, key=lambda track: (track["label"].casefold(), track["source"] != "manual"))


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
        role = next((name for name in ("original", "dubbed", "descriptive", "commentary") if name in note.lower()), "")
        if not first_note or first_note.lower() in quality_words or re.fullmatch(r"\d+p(?:\d+)?|\d+k|DASH audio", first_note, re.I):
            first_note = language
        if role and role not in first_note.lower():
            first_note = f"{first_note} ({role})"
        label = first_note
        key = (language.lower(), role)
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
            "hasVideo": item.get("vcodec") not in (None, "none"),
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
    # A muxed fallback can otherwise silently keep the source's default audio.
    # Muxed tracks are handled explicitly after refreshing the source metadata.
    return f"bestvideo+{audio_format_id}"


def fast_burn_video_format(info):
    """Prefer a native HD/30 stream over decoding 4K when HD is requested."""
    candidates = [f for f in info.get("formats") or []
                  if f.get("vcodec") not in (None, "none") and f.get("acodec") in (None, "none")
                  and 0 < int(f.get("width") or 0) <= 1920 and 0 < int(f.get("height") or 0) <= 1920
                  and min(int(f["width"]), int(f["height"])) <= 1080 and float(f.get("fps") or 30) <= 30
                  and re.fullmatch(r"[A-Za-z0-9._+-]+", str(f.get("format_id") or ""))]
    if not candidates:
        return None
    pixels = max(int(f["width"]) * int(f["height"]) for f in candidates)
    candidates = [f for f in candidates if int(f["width"]) * int(f["height"]) == pixels]
    h264 = [f for f in candidates if str(f["vcodec"]).startswith(("avc1", "h264"))]
    return max(h264 or candidates, key=lambda f: (float(f.get("fps") or 0), float(f.get("tbr") or 0)))["format_id"]


def inspect_url(url: str, cookie_file: str | None = None) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        raise ValueError("Enter a complete http:// or https:// media URL")
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        # YouTube omits part of its translation catalogue unless caption
        # discovery is requested. download=False still fetches no media/subs.
        "writeautomaticsub": True,
        "socket_timeout": 30,
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
        "subtitleTracks": subtitle_tracks_from_info(info),
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
    subtitle_language: str | None = None,
    subtitle_source: str = "manual",
    subtitle_mode: str = "embed",
    burn_size: str = "source",
    existing_media_path: str | None = None,
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
    validate_subtitle_selection(subtitle_language, subtitle_source, target_format, mode=subtitle_mode, burn_size=burn_size)
    download_format_selector(target_format, audio_format_id)
    if existing_media_path and (not subtitle_language or not Path(existing_media_path).is_file()):
        raise ValueError("Choose an existing video and a subtitle language")
    if existing_media_path and audio_format_id:
        raise ValueError("An existing video keeps its own audio; do not select another audio track")

    destination = Path(output_directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    # Keep subtitle sidecars, intermediate conversions and concurrent downloads
    # separate. Only the verified final video is moved to the user's folder.
    with tempfile.TemporaryDirectory(prefix=".clipharbor-", dir=destination) as temporary:
        return _download(context, url=url, destination=destination, working=Path(temporary),
                         target_format=target_format, x_compatible=x_compatible,
                         audio_format_id=audio_format_id, audio_track_label=audio_track_label,
                         subtitle_language=subtitle_language, subtitle_source=subtitle_source,
                         subtitle_mode=subtitle_mode, burn_size=burn_size, existing_media_path=existing_media_path,
                         cookie_file=cookie_file, register=register)


def _download(context, *, url, destination, working, target_format, x_compatible,
              audio_format_id, audio_track_label, subtitle_language, subtitle_source, subtitle_mode,
              burn_size, existing_media_path, cookie_file, register):
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
        "format": download_format_selector(target_format),
        "outtmpl": str(working / "%(title).160B [source].%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mkv",
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 8,
        "socket_timeout": 30,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [post_hook],
        "windowsfilenames": True,
        "writesubtitles": bool(subtitle_language and subtitle_source == "manual"),
        "writeautomaticsub": bool(subtitle_language and subtitle_source == "automatic"),
        "skip_download": bool(existing_media_path),
    }
    if subtitle_language:
        options.update(subtitleslangs=[f"^{re.escape(subtitle_language)}$"],
                       subtitlesformat="srt/vtt/ttml/dfxp/best",
                       postprocessors=[{"key": "FFmpegSubtitlesConvertor", "format": "srt"}])
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
    if cookie_file:
        cookie_path = Path(cookie_file).expanduser().resolve()
        if not cookie_path.is_file():
            raise FileNotFoundError(f"Cookies file not found: {cookie_path}")
        options["cookiefile"] = str(cookie_path)

    selected_subtitle = None
    with yt_dlp.YoutubeDL(options) as ydl:
        if subtitle_language or audio_format_id:
            info = ydl.extract_info(url, download=False)
            if info.get("entries"):
                info = next((entry for entry in info["entries"] if entry), info)
            if subtitle_language:
                selected_subtitle = next((track for track in subtitle_tracks_from_info(info)
                                          if track["language"] == subtitle_language and track["source"] == subtitle_source), None)
                if not selected_subtitle:
                    raise ValueError("The selected subtitles are no longer available. Inspect the video again.")
            if audio_format_id:
                selected_format = download_format_selector(target_format, audio_format_id)
                selected_audio = next((item for item in info.get("formats", [])
                                       if item.get("format_id") == audio_format_id and item.get("acodec") not in (None, "none")), None)
                if not selected_audio:
                    raise ValueError("The selected audio track is no longer available. Inspect the video again.")
                if selected_audio.get("vcodec") not in (None, "none"):
                    # Facebook can expose a complete video per dubbed language.
                    # Keep that version's audio instead of merging default audio.
                    selected_format = audio_format_id
                ydl.params["format"] = selected_format
                ydl.format_selector = ydl.build_format_selector(selected_format)
            if subtitle_language and subtitle_mode == "burn" and burn_size == "1080" and not existing_media_path:
                audio_is_muxed = audio_format_id and selected_audio.get("vcodec") not in (None, "none")
                video_format = fast_burn_video_format(info)
                if video_format and not audio_is_muxed:
                    selected_format = f"{video_format}+{audio_format_id or 'bestaudio'}/{video_format}"
                    ydl.params["format"] = selected_format
                    ydl.format_selector = ydl.build_format_selector(selected_format)
            wait_for_youtube_translation(context, info, selected_subtitle)
            try:
                info = ydl.process_ie_result(info, download=True)
            except yt_dlp.utils.DownloadError as error:
                if subtitle_language and "subtitle" in str(error).lower() and "429" in str(error):
                    raise RuntimeError("The source is temporarily rate-limiting subtitle downloads (HTTP 429). Wait and try again. No video without the requested subtitles was saved.") from None
                raise
        else:
            info = ydl.extract_info(url, download=True)

    if info.get("entries"):
        info = next((entry for entry in info["entries"] if entry), info)

    subtitle_file = None
    if subtitle_language:
        subtitle_data = (info.get("requested_subtitles") or {}).get(subtitle_language) or {}
        subtitle_file = Path(subtitle_data["filepath"]).resolve() if subtitle_data.get("filepath") else None
        if not subtitle_file or not subtitle_file.is_file() or subtitle_file.parent != working.resolve():
            raise RuntimeError("The selected subtitles could not be downloaded. No video without the requested subtitles was saved.")
        if subtitle_file.suffix.lower() != ".srt":
            from .ffmpeg import run
            converted_subtitle = working / "selected-captions.srt"
            run(["ffmpeg", "-hide_banner", "-i", str(subtitle_file), "-c:s", "srt", "-y", str(converted_subtitle)],
                context.write, check_cancelled=getattr(context, "check_cancelled", None))
            subtitle_file = converted_subtitle

    def is_media(path):
        return (path.is_file() and path.parent.resolve() == working.resolve()
                and path.suffix.lstrip(".").lower() not in _SUBTITLE_EXTS | {"json", "part", "ytdl"}
                and path != subtitle_file)

    primary = [info.get("filepath"), *(item.get("filepath") for item in info.get("requested_downloads") or [])]
    candidates = [Path(path).resolve() for path in primary if path and is_media(Path(path))]
    primary_candidates = candidates[:]
    if not candidates:
        candidates = [p.resolve() for p in observed if is_media(p)]
    if not candidates:
        candidates = [p for p in working.iterdir() if is_media(p)]
    if not candidates and not existing_media_path:
        raise RuntimeError("yt-dlp completed but the downloaded file could not be located")
    source = Path(existing_media_path).resolve() if existing_media_path else (primary_candidates[0] if primary_candidates else max(candidates, key=lambda p: p.stat().st_mtime))
    title = _safe_title((f"{source.stem} [{selected_subtitle['label']} {'burned-in' if subtitle_mode == 'burn' else 'subtitles'}]")
                        if existing_media_path else info.get("title") or source.stem.replace(" [source]", ""))
    final_path = source
    converted = False
    skipped_x_conversion = False

    burn = bool(subtitle_file and subtitle_mode == "burn")
    if target_format != "original" or burn:
        render_format = target_format if target_format != "original" else "mkv"
        output = working / f"converted.{render_format}"
        context.update(82, f"Rendering {target_format.upper()} output")
        convert(source, output, render_format, x_compatible=x_compatible, on_line=context.write,
                on_progress=lambda ratio, mode: context.update(82 + ratio * 13, f"{mode} · {ratio:.0%}"),
                check_cancelled=getattr(context, "check_cancelled", None),
                subtitle_path=subtitle_file if burn else None, burn_size=burn_size)
        final_path = output
        converted = True

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

    if subtitle_file and not burn:
        context.update(97, "Adding the selected subtitles without re-encoding video")
        extension = final_path.suffix.lstrip(".").lower()
        if extension not in {"mp4", "mkv", "mov", "webm"}:
            extension = "mkv"
        captioned = working / f"captioned.{extension}"
        embed_subtitle(final_path, subtitle_file, captioned, language=subtitle_language,
                       title=selected_subtitle["label"], on_line=context.write,
                       check_cancelled=getattr(context, "check_cancelled", None))
        final_path = captioned

    with _output_lock:
        if hasattr(context, "check_cancelled"):
            context.check_cancelled()
        finished = unique_output(destination, title, final_path.suffix.lstrip("."))
        final_path.replace(finished)
    final_path = finished
    media = probe(final_path)
    return {
        "path": str(final_path),
        "token": register(final_path),
        "media": media,
        "converted": converted,
        "xCompatible": x_compatible,
        "xConversionSkipped": skipped_x_conversion,
        "audioTrack": audio_track_label or None,
        "subtitleTrack": selected_subtitle,
        "subtitleRendering": subtitle_mode if selected_subtitle else None,
        "burnSize": burn_size if burn else None,
    }
