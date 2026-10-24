"""Exercise source metadata, exact audio selection, and real captioned files."""
from __future__ import annotations

import copy
import functools
import http.server
import json
from pathlib import Path
import subprocess
import threading

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor

from mediaforge import downloader, web
from mediaforge.ffmpeg import embed_subtitle, probe
from mediaforge.jobs import Job, JobContext, JobManager


def context():
    manager = JobManager()
    job = Job(id="source-track-test", kind="download")
    manager._jobs[job.id] = job
    return JobContext(manager, job.id)


def test_caption_metadata_keeps_creator_and_auto_translations_without_urls():
    info = {"subtitles": {"en": [{"ext": "vtt", "name": "English", "url": "https://example.test/en.vtt"}]},
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "https://example.test/auto.vtt"}],
                "fr": [{"ext": "vtt", "name": "French", "url": "https://example.test/caption?tlang=fr&signature=private"}],
                "live_chat": [{"ext": "json", "url": "https://example.test/chat"}],
                "all": [{"ext": "vtt", "url": "https://example.test/all"}],
                "bad.*": [{"ext": "vtt", "url": "https://example.test/bad"}],
                "de": [{"ext": "json3", "url": "https://example.test/json"}],
                "es": []}}
    tracks = downloader.subtitle_tracks_from_info(info)
    assert {(t["language"], t["source"]) for t in tracks} == {("en", "manual"), ("en", "automatic"), ("fr", "automatic")}
    assert next(t for t in tracks if t["language"] == "fr")["translated"] is True
    assert "signature" not in json.dumps(tracks) and "https://" not in json.dumps(tracks)


def test_inspection_requests_youtube_translation_catalogue_without_downloading(monkeypatch):
    class Source:
        def __init__(self, options):
            assert options["skip_download"] is True and options["writeautomaticsub"] is True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert download is False
            return {"automatic_captions": {"fr-en": [{"ext": "vtt", "name": "French from English", "url": "https://example.test/subs?tlang=fr"}]}}
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", Source)
    info = downloader.inspect_url("https://www.youtube.com/watch?v=fixture")
    assert info["subtitleTracks"][0]["translated"] is True


@pytest.mark.parametrize("language,source,output", [(".*", "manual", "mp4"), ("all", "automatic", "mp4"),
    ("en", "manual", "mp3"), ("en", "other", "mp4"), ([], "manual", "mp4"), ("en", {}, "mp4")])
def test_bad_caption_selection_is_rejected_before_job_start(monkeypatch, tmp_path, language, source, output):
    monkeypatch.setattr(web.jobs, "start", lambda *a, **k: pytest.fail("Invalid selection started a job"))
    response = web.create_app().test_client().post("/api/downloads", json={
        "url": "https://example.test/video", "outputDirectory": str(tmp_path), "outputFormat": output,
        "subtitleLanguage": language, "subtitleSource": source})
    assert response.status_code == 400


def test_facebook_language_variants_are_separate_and_muxed_tracks_identified():
    tracks = downloader.audio_tracks_from_formats([
        {"format_id": "audio-en", "vcodec": "none", "acodec": "aac", "language": "en", "abr": 128},
        {"format_id": "audio-es", "vcodec": "none", "acodec": "aac", "language": "es", "abr": 128},
        {"format_id": "dub-fr", "vcodec": "h264", "acodec": "aac", "language": "fr"}])
    assert {t["language"] for t in tracks} == {"en", "es", "fr"}
    assert next(t for t in tracks if t["language"] == "fr")["hasVideo"] is True
    assert downloader.download_format_selector("mp4", "audio-es") == "bestvideo+audio-es"


