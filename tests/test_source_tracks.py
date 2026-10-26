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
from mediaforge.jobs import JobCancelled


def context():
    manager = JobManager()
    job = Job(id="source-track-test", kind="download")
    manager._jobs[job.id] = job
    return JobContext(manager, job.id)


def test_youtube_translation_ages_the_same_session_with_countdown():
    ctx=context();now=[0.];messages=[]
    original_update=ctx.update
    def update(progress=None,message=None):
        messages.append(message);original_update(progress,message)
    ctx.update=update
    downloader.wait_for_youtube_translation(ctx,{'extractor_key':'Youtube'},{'translated':True},
        clock=lambda:now[0],sleep=lambda seconds:now.__setitem__(0,now[0]+seconds))
    assert now[0]>=60 and now[0]<=70
    assert '65 s remaining' in messages[0] and '1 s remaining' in messages[-2]
    assert messages[-1]=='Downloading the selected subtitles'


@pytest.mark.parametrize('provider,track', [('Youtube',None),('Youtube',{'translated':False}),
    ('Facebook',{'translated':True}),('Generic',{'translated':True})])
def test_native_captions_and_other_sites_do_not_wait(provider,track):
    downloader.wait_for_youtube_translation(context(),{'extractor_key':provider},track,
        sleep=lambda seconds:pytest.fail('This caption does not need a session-age delay'))


def test_translation_countdown_cancels_promptly_without_starting_media_download():
    ctx=context();now=[0.]
    def sleep(seconds):
        now[0]+=seconds
        ctx.manager.cancel(ctx.job_id)
    with pytest.raises(JobCancelled):
        downloader.wait_for_youtube_translation(ctx,{'extractor_key':'Youtube'},{'translated':True},
            clock=lambda:now[0],sleep=sleep)
    assert now[0]==1


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


@pytest.mark.parametrize("field,value", [("subtitleMode", "unknown"), ("subtitleMode", []), ("burnSize", "4k"), ("burnSize", {})])
def test_invalid_caption_rendering_is_rejected_before_start(monkeypatch, tmp_path, field, value):
    monkeypatch.setattr(web.jobs, "start", lambda *a, **k: pytest.fail("Invalid rendering started a job"))
    response = web.create_app().test_client().post("/api/downloads", json={
        "url": "https://example.test/video", "outputDirectory": str(tmp_path), "outputFormat": "mp4",
        "subtitleLanguage": "ar", field: value})
    assert response.status_code == 400


@pytest.mark.integration
def test_route_reuses_only_a_registered_video_and_keeps_its_audio(media_site, tmp_path, monkeypatch):
    root, base = media_site
    client = web.create_app().test_client()
    asset = client.post('/api/assets/register', json={'assets':[{'id':'existing','path':str(root/'source.mp4')}]}).json['assets'][0]
    captured=[]
    monkeypatch.setattr(web.jobs,'start',lambda *a,**k:(captured.append(k) or Job(id='test',kind='download')))
    data={'url':base+'/index.html','outputDirectory':str(tmp_path),'outputFormat':'mp4',
          'subtitleLanguage':'fr','subtitleMode':'burn','burnAcknowledged':True,'burnSize':'source','sourceToken':asset['token']}
    assert client.post('/api/downloads',json=data).status_code==202
    assert captured[-1]['existing_media_path']==str(root/'source.mp4')
    assert captured[-1]['subtitle_mode']=='burn' and captured[-1]['burn_size']=='source'
    for invalid in ({'sourceToken':'unknown'},{'audioFormatId':'dub'},{'subtitleLanguage':None}):
        assert client.post('/api/downloads',json=data|invalid).status_code==400
    assert len(captured)==1


