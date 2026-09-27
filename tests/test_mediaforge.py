from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mediaforge.editor import _x_canvas, build_render_command
from mediaforge.downloader import audio_tracks_from_formats, download_format_selector
from mediaforge.projects import ProjectStore
from mediaforge.ffmpeg import atempo_chain, convert, probe, x_compatibility
from mediaforge.waveform import extract_waveform


def test_atempo_chain_stays_inside_ffmpeg_factor_limits():
    assert atempo_chain(1) == "atempo=1"
    assert atempo_chain(4) == "atempo=2,atempo=2"
    assert atempo_chain(0.25) == "atempo=0.5,atempo=0.5"


def test_x_compatibility_uses_regular_web_upload_limits():
    media = {
        "format": "mov,mp4",
        "size": 100,
        "duration": 20,
        "bitRate": 10_000_000,
        "video": {
            "codec": "h264", "pixelFormat": "yuv420p", "fieldOrder": "progressive",
            "fps": 60, "width": 3840, "height": 2160,
        },
        "audio": {"codec": "aac", "profile": "LC", "channels": 2},
    }
    result = x_compatibility(media)
    assert not result["compatible"]
    assert any("40 FPS" in issue for issue in result["issues"])
    assert any("Resolution" in issue for issue in result["issues"])
    assert not result["videoCopySafe"]


def test_x_export_uses_largest_allowed_canvas_and_profile(tmp_path: Path):
    source = tmp_path / "source.mp4"
    source.touch()
    project = {
        "settings": {"width": 3840, "height": 2160, "fps": 60, "quality": "compact", "xCompatible": True},
        "assets": [{"id": "asset", "path": str(source), "audio": True}],
        "clips": [{"id": "clip", "assetId": "asset", "kind": "video", "start": 0, "in": 0, "out": 1, "speed": 1, "volume": 1, "layer": 0}],
    }
    command = build_render_command(project, tmp_path / "x.mp4", "mp4")
    graph = command[command.index("-filter_complex") + 1]
    assert "s=1920x1080:r=40" in graph
    assert command[command.index("-profile:v") + 1] == "high"
    assert command[command.index("-maxrate") + 1] == "24M"
    assert command[command.index("-profile:a") + 1] == "aac_low"
    assert _x_canvas(1080, 1920) == (1068, 1900)


def test_named_projects_round_trip_on_disk(tmp_path: Path):
    store = ProjectStore(tmp_path / "projects")
    saved = store.save("Project One", {"assets": [{"id": "a"}], "clips": []})
    assert store.list()[0]["name"] == "Project One"
    loaded = store.get(saved["id"])
    assert loaded["project"]["assets"][0]["id"] == "a"
    updated = store.save("Project One renamed", {"assets": [], "clips": []}, saved["id"])
    assert updated["id"] == saved["id"]
    assert len(store.list()) == 1


def test_audio_tracks_collapse_quality_variants_and_keep_dubs_distinct():
    formats = [
        {"format_id": "140-0", "vcodec": "none", "acodec": "aac", "language": "en", "format_note": "English original (default), medium", "abr": 128, "asr": 44100, "language_preference": 10},
        {"format_id": "251-0", "vcodec": "none", "acodec": "opus", "language": "en", "format_note": "English original (default), medium", "abr": 150, "asr": 48000, "language_preference": 10},
        {"format_id": "140-2", "vcodec": "none", "acodec": "aac", "language": "es", "format_note": "Spanish (dubbed), medium", "abr": 128, "asr": 44100, "language_preference": -1},
    ]
    tracks = audio_tracks_from_formats(formats)
    assert len(tracks) == 2
    assert tracks[0]["formatId"] == "251-0"
    assert tracks[0]["original"] is True
    assert tracks[1]["dubbed"] is True
    assert download_format_selector("mp4", tracks[1]["formatId"]) == "bestvideo+140-2/bestvideo*+140-2"
    assert download_format_selector("mp3", "140-2") == "140-2"