def test_route_preserves_exact_caption_source_and_language(monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr(web.jobs, "start", lambda *args, **kwargs: (captured.append(kwargs) or Job(id="test", kind="download")))
    response = web.create_app().test_client().post("/api/downloads", json={
        "url": "https://example.test/video", "outputDirectory": str(tmp_path), "outputFormat": "mp4",
        "subtitleLanguage": "en-orig", "subtitleSource": "automatic", "audioFormatId": "140-2"})
    assert response.status_code == 202
    assert captured[0]["subtitle_language"] == "en-orig"
    assert captured[0]["subtitle_source"] == "automatic"
    assert captured[0]["audio_format_id"] == "140-2"


def test_removed_subtitle_stops_before_downloading_and_cleans_working_files(monkeypatch, tmp_path):
    class Source:
        def __init__(self, options):
            assert options["subtitleslangs"] == ["^en\\-orig$"]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert download is False
            return {"formats": []}
        def process_ie_result(self, *args, **kwargs): pytest.fail("Missing subtitles must stop before download")
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", Source)
    with pytest.raises(ValueError, match="no longer available"):
        downloader.download(context(), url="https://example.test/video", output_directory=str(tmp_path), output_format="mp4",
                            subtitle_language="en-orig", subtitle_source="automatic", register=lambda p: "file")
    assert list(tmp_path.iterdir()) == []


def test_subtitle_rate_limit_is_actionable_and_never_saves_a_captionless_video(monkeypatch, tmp_path):
    class Source:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            return {"subtitles": {"en": [{"ext": "vtt", "url": "https://example.test/en.vtt"}]}}
        def process_ie_result(self, *args, **kwargs):
            raise yt_dlp.utils.DownloadError("Unable to download video subtitles: HTTP Error 429")
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", Source)
    with pytest.raises(RuntimeError, match="rate-limiting subtitle downloads"):
        downloader.download(context(), url="https://example.test/video", output_directory=str(tmp_path), output_format="mp4",
                            subtitle_language="en", register=lambda p: "file")
    assert list(tmp_path.iterdir()) == []


@pytest.fixture(scope="module")
def media_site(tmp_path_factory):
    root = tmp_path_factory.mktemp("source-media")
    def ffmpeg(*args):
        subprocess.run(["ffmpeg", "-v", "error", *args], check=True, capture_output=True)
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=1.2", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2",
           "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-y", str(root / "source.mp4"))
    ffmpeg("-i", str(root / "source.mp4"), "-an", "-c:v", "copy", str(root / "video.mp4"))
    ffmpeg("-i", str(root / "source.mp4"), "-vn", "-c:a", "copy", str(root / "english.m4a"))
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=1.2", "-c:a", "aac", str(root / "spanish.m4a"))
    ffmpeg("-i", str(root / "video.mp4"), "-i", str(root / "spanish.m4a"), "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", str(root / "spanish.mp4"))
    for language, text in (("en", "Hello from ClipHarbor"), ("fr", "Bonjour de ClipHarbor")):
        (root / f"{language}.vtt").write_text(f"WEBVTT\n\n00:00.000 --> 00:01.100\n{text}\n", encoding="utf-8")
    (root / "auto.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:01.100\nAutomatic caption version\n", encoding="utf-8")
    (root / "index.html").write_text('''<html><head><title>Caption test</title></head><body><video controls src="source.mp4">
        <track kind="subtitles" srclang="en" label="English" src="en.vtt">
        <track kind="subtitles" srclang="fr" label="French" src="fr.vtt"></video></body></html>''', encoding="utf-8")
    (root / "audio.mpd").write_text('''<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT1.2S"><Period>
        <AdaptationSet mimeType="video/mp4"><Representation id="video" bandwidth="100000" codecs="avc1.64000a" width="160" height="90"><BaseURL>video.mp4</BaseURL></Representation></AdaptationSet>
        <AdaptationSet mimeType="audio/mp4" lang="en"><Representation id="audio-en" bandwidth="64000" codecs="mp4a.40.2"><BaseURL>english.m4a</BaseURL></Representation></AdaptationSet>
        <AdaptationSet mimeType="audio/mp4" lang="es"><Representation id="audio-es" bandwidth="64000" codecs="mp4a.40.2"><BaseURL>spanish.m4a</BaseURL></Representation></AdaptationSet>
        </Period></MPD>''', encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.integration
@pytest.mark.parametrize("container,codec", [("mp4", "mov_text"), ("mkv", "subrip"), ("mov", "mov_text"), ("webm", "webvtt"), ("original", "mov_text")])
def test_real_inspection_and_caption_download_in_every_video_container(media_site, tmp_path, container, codec):
    root, base = media_site
    info = downloader.inspect_url(base + "/index.html")
    assert {t["language"] for t in info["subtitleTracks"]} == {"en", "fr"}
    result = downloader.download(context(), url=base + "/index.html", output_directory=str(tmp_path),
        output_format=container, subtitle_language="fr", register=lambda p: "registered")
    assert result["subtitleTrack"]["language"] == "fr"
    assert result["media"]["subtitles"][0]["codec"] == codec
    text = subprocess.check_output(["ffmpeg", "-v", "error", "-i", result["path"], "-map", "0:s:0", "-f", "srt", "pipe:1"]).decode("utf-8")
    assert "Bonjour de ClipHarbor" in text and "Hello from ClipHarbor" not in text
    assert list(tmp_path.iterdir()) == [Path(result["path"])], "Do not leave intermediate files or caption sidecars"


@pytest.mark.integration
def test_none_download_has_no_added_subtitle_stream(media_site, tmp_path):
    root, base = media_site
    result = downloader.download(context(), url=base + "/index.html", output_directory=str(tmp_path), output_format="mp4", register=lambda p: "file")
    assert result["subtitleTrack"] is None and result["media"]["subtitles"] == []
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.integration
def test_exact_manifest_audio_language_is_downloaded(media_site, tmp_path):
    root, base = media_site
    info = downloader.inspect_url(base + "/audio.mpd")
    assert {t["language"] for t in info["audioTracks"]} == {"en", "es"}
    spanish = next(t for t in info["audioTracks"] if t["language"] == "es")
    result = downloader.download(context(), url=base + "/audio.mpd", output_directory=str(tmp_path), output_format="mp4",
        audio_format_id=spanish["formatId"], audio_track_label=spanish["label"], register=lambda p: "file")
    def hashes(path):
        return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_packets", "-show_data_hash", "sha256", "-of", "json", str(path)]))["packets"]
    assert [p["data_hash"] for p in hashes(result["path"])] == [p["data_hash"] for p in hashes(root / "spanish.m4a")]


@pytest.mark.integration
def test_caption_remux_does_not_reencode_video_or_audio(media_site, tmp_path):
    root, _ = media_site
    output = tmp_path / "captioned.mp4"
    embed_subtitle(root / "source.mp4", root / "en.vtt", output, language="en", title="English")
    def hashes(path, stream):
        data = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", stream, "-show_packets", "-show_data_hash", "sha256", "-of", "json", str(path)])
        return [p["data_hash"] for p in json.loads(data)["packets"]]
    assert hashes(root / "source.mp4", "v:0") == hashes(output, "v:0")
    assert hashes(root / "source.mp4", "a:0") == hashes(output, "a:0")


def fixture_extractor(monkeypatch, info):
    """Keep yt-dlp's real selection, downloads and postprocessors; fix metadata."""
    real_ydl = yt_dlp.YoutubeDL
    class TrackFixtureIE(InfoExtractor):
        _VALID_URL = r"http://127\.0\.0\.1:\d+/track-fixture"
        def _real_extract(self, url):
            return copy.deepcopy(info)
    class FixtureYoutubeDL(real_ydl):
        def __init__(self, options):
            super().__init__(options, auto_init=False)
            self.add_info_extractor(TrackFixtureIE())
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FixtureYoutubeDL)