@pytest.mark.parametrize('acknowledgement',[None,False,'true'])
def test_cached_burn_defaults_cannot_start_an_encode(monkeypatch,tmp_path,acknowledgement):
    monkeypatch.setattr(web.jobs,'start',lambda *a,**k:pytest.fail('Old cached burn default started work'))
    response=web.create_app().test_client().post('/api/downloads',json={
        'url':'https://example.test/video','outputDirectory':str(tmp_path),'outputFormat':'mp4',
        'subtitleLanguage':'ar','subtitleMode':'burn','burnAcknowledged':acknowledgement})
    assert response.status_code==400 and 're-encodes' in response.json['error']


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
@pytest.mark.parametrize("container,codec", [("mp4", "mov_text"), ("mkv", "subrip"), ("mov", "mov_text"), ("webm", "subrip"), ("original", "mov_text")])
def test_real_inspection_and_caption_download_in_every_video_container(media_site, tmp_path, container, codec):
    root, base = media_site
    info = downloader.inspect_url(base + "/index.html")
    assert {t["language"] for t in info["subtitleTracks"]} == {"en", "fr"}
    result = downloader.download(context(), url=base + "/index.html", output_directory=str(tmp_path),
        output_format=container, subtitle_language="fr", register=lambda p: "registered")
    assert result["subtitleTrack"]["language"] == "fr"
    assert result["media"]["subtitles"][0]["codec"] == codec
    assert result["qualityPreserved"] is True
    if container == "webm":
        assert Path(result["path"]).suffix == ".mkv" and result["containerFallback"]
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
@pytest.mark.parametrize("container", ["mp4", "mkv", "mov", "webm", "original"])
def test_burned_subtitles_are_video_pixels_not_a_switchable_track(media_site, tmp_path, container):
    root, base = media_site
    result = downloader.download(context(), url=base + "/index.html", output_directory=str(tmp_path),
        output_format=container, subtitle_language="fr", subtitle_mode="burn", register=lambda p: "file")
    assert result["subtitleRendering"] == "burn" and result["burnSize"] == "source"
    assert result["media"]["subtitles"] == []
    assert result["media"]["video"]["width"] == 160 and result["media"]["audio"]
    def pixels(path):
        return subprocess.check_output(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(path),
            "-frames:v", "1", "-vf", "crop=160:30:0:60,format=gray", "-f", "rawvideo", "pipe:1"])
    # White caption outlines/text change the decoded picture, even with subtitles disabled.
    original, burned = pixels(root / "source.mp4"), pixels(result["path"])
    assert sum(abs(a - b) for a, b in zip(original, burned)) / len(original) > 3


@pytest.mark.integration
def test_caption_only_repair_keeps_existing_audio_and_never_downloads_video(media_site, tmp_path, monkeypatch):
    root, base = media_site
    original = (root / "source.mp4").read_bytes()
    fixture_extractor(monkeypatch, {"id": "test", "title": "Reuse the existing video",
        "formats": [{"format_id": "source", "url": base + "/must-not-request-this-video.mp4", "vcodec": "h264", "acodec": "aac"}],
        "subtitles": {"fr": [{"url": base + "/fr.vtt", "ext": "vtt"}]}})
    result = downloader.download(context(), url=base + "/track-fixture", output_directory=str(tmp_path),
        output_format="mp4", subtitle_language="fr", subtitle_mode="burn", existing_media_path=str(root / "source.mp4"),
        register=lambda p: "file")
    assert result["subtitleRendering"] == "burn" and result["media"]["subtitles"] == []
    assert (root / "source.mp4").read_bytes() == original
    def audio(path):
        return subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "adts", "pipe:1"])
    assert audio(result["path"]) == audio(root / "source.mp4")


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


@pytest.mark.integration
def test_actual_download_uses_original_caption_source_instead_of_last_dub(media_site, tmp_path, monkeypatch):
    root, base=media_site
    for name,text in [('ar-en','FROM_ENGLISH'),('ar-uk','FROM_UKRAINIAN')]:
        (root/f'{name}.vtt').write_text(f'WEBVTT\n\n00:00.000 --> 00:01.100\n{text}\n',encoding='utf-8')
    fixture_extractor(monkeypatch,{'id':'test','title':'Caption origin check','formats':[
        {'format_id':'source','url':base+'/source.mp4','vcodec':'h264','acodec':'aac','language':'en-US','format_note':'English original (default)'}],
        'automatic_captions':{'ar':[{'url':base+'/ar-en.vtt?lang=en&tlang=ar','ext':'vtt','name':'Arabic'},
                                  {'url':base+'/ar-uk.vtt?lang=uk&tlang=ar','ext':'vtt','name':'Arabic'}]}})
    result=downloader.download(context(),url=base+'/track-fixture',output_directory=str(tmp_path),output_format='mp4',
        subtitle_language='ar',subtitle_source='automatic',register=lambda p:'file')
    text=subprocess.check_output(['ffmpeg','-v','error','-i',result['path'],'-map','0:s:0','-f','srt','pipe:1']).decode('utf-8')
    assert 'FROM_ENGLISH' in text and 'FROM_UKRAINIAN' not in text
    assert result['subtitleTrack']['sourceLanguage']=='en'