def test_timeline_uses_accurate_per_clip_input_seeking(tmp_path: Path):
    source = tmp_path / "long-source.mp4"
    source.touch()
    project = {
        "settings": {"width": 320, "height": 180, "fps": 30},
        "assets": [{"id": "asset", "path": str(source), "audio": True}],
        "clips": [{"id": "late", "assetId": "asset", "kind": "video", "start": 0, "in": 1527.125, "out": 1532.25, "speed": 1, "volume": 1, "muted": False, "layer": 0}],
    }
    command = build_render_command(project, tmp_path / "render.mp4", "mp4")
    assert command[command.index("-ss") + 1] == "1527.125000"
    assert command[command.index("-t") + 1] == "5.125000"
    graph = command[command.index("-filter_complex") + 1]
    assert "trim=start=1527" not in graph
    assert "atrim=start=1527" not in graph
    assert "-progress" in command


def test_timeline_auto_balances_music_and_protects_master_peak(tmp_path: Path):
    source = tmp_path / "source.mp4"
    source.touch()
    project = {
        "settings": {"width": 320, "height": 180, "fps": 30, "autoBalance": True},
        "assets": [{"id": "asset", "path": str(source), "audio": True}],
        "clips": [
            {"id": "video", "assetId": "asset", "kind": "video", "start": 2, "in": 0, "out": 5, "speed": 1, "volume": 1, "muted": False, "layer": 0},
            {"id": "music", "assetId": "asset", "kind": "audio", "start": 0, "in": 0, "out": 8, "speed": 1, "volume": 1, "muted": False, "layer": 0},
        ],
    }
    command = build_render_command(project, tmp_path / "render.mp4", "mp4")
    graph = command[command.index("-filter_complex") + 1]
    assert "between(t,2.000000,7.000000)" in graph
    assert "0.38" in graph
    assert "normalize=0" in graph
    assert "acompressor=" in graph
    assert "alimiter=limit=0.95" in graph
    assert "latency=1" in graph


@pytest.mark.integration
def test_ffmpeg_timeline_renders_split_speed_and_audio(tmp_path: Path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "render.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=660:duration=1", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-y", str(source),
        ],
        check=True,
    )
    media = probe(source)
    project = {
        "settings": {"width": 320, "height": 180, "fps": 30},
        "assets": [{"id": "asset", "path": str(source), "audio": True}],
        "clips": [
            {"id": "left", "assetId": "asset", "kind": "video", "start": 0, "in": 0, "out": .5, "speed": 1, "volume": 1, "muted": False, "layer": 0},
            {"id": "right", "assetId": "asset", "kind": "video", "start": .5, "in": .5, "out": 1, "speed": .5, "volume": .4, "muted": False, "layer": 0},
            {"id": "overlay", "assetId": "asset", "kind": "video", "start": .25, "in": 0, "out": .5, "speed": 1, "volume": 0, "muted": True, "layer": 1},
        ],
    }
    command = build_render_command(project, output, "mp4")
    subprocess.run(command, check=True, capture_output=True)
    rendered = probe(output)
    assert rendered["video"]["codec"] == "h264"
    assert rendered["audio"]["codec"] == "aac"
    assert 1.4 <= rendered["duration"] <= 1.6
    assert media["duration"] >= .9


@pytest.mark.integration
def test_waveform_extracts_a_normalized_audio_envelope(tmp_path: Path):
    source = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4", "-y", str(source)],
        check=True,
    )
    waveform = extract_waveform(source, 256)
    assert len(waveform["samples"]) > 10
    assert max(waveform["samples"]) == 1
    assert waveform["peak"] > 0


@pytest.mark.integration
def test_x_conversion_reencodes_only_when_probe_requires_it(tmp_path: Path):
    source = tmp_path / "sixty-fps.mp4"
    output = tmp_path / "x-ready.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=60:duration=0.5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-y", str(source),
        ],
        check=True,
    )
    assert not x_compatibility(probe(source))["compatible"]
    convert(source, output, "mp4", x_compatible=True)
    final = probe(output)
    assert final["video"]["fps"] <= 40.01
    assert x_compatibility(final)["compatible"]