@pytest.mark.integration
def test_facebook_muxed_dub_keeps_its_own_audio(media_site, tmp_path, monkeypatch):
    root, base = media_site
    fixture_extractor(monkeypatch, {"id": "test", "title": "Facebook shaped muxed tracks", "formats": [
        {"format_id": "original-en", "url": base + "/source.mp4", "vcodec": "h264", "acodec": "aac", "language": "en"},
        {"format_id": "dub-es", "url": base + "/spanish.mp4", "vcodec": "h264", "acodec": "aac", "language": "es"}]})
    result = downloader.download(context(), url=base + "/track-fixture", output_directory=str(tmp_path), output_format="mp4",
        audio_format_id="dub-es", register=lambda p: "file")
    audio = subprocess.check_output(["ffmpeg", "-v", "error", "-i", result["path"], "-map", "0:a:0", "-c", "copy", "-f", "adts", "pipe:1"])
    expected = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(root / "spanish.m4a"), "-c", "copy", "-f", "adts", "pipe:1"])
    assert audio == expected


@pytest.mark.integration
@pytest.mark.parametrize("language,expected", [("en", "Automatic caption version"), ("fr", "Bonjour de ClipHarbor")])
def test_auto_captions_and_translations_do_not_fall_back_to_creator_captions(media_site, tmp_path, monkeypatch, language, expected):
    root, base = media_site
    fixture_extractor(monkeypatch, {"id": "test", "title": "YouTube shaped caption tracks",
        "formats": [{"format_id": "source", "url": base + "/source.mp4", "vcodec": "h264", "acodec": "aac"}],
        "subtitles": {"en": [{"url": base + "/en.vtt", "ext": "vtt"}]},
        "automatic_captions": {"en": [{"url": base + "/auto.vtt", "ext": "vtt"}],
                               "fr": [{"url": base + "/fr.vtt?tlang=fr", "ext": "vtt"}]}})
    result = downloader.download(context(), url=base + "/track-fixture", output_directory=str(tmp_path), output_format="mp4",
        subtitle_language=language, subtitle_source="automatic", register=lambda p: "file")
    text = subprocess.check_output(["ffmpeg", "-v", "error", "-i", result["path"], "-map", "0:s:0", "-f", "srt", "pipe:1"]).decode("utf-8")
    assert expected in text and "Hello from ClipHarbor" not in text
    assert result["subtitleTrack"]["automatic"] is True


@pytest.mark.integration
def test_drive_staging_uploads_the_captioned_file_before_cleaning_it(media_site, tmp_path, monkeypatch):
    from mediaforge import cloud_downloads as cloud
    _, base = media_site
    observed = []
    monkeypatch.setattr(cloud, "data_root", lambda: tmp_path / "app-data")
    monkeypatch.setattr(cloud, "validate_destination", lambda *a, **k: None)
    def upload(context, *, result, provider, options):
        assert provider == "drive"
        assert probe(result["path"])["subtitles"][0]["codec"] == "mov_text"
        assert result["subtitleTrack"]["language"] == "fr"
        observed.append(Path(result["path"]))
        return {**result, "delivery": {"provider": "drive", "url": "https://drive.google.com/file/d/test/view"}}
    monkeypatch.setattr(cloud, "upload", upload)
    result = cloud.download_to_destination(context(), provider="drive", url=base + "/index.html",
        output_directory=str(tmp_path / "local"), output_format="mp4", subtitle_language="fr", register=lambda p: "file")
    assert result["subtitleTrack"]["language"] == "fr" and result["localAvailable"] is False
    assert not observed[0].exists() and list(cloud.staging_root().iterdir()) == []
