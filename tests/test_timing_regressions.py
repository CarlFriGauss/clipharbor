from pathlib import Path
import os
import subprocess

import pytest

from mediaforge.editor import build_render_command
from mediaforge.ffmpeg import probe
from mediaforge.waveform import extract_waveform
from mediaforge.playback import editing_source


def make_audio(path, expression, duration=3, rate=48000):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='{expression}':s={rate}:d={duration}", "-y", str(path)],
                   check=True, capture_output=True, timeout=60)


@pytest.mark.integration
def test_detail_waveform_preserves_100ms_pause_and_stereo(tmp_path: Path):
    source = tmp_path / "opposite-phase.wav"
    signal = "0.4*sin(2*PI*6000*t)*not(between(t,1.1,1.2))"
    make_audio(source, f"{signal}|-({signal})")
    wave = extract_waveform(source, 2400, start=1, duration=.5)
    assert wave["start"] == 1
    assert wave["binDuration"] <= .001
    assert wave["peak"] > .3  # Mono downmix would cancel this source entirely.
    quiet = [v for i, v in enumerate(wave["samples"]) if 1.12 < 1+i*wave["binDuration"] < 1.18]
    assert quiet and max(quiet) < .001
    assert max(wave["samples"][:100]) > .9


@pytest.mark.integration
@pytest.mark.parametrize("speed", [.75, 1, 1.25, 2])
def test_audio_cut_export_duration_after_speed_and_gap(tmp_path: Path, speed):
    source = tmp_path / "source.wav"
    make_audio(source, "0.1*sin(2*PI*440*t)", rate=44100)
    end = .4 + (2.731 - .137) / speed
    project = {"assets": [{"id": "a", "path": str(source), "audio": True}], "clips": [
        {"assetId": "a", "kind": "audio", "in": .137, "out": 2.731,
         "start": .4, "speed": speed, "volume": 1, "layer": 0}
    ]}
    output = tmp_path / "cut.mp3"
    subprocess.run(build_render_command(project, output, "mp3"), check=True, capture_output=True, timeout=60)
    assert abs(probe(output)["duration"] - end) < .08


@pytest.mark.integration
def test_hour_long_mp3_cut_does_not_accumulate_seconds(tmp_path: Path):
    source = tmp_path / "long.mp3"
    make_audio(source, "0.1*sin(2*PI*440*t)", duration=3990, rate=8000)
    project = {"assets": [{"id": "a", "path": str(source), "audio": True}], "clips": [
        {"assetId": "a", "kind": "audio", "in": 0, "out": 3988.123,
         "start": 0, "speed": 1, "volume": 1, "layer": 0}
    ]}
    output = tmp_path / "hour-cut.mp3"
    subprocess.run(build_render_command(project, output, "mp3"), check=True, capture_output=True, timeout=180)
    assert abs(probe(output)["duration"] - 3988.123) < .08


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("MEDIAFORGE_TEST_AUDIO"), reason="Optional local recording check")
def test_real_recording_hour_export(tmp_path: Path):
    from mediaforge.editor import render
    source = Path(os.environ["MEDIAFORGE_TEST_AUDIO"])
    project = {"assets": [{"id": "a", "path": str(source), "audio": True}], "clips": [
        {"assetId": "a", "kind": "audio", "in": 0, "out": 3988.123,
         "start": 0, "speed": 1, "volume": 1, "layer": 0}
    ]}
    class Context:
        def update(self, *args):
            pass
        def write(self, line):
            pass
    result = render(Context(), project=project, output_directory=str(tmp_path), filename="timing-check",
                    output_format="mp3", save_project=False, register=lambda _: "test")
    print(f"Requested {result['timelineDuration']:.6f}s; MP3 {result['media']['duration']:.6f}s")
    assert abs(result["media"]["duration"] - 3988.123) < .08


def decode_pcm(path, start=None, duration=None, preroll=0):
    command = ["ffmpeg", "-v", "error"]
    if start is not None:
        preroll = min(start, preroll)
        command += ["-ss", str(start-preroll)]
    command += ["-i", str(path)]
    if preroll:
        command += ["-ss", str(preroll)]
    if duration is not None:
        command += ["-t", str(duration)]
    command += ["-map", "0:a:0", "-f", "f32le", "pipe:1"]
    return subprocess.run(command, check=True, capture_output=True, timeout=60).stdout


@pytest.mark.integration
def test_indexed_mp3_preserves_decoded_content_and_seek(tmp_path, monkeypatch):
    from mediaforge import playback
    import array
    monkeypatch.setattr(playback, "CACHE_ROOT", tmp_path / "index")
    source = tmp_path / "variable.mp3"
    make_audio(source, "0.2*sin(2*PI*(200*t+17*t*t))*not(between(t,4.1,4.2))", duration=8)
    original_bytes = source.read_bytes()
    indexed = editing_source(source)
    assert indexed != source and indexed.suffix == ".mp4"
    assert probe(indexed)["audio"]["codec"] == "mp3"  # No lossy AAC conversion.
    sequential = decode_pcm(source)
    copied = decode_pcm(indexed)
    # MP4 does not carry MP3's final discard-padding tag; content up to the
    # original decoded end must be unchanged, including encoder delay removal.
    assert copied[:len(sequential)] == sequential
    assert len(copied) - len(sequential) < 1152 * 4
    sought = array.array("f", decode_pcm(indexed, 4, .4, preroll=.25))
    expected = array.array("f", sequential[4*48000*4:])[:len(sought)]
    assert len(sought) == len(expected)
    assert max(abs(a-b) for a,b in zip(sought, expected)) < .00001
    wave = extract_waveform(source, 2000, start=4, duration=.4)
    silence = [v for i,v in enumerate(wave["samples"]) if 4.12 < 4+i*wave["binDuration"] < 4.18]
    assert silence and max(silence) < .001
    assert editing_source(source) == indexed  # Reused, not encoded again.
    assert source.read_bytes() == original_bytes


@pytest.mark.integration
def test_index_cache_refreshes_when_source_changes(tmp_path, monkeypatch):
    from mediaforge import playback
    monkeypatch.setattr(playback, "CACHE_ROOT", tmp_path / "index")
    source = tmp_path / "variable.mp3"
    make_audio(source, "0.2*sin(2*PI*300*t)", duration=.2)
    first = editing_source(source)
    make_audio(source, "0.2*sin(2*PI*700*t)", duration=.3)
    second = editing_source(source)
    assert first != second and first.is_file() and second.is_file()
    assert not list((tmp_path / "index").glob("*.partial"))
