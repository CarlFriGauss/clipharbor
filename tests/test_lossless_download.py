"""Original-quality download policy: mux once, never silently encode media."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from mediaforge import downloader, ffmpeg
from mediaforge.jobs import JobCancelled
from test_source_tracks import context, fixture_extractor, media_site


def test_language_choice_uses_downloader_quality_order_not_cross_codec_bit_rates():
    formats = [
        {"format_id": "aac", "acodec": "aac", "vcodec": "none", "language": "en", "abr": 192,
         "format_note": "English original"},
        {"format_id": "opus", "acodec": "opus", "vcodec": "none", "language": "en", "abr": 128,
         "format_note": "English original"},
    ]
    assert downloader.audio_tracks_from_formats(formats)[0]["formatId"] == "opus"


def test_one_mux_copies_video_and_multichannel_audio_and_reports_phase(monkeypatch, tmp_path):
    source = tmp_path / "source.mkv"; source.touch()
    caption = tmp_path / "ar.srt"; caption.touch()
    media = {"duration": 10, "video": {"codec": "av1", "width": 3840, "height": 2160, "fps": 60},
             "audio": {"codec": "aac", "channels": 6}, "subtitles": [{"codec": "mov_text"}]}
    monkeypatch.setattr(ffmpeg, "probe", lambda p: media)
    commands = []; progress = []
    def run(command, on_line, **kwargs):
        commands.append(command)
        on_line("out_time_us=5000000"); on_line("progress=end")
    monkeypatch.setattr(ffmpeg, "run", run)
    output, fallback = ffmpeg.remux_original(source, tmp_path / "out.mp4", subtitle_path=caption,
        language="ar", title="Arabic", on_progress=lambda ratio, mode: progress.append((ratio, mode)))
    assert output.suffix == ".mp4" and fallback is None and len(commands) == 1
    command = commands[0]
    assert command[command.index("-c:v") + 1] == command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-c:s") + 1] == "mov_text"
    assert not {"-ac", "-ar", "-vf", "-r", "-crf", "-preset"}.intersection(command)
    assert any(ratio == .5 for ratio, _ in progress) and progress[-1][0] == 1


def test_unsupported_container_falls_back_to_copying_into_mkv(monkeypatch, tmp_path):
    source = tmp_path / "source.mkv"; source.write_bytes(b"original")
    monkeypatch.setattr(ffmpeg, "probe", lambda p: {"duration": 1, "video": {"codec": "h264"}, "audio": {"codec": "opus"}})
    commands = []
    def run(command, on_line, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"muxed")
        if command[-1].endswith(".mov"):
            on_line("opus only supported in MP4.")
            raise RuntimeError("FFmpeg exited with status 1")
    monkeypatch.setattr(ffmpeg, "run", run)
    output, fallback = ffmpeg.remux_original(source, tmp_path / "out.mov")
    assert output == tmp_path / "out.mkv" and "keep original video/audio quality" in fallback
    assert len(commands) == 2 and not (tmp_path / "out.mov").exists()
    assert all(command[command.index("-c:v") + 1] == command[command.index("-c:a") + 1] == "copy" for command in commands)
    assert source.read_bytes() == b"original"


@pytest.mark.parametrize("error", ["No space left on device", "Permission denied"])
def test_storage_errors_do_not_get_retried_as_container_failures(monkeypatch, tmp_path, error):
    source = tmp_path / "source.mkv"; source.touch()
    calls = []
    def run(command, on_line, **kwargs):
        calls.append(command); on_line(error); raise RuntimeError("FFmpeg exited with status 1")
    monkeypatch.setattr(ffmpeg, "run", run)
    with pytest.raises(RuntimeError):
        ffmpeg.remux_original(source, tmp_path / "out.mp4", media={"duration": 1})
    assert len(calls) == 1


def test_cancel_does_not_start_a_fallback_mux(monkeypatch, tmp_path):
    source = tmp_path / "source.mkv"; source.touch()
    calls = []
    def run(command, on_line, **kwargs):
        calls.append(command); on_line("Could not find tag for codec opus"); raise RuntimeError("failed")
    def cancelled(): raise JobCancelled("cancelled")
    monkeypatch.setattr(ffmpeg, "run", run)
    with pytest.raises(JobCancelled):
        ffmpeg.remux_original(source, tmp_path / "out.mov", media={"duration": 1}, check_cancelled=cancelled)
    assert len(calls) == 1


def test_existing_input_and_output_cannot_be_overwritten(tmp_path):
    source = tmp_path / "original.mp4"; source.write_bytes(b"keep")
    with pytest.raises(ValueError):
        ffmpeg.remux_original(source, source)
    output = tmp_path / "out.mp4"; output.write_bytes(b"keep output")
    with pytest.raises(FileExistsError):
        ffmpeg.remux_original(source, output)
    assert source.read_bytes() == b"keep" and output.read_bytes() == b"keep output"


@pytest.fixture(scope="module")
def copy_sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("copy-quality")
    for name, video, audio in [("surround", "libx264", "aac"), ("opus", "libx264", "libopus"), ("av1-opus", "libaom-av1", "libopus")]:
        command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=0.4",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=" + ("5.1" if name == "surround" else "stereo"),
            "-t", "0.4", "-c:v", video, "-threads", "2", "-c:a", audio]
        if video == "libaom-av1": command += ["-cpu-used", "8"]
        subprocess.run([*command, "-y", str(root / (name + ".mkv"))], check=True, capture_output=True)
    caption = root / "ar.srt"
    caption.write_text("1\n00:00:00,000 --> 00:00:00,350\nمرحبا بالعالم\n", encoding="utf-8")
    return root


def packet_hashes(path, stream):
    data = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", stream, "-show_packets",
        "-show_entries", "packet=data_hash", "-show_data_hash", "sha256", "-of", "json", str(path)])
    return [entry["data_hash"] for entry in json.loads(data)["packets"]]


@pytest.mark.integration
@pytest.mark.parametrize("name,container,expected", [("surround", "mp4", "mp4"), ("opus", "mp4", "mp4"),
    ("av1-opus", "mp4", "mp4"), ("opus", "mov", "mkv"), ("surround", "webm", "mkv")])
def test_real_mux_preserves_packets_and_audio_channels(copy_sources, tmp_path, name, container, expected):
    source = copy_sources / (name + ".mkv")
    output, fallback = ffmpeg.remux_original(source, tmp_path / ("output." + container),
        subtitle_path=copy_sources / "ar.srt", language="ar", title="Arabic")
    assert output.suffix == "." + expected
    assert bool(fallback) == (expected != container)
    assert packet_hashes(source, "v:0") == packet_hashes(output, "v:0")
    assert packet_hashes(source, "a:0") == packet_hashes(output, "a:0")
    before, after = ffmpeg.probe(source), ffmpeg.probe(output)
    assert after["audio"]["codec"] == before["audio"]["codec"] and after["audio"]["channels"] == before["audio"]["channels"]
    assert after["video"]["width"] == before["video"]["width"] and after["video"]["fps"] == before["video"]["fps"]
    assert after["subtitles"][0]["language"] == "ara"


@pytest.mark.integration
def test_download_with_selected_subtitles_uses_one_media_mux(copy_sources, media_site, tmp_path, monkeypatch):
    root, base = media_site
    source = root / "opus-source.mkv"; source.write_bytes((copy_sources / "opus.mkv").read_bytes())
    fixture_extractor(monkeypatch, {"id": "copy-test", "title": "Original quality", "formats": [
        {"format_id": "original", "url": base + "/opus-source.mkv", "vcodec": "h264", "acodec": "opus", "ext": "mkv"}],
        "subtitles": {"fr": [{"url": base + "/fr.vtt", "ext": "vtt"}]}})
    commands = []; real_run = ffmpeg.run
    def run(command, *args, **kwargs): commands.append(command); return real_run(command, *args, **kwargs)
    monkeypatch.setattr(ffmpeg, "run", run)
    result = downloader.download(context(), url=base + "/track-fixture", output_directory=str(tmp_path),
        output_format="mp4", subtitle_language="fr", register=lambda p: "file")
    assert result["qualityPreserved"] and result["sourceCodecs"] == {"video": "h264", "audio": "opus"}
    assert len(commands) == 1 and result["outputFormat"] == "mp4"
    assert packet_hashes(source, "v:0") == packet_hashes(result["path"], "v:0")
    assert packet_hashes(source, "a:0") == packet_hashes(result["path"], "a:0")


@pytest.mark.integration
def test_original_download_without_captions_does_not_mux_again(media_site, tmp_path, monkeypatch):
    _, base = media_site
    monkeypatch.setattr(downloader, "remux_original", lambda *a, **k: pytest.fail("Original source must not be muxed twice"))
    result = downloader.download(context(), url=base + "/index.html", output_directory=str(tmp_path),
        output_format="original", register=lambda p: "file")
    assert result["qualityPreserved"] and not result["converted"] and result["subtitleTrack"] is None
