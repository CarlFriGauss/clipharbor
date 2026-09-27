from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

from .ffmpeg import atempo_chain, run, unique_output, x_compatibility
from .jobs import JobContext
from .playback import editing_source


def _number(value: Any, name: str, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{name} is outside the allowed range")
    return result


def validate_project(project: dict[str, Any]) -> dict[str, Any]:
    settings = project.get("settings") or {}
    width = int(_number(settings.get("width", 1920), "Width", 16))
    height = int(_number(settings.get("height", 1080), "Height", 16))
    fps = min(240.0, _number(settings.get("fps", 30), "Frame rate", 1))
    quality = str(settings.get("quality", "master")).lower()
    if quality not in {"master", "high", "compact"}:
        quality = "master"
    auto_balance = settings.get("autoBalance", True) is not False
    x_compatible = settings.get("xCompatible", False) is True
    if x_compatible:
        width, height = _x_canvas(width, height)
        fps = min(40.0, fps)
    assets = {str(asset["id"]): asset for asset in project.get("assets", [])}
    clips: list[dict[str, Any]] = []
    for raw in project.get("clips", []):
        asset_id = str(raw.get("assetId", ""))
        if asset_id not in assets:
            raise ValueError(f"Clip refers to missing asset {asset_id}")
        source = Path(assets[asset_id]["path"]).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Source file no longer exists: {source}")
        clip = dict(raw)
        clip["assetPath"] = str(source)
        clip["start"] = _number(raw.get("start", 0), "Timeline start", 0)
        clip["in"] = _number(raw.get("in", 0), "Source in", 0)
        clip["out"] = _number(raw.get("out"), "Source out", 0)
        clip["speed"] = _number(raw.get("speed", 1), "Speed", 0.25)
        if clip["speed"] > 4:
            raise ValueError("Speed cannot exceed 4x")
        if clip["out"] <= clip["in"]:
            raise ValueError("Every clip must end after its in point")
        clip["volume"] = _number(raw.get("volume", 1), "Volume", 0)
        clip["layer"] = int(raw.get("layer", 0))
        clip["kind"] = "audio" if raw.get("kind") == "audio" else "video"
        clip["duration"] = (clip["out"] - clip["in"]) / clip["speed"]
        clips.append(clip)
    if not clips:
        raise ValueError("Add at least one clip to the timeline")
    return {"settings": {"width": width, "height": height, "fps": fps, "quality": quality, "autoBalance": auto_balance, "xCompatible": x_compatible}, "assets": assets, "clips": clips}


def _x_canvas(width: int, height: int) -> tuple[int, int]:
    """Largest even canvas no larger than the source within X web limits."""
    if width >= height:
        scale = min(1.0, 1920 / width, 1200 / height)
    else:
        scale = min(1.0, 1200 / width, 1900 / height)
    target_width = max(2, int(width * scale) // 2 * 2)
    target_height = max(2, int(height * scale) // 2 * 2)
    aspect = target_width / target_height
    if aspect > 2.39:
        target_height = max(target_height, math.ceil(target_width / 2.39 / 2) * 2)
    elif aspect < 1 / 2.39:
        target_width = max(target_width, math.ceil(target_height / 2.39 / 2) * 2)
    return target_width, target_height


def build_render_command(project: dict[str, Any], output: Path, output_format: str) -> list[str]:
    normalized = validate_project(project)
    clips = normalized["clips"]
    settings = normalized["settings"]
    duration = max(clip["start"] + clip["duration"] for clip in clips)
    inputs: list[str] = []
    filters: list[str] = []
    # Seek each source before opening it. FFmpeg still decodes forward from the
    # preceding keyframe and re-encodes the exact requested interval, but it no
    # longer decodes a long source from 00:00 once for every late timeline clip.
    for clip in clips:
        asset = normalized["assets"][str(clip["assetId"])]
        clip["preroll"] = min(clip["in"], .25) if asset.get("indexedAudio") else 0
        inputs += [
            "-ss", f"{clip['in'] - clip['preroll']:.6f}",
            "-t", f"{clip['out'] - clip['in'] + clip['preroll']:.6f}",
            "-i", clip["assetPath"],
        ]

    video_clips = sorted(
        ((index, clip) for index, clip in enumerate(clips) if clip["kind"] == "video" and not clip.get("hidden")),
        key=lambda item: (item[1]["layer"], item[1]["start"]),
    )
    audio_labels: list[str] = []
    width, height, fps = settings["width"], settings["height"], settings["fps"]

    if video_clips and output_format not in {"mp3", "m4a", "wav"}:
        filters.append(f"color=c=0x101319:s={width}x{height}:r={fps}:d={duration:.6f}[base0]")
        previous = "base0"
        for sequence, (index, clip) in enumerate(video_clips, start=1):
            speed = clip["speed"]
            timeline_start = clip["start"]
            filters.append(
                f"[{index}:v:0]trim=duration={clip['out'] - clip['in']:.6f},"
                f"setpts=(PTS-STARTPTS)/{speed:.8g},fps={fps}:round=near,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setpts=PTS+{timeline_start:.6f}/TB[v{index}]"
            )
            output_label = f"base{sequence}"
            clip_end = timeline_start + clip["duration"]
            filters.append(
                f"[{previous}][v{index}]overlay=eof_action=pass:shortest=0:"
                f"enable='between(t,{timeline_start:.6f},{clip_end:.6f})'[{output_label}]"
            )
            previous = output_label
        video_output = previous
    else:
        video_output = None

    audible_video_clips = [
        item for item in clips
        if item["kind"] == "video"
        and not item.get("muted")
        and item["volume"] > 0
        and normalized["assets"][str(item["assetId"])].get("audio")
    ]
    for index, clip in enumerate(clips):
        if clip.get("muted") or clip["volume"] == 0:
            continue
        # Audio clips always have audio. Video clips may not, so the caller supplies probe metadata.
        asset = normalized["assets"][str(clip["assetId"])]
        if not asset.get("audio"):
            continue
        delay = max(0, round(clip["start"] * 1000))
        volume_filter = f"volume={clip['volume']:.8g}"
        if settings["autoBalance"] and clip["kind"] == "audio":
            overlaps: list[str] = []
            for video_clip in audible_video_clips:
                overlap_start = max(clip["start"], video_clip["start"])
                overlap_end = min(clip["start"] + clip["duration"], video_clip["start"] + video_clip["duration"])
                if overlap_end > overlap_start:
                    local_start = overlap_start - clip["start"]
                    local_end = overlap_end - clip["start"]
                    overlaps.append(f"between(t,{local_start:.6f},{local_end:.6f})")
            if overlaps:
                condition = "+".join(overlaps)
                volume_filter = f"volume='{clip['volume']:.8g}*if(gt({condition},0),0.38,1)':eval=frame"
        filters.append(
            f"[{index}:a:0]atrim=start={clip['preroll']:.6f}:duration={clip['out'] - clip['in']:.6f},"
            f"asetpts=PTS-STARTPTS,{atempo_chain(clip['speed'])},"
            f"{volume_filter},aresample=48000:async=1:first_pts=0,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"adelay={delay}:all=1[a{index}]"
        )
        audio_labels.append(f"[a{index}]")

    audio_output = None
    if audio_labels:
        audio_output = "aout"
        filters.append(
            "".join(audio_labels)
            + f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=0:normalize=0,"
            + "acompressor=threshold=0.398:ratio=8:knee=2:attack=3:release=120,"
            + "alimiter=limit=0.95:attack=5:release=50:latency=1,"
            + f"apad=whole_dur={duration:.6f},atrim=duration={duration:.6f},aresample=48000:async=1:first_pts=0[{audio_output}]"
        )

    command = ["ffmpeg", "-hide_banner", "-nostats", "-progress", "pipe:1", *inputs, "-filter_complex", ";".join(filters)]
    if video_output:
        command += ["-map", f"[{video_output}]"]
    if audio_output:
        command += ["-map", f"[{audio_output}]"]

    crf = {"master": "14", "high": "17", "compact": "21"}[settings["quality"]]
    audio_rate = {"master": "320k", "high": "256k", "compact": "192k"}[settings["quality"]]
    if output_format == "mp4":
        if settings["xCompatible"]:
            command += [
                "-c:v", "libx264", "-preset", "medium", "-crf", "14",
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2",
                "-maxrate", "24M", "-bufsize", "48M", "-c:a", "aac",
                "-profile:a", "aac_low", "-b:a", "256k", "-ac", "2", "-ar", "48000",
                "-movflags", "+faststart",
            ]
        else:
            command += ["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", audio_rate, "-movflags", "+faststart"]
    elif output_format == "mkv":
        command += ["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-c:a", "aac", "-b:a", audio_rate]
    elif output_format == "webm":
        command += ["-c:v", "libvpx-vp9", "-crf", "18", "-b:v", "0", "-c:a", "libopus", "-b:a", "160k"]
    elif output_format == "mov":
        command += ["-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", audio_rate]
    elif output_format == "mp3":
        command += ["-vn", "-c:a", "libmp3lame", "-q:a", "0"]
    elif output_format == "m4a":
        command += ["-vn", "-c:a", "aac", "-b:a", "256k"]
    elif output_format == "wav":
        command += ["-vn", "-c:a", "pcm_s24le"]
    else:
        raise ValueError(f"Unsupported render format: {output_format}")
    command += ["-max_muxing_queue_size", "4096", "-t", f"{duration:.6f}", "-y", str(output)]
    return command


def render(
    context: JobContext,
    *,
    project: dict[str, Any],
    output_directory: str,
    filename: str,
    output_format: str,
    save_project: bool,
    register: Callable[[Path], str],
) -> dict[str, Any]:
    destination = Path(output_directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c not in '<>:"/\\|?*' else "_" for c in filename).strip(" .") or "ClipHarbor export"
    output = unique_output(destination, Path(safe_name).stem, output_format)
    context.update(2, "Preparing precise audio indexes")
    # Keep saved projects pointing at originals; only this render uses the
    # losslessly indexed sources also used by the browser and waveform.
    render_assets = []
    for asset in project.get("assets", []):
        prepared = editing_source(asset["path"])
        render_assets.append({**asset, "path": str(prepared),
                              "indexedAudio": prepared != Path(asset["path"]).expanduser().resolve()})
    render_project = {**project, "assets": render_assets}
    command = build_render_command(render_project, output, output_format)
    context.update(5, "Building FFmpeg composition")

    total_duration = max(
        float(c.get("start", 0)) + (float(c["out"]) - float(c.get("in", 0))) / float(c.get("speed", 1))
        for c in project["clips"]
    )

    def log(line: str) -> None:
        context.write(line)
        seconds = None
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                # Despite its historical name, out_time_ms is expressed in
                # microseconds by FFmpeg's progress protocol.
                seconds = float(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                pass
        elif line.startswith("out_time="):
            try:
                hours, minutes, raw_seconds = line.split("=", 1)[1].split(":")
                seconds = int(hours) * 3600 + int(minutes) * 60 + float(raw_seconds)
            except ValueError:
                pass
        if seconds is not None:
            context.update(min(98, 5 + seconds / max(total_duration, 0.01) * 93), "Rendering timeline")

    run(command, log)
    from .ffmpeg import probe
    media = probe(output)
    # Codec frame padding is expected; seconds of extra/missing timeline are not.
    tolerance = 0.12
    if media.get("video"):
        tolerance = max(tolerance, 1 / float(project.get("settings", {}).get("fps", 30)) + 0.03)
    if abs(media["duration"] - total_duration) > tolerance:
        raise RuntimeError(
            f"Export duration check failed: timeline {total_duration:.3f}s, "
            f"file {media['duration']:.3f}s. Output retained at {output} for inspection."
        )
    result = {"path": str(output), "token": register(output), "media": media, "timelineDuration": total_duration}
    if project.get("settings", {}).get("xCompatible") is True:
        compatibility = x_compatibility(media)
        if not compatibility["compatible"]:
            raise RuntimeError("X-compatible render failed validation: " + "; ".join(compatibility["issues"]))
        result["xCompatible"] = True
        result["xCompatibility"] = compatibility
    if save_project:
        project_file = output.with_suffix(output.suffix + ".mediaforge.json")
        project_file.write_text(json.dumps(project, indent=2), encoding="utf-8")
        result["projectPath"] = str(project_file)
    return result
