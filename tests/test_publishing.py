from __future__ import annotations

import io
import json
import threading
from pathlib import Path
from urllib.error import HTTPError

import pytest

from mediaforge import publishing as p
from mediaforge.jobs import JobManager, JobContext


@pytest.fixture
def store(tmp_path, monkeypatch):
    store = p.Connections(tmp_path / "connections" / "accounts.dat")
    monkeypatch.setattr(p, "connections", store)
    return store


class Progress:
    def __init__(self):
        self.events = []
    def update(self, progress=None, message=None):
        self.events.append((progress, message))


def test_credentials_round_trip_are_private_and_disconnect_removes_them(store):
    store.put("drive", {"access_token": "secret-value", "folder_id": "saved-folder"})
    assert store.get("drive")["access_token"] == "secret-value"
    status = store.status()
    assert status["drive"]["connected"]
    assert "secret-value" not in json.dumps(status)
    if p.os.name == "nt":
        assert b"secret-value" not in store.path.read_bytes()
    store.put("drive", None)
    assert not store.status()["drive"]["connected"]


def test_google_refresh_preserves_folder_and_refresh_token(store, monkeypatch):
    store.put("drive", {"client_id": "id", "client_secret": "secret", "refresh_token": "refresh",
                        "access_token": "old", "expires_at": 0, "folder_id": "saved"})
    monkeypatch.setattr(p, "_form", lambda *args: {"access_token": "new", "expires_in": 3600})
    assert p.access_token("drive") == "new"
    assert store.get("drive")["folder_id"] == "saved"
    assert store.get("drive")["refresh_token"] == "refresh"


def test_drive_reuses_dedicated_folder(store, monkeypatch):
    store.put("drive", {"access_token": "token"})
    requests = []
    def request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        if method == "GET" and "/files?" in url:
            return {"files": []}
        if method == "POST":
            return {"id": "dedicated", "name": "ClipHarbor Exports"}
        return {"id": "dedicated", "name": "ClipHarbor Exports", "mimeType": "application/vnd.google-apps.folder"}
    monkeypatch.setattr(p, "_request", request)
    assert p.drive_folder("token") == "dedicated"
    assert p.drive_folder("token") == "dedicated"
    assert sum(method == "POST" for method, _, _ in requests) == 1
    assert store.status()["drive"]["folderId"] == "dedicated"


def test_drive_rejects_deleted_folder(store, monkeypatch):
    store.put("drive", {"access_token": "token", "folder_id": "deleted"})
    monkeypatch.setattr(p, "_request", lambda *a, **k: {"id": "deleted", "trashed": True})
    with pytest.raises(p.PublishError, match="unavailable"):
        p.drive_folder("token")


def test_google_upload_resumes_from_acknowledged_bytes(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"abcdefghij")
    monkeypatch.setattr(p, "CHUNK", 4)
    monkeypatch.setattr(p.time, "sleep", lambda _: None)
    calls = []
    failed = False
    def request(method, url, **kwargs):
        nonlocal failed
        if method == "POST":
            return 200, {"Location": "https://www.googleapis.com/upload/session"}, b""
        content_range = kwargs["headers"]["Content-Range"]
        calls.append((content_range, kwargs["data"]))
        if content_range == "bytes 0-3/10":
            return 308, {"Range": "bytes=0-3"}, b""
        if content_range == "bytes 4-7/10" and not failed:
            failed = True
            raise p.PublishError("Network interruption after bytes were accepted")
        if content_range == "bytes */10":
            return 308, {"Range": "bytes=0-7"}, b""
        assert content_range == "bytes 8-9/10"
        return 200, {}, b'{"id":"complete"}'
    monkeypatch.setattr(p, "_request", request)
    result = p._google_upload(Progress(), path, "drive", {"name": "sample.mp4"}, "token")
    assert result["id"] == "complete"
    assert calls == [("bytes 0-3/10", b"abcd"), ("bytes 4-7/10", b"efgh"),
                     ("bytes */10", b""), ("bytes 8-9/10", b"ij")]


def test_google_rejects_foreign_upload_session(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")
    monkeypatch.setattr(p, "_request", lambda *a, **k: (200, {"Location": "https://example.com/steal"}, b""))
    with pytest.raises(p.PublishError, match="valid upload session"):
        p._google_upload(Progress(), path, "drive", {}, "secret")


def test_drive_verifies_remote_size_and_parent(store, tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")
    store.put("drive", {"access_token": "token"})
    monkeypatch.setattr(p, "drive_folder", lambda *a: "dedicated")
    monkeypatch.setattr(p, "_google_upload", lambda *a: {"id": "uploaded"})
    monkeypatch.setattr(p, "_request", lambda *a, **k: {"id": "uploaded", "size": "4", "parents": ["wrong"]})
    with pytest.raises(p.PublishError, match="verify"):
        p.upload(Progress(), result={"path": str(path)}, provider="drive")


def test_x_waits_for_processing_before_creating_post(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"abcdefghij")
    monkeypatch.setattr(p, "CHUNK", 4)
    monkeypatch.setattr(p.time, "sleep", lambda _: None)
    calls = []
    def request(method, url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/initialize"):
            return {"data": {"id": "media"}}
        if url.endswith("/append"):
            assert len(kwargs["data"]) < 1024
            return {}
        if url.endswith("/finalize"):
            return {"data": {"processing_info": {"state": "pending"}}}
        if "command=STATUS" in url:
            return {"data": {"processing_info": {"state": "succeeded"}}}
        assert url.endswith("/tweets")
        assert kwargs["data"]["media"] == {"media_ids": ["media"]}
        return {"data": {"id": "post"}}
    monkeypatch.setattr(p, "_request", request)
    result = p._x_upload(Progress(), path, "token", "A caption")
    assert result["url"] == "https://x.com/i/status/post"
    assert sum(url.endswith("/append") for url, _ in calls) == 3
    assert "command=STATUS" in calls[-2][0]


def test_x_processing_failure_never_posts(tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"video")
    calls = []
    def request(method, url, **kwargs):
        calls.append(url)
        if url.endswith("/initialize"):
            return {"data": {"id": "media"}}
        if url.endswith("/finalize"):
            return {"data": {"processing_info": {"state": "failed"}}}
        return {}
    monkeypatch.setattr(p, "_request", request)
    with pytest.raises(p.PublishError, match="process"):
        p._x_upload(Progress(), path, "token", "Caption")
    assert not any(url.endswith("/tweets") for url in calls)


def test_facebook_streams_file_and_defaults_to_unpublished(store, tmp_path, monkeypatch):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"abcdefghij")
    store.put("facebook", {"access_token": "token", "page_id": "123"})
    monkeypatch.setattr(p, "CHUNK", 4)
    def request(method, url, **kwargs):
        assert url == "https://graph-video.facebook.com/v26.0/123/videos"
        assert not isinstance(kwargs["data"], bytes)
        chunks = list(kwargs["data"])
        assert max(map(len, chunks[1:-1])) == 4
        assert b'name="published"\r\n\r\nfalse' in chunks[0]
        assert sum(map(len, chunks)) == int(kwargs["headers"]["Content-Length"])
        assert b"".join(chunks[1:-1]) == b"abcdefghij"
        return {"id": "video"}
    monkeypatch.setattr(p, "_request", request)
    result = p._facebook_upload(Progress(), path, "token", {})
    assert result["visibility"] == "unpublished"


@pytest.mark.parametrize("browser_result", [True, False, OSError("No browser")])
def test_facebook_browser_prepares_existing_file_without_credentials_or_upload(tmp_path, monkeypatch, browser_result):
    path = tmp_path / "profile.mp4"
    path.write_bytes(b"original-video")
    local = {"path": str(path), "token": "registered", "media": {"video": True}}
    opened = []
    def open_browser(url):
        opened.append(url)
        if isinstance(browser_result, Exception):
            raise browser_result
        return browser_result
    def forbidden(*args, **kwargs):
        pytest.fail("Profile sharing must not request a token or upload to an API")
    monkeypatch.setattr(p.webbrowser, "open", open_browser)
    monkeypatch.setattr(p, "access_token", forbidden)
    monkeypatch.setattr(p, "_request", forbidden)
    monkeypatch.setattr(p.connections, "status", forbidden)
    result = p.upload(Progress(), result=local, provider="facebook_browser", options={"description": "My caption", "publish": True})
    assert result["path"] == str(path)
    assert path.read_bytes() == b"original-video"
    assert "delivery" not in result
    assert result["handoff"] == {"provider": "facebook_browser", "url": "https://www.facebook.com/",
                                "target": "profile", "caption": "My caption", "browserOpened": browser_result is True}
    assert opened == ["https://www.facebook.com/"]


def test_facebook_browser_rejects_audio_and_non_mp4_before_opening_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(p.webbrowser, "open", lambda *a: pytest.fail("Invalid media must not open Facebook"))
    with pytest.raises(ValueError, match="MP4"):
        p.validate_destination("facebook_browser", "mp3")
    with pytest.raises(ValueError, match="personal profile or Page"):
        p.validate_destination("facebook_browser", "mp4", {"facebookTarget": "somebody-else"})
    path = tmp_path / "audio.mp4"
    path.touch()
    with pytest.raises(ValueError, match="video"):
        p.upload(Progress(), result={"path": str(path), "media": {}}, provider="facebook_browser")


def test_facebook_browser_render_handoff_uses_finished_render(monkeypatch):
    from mediaforge import editor
    local = {"path": "finished.mp4", "token": "registered", "media": {"video": True}}
    monkeypatch.setattr(editor, "render", lambda *a, **k: local)
    monkeypatch.setattr(p.webbrowser, "open", lambda *a: True)
    result = p.render_and_publish(Progress(), provider="facebook_browser", delivery_options={"description": "Edited video", "facebookTarget": "page"})
    assert result["path"] == "finished.mp4"
    assert result["handoff"]["caption"] == "Edited video"
    assert result["handoff"]["target"] == "page"
    assert "delivery" not in result


def test_facebook_browser_route_does_not_require_a_page_connection(tmp_path, monkeypatch):
    from mediaforge import web
    from mediaforge.jobs import Job
    client = web.create_app().test_client()
    path = tmp_path / "video.mp4"
    path.touch()
    monkeypatch.setattr(web.registry, "get", lambda *a: path)
    monkeypatch.setattr(web.registry, "add", lambda *a: "registered")
    monkeypatch.setattr(web, "probe", lambda *a: {"video": True})
    calls = []
    def start(kind, target, **kwargs):
        calls.append((kind, kwargs))
        return Job(id="share", kind=kind)
    monkeypatch.setattr(web.jobs, "start", start)
    response = client.post("/api/uploads", json={"token": "registered", "destination": "facebook_browser"})
    assert response.status_code == 202
    assert calls[0][0] == "share"
    assert calls[0][1]["provider"] == "facebook_browser"
    response = client.post("/api/renders", json={"destination": "facebook_browser", "project": {"clips": []}})
    assert response.status_code == 400
    assert "visible video" in response.json["error"]


def test_failed_delivery_preserves_local_result_for_retry(store, monkeypatch):
    from mediaforge import editor
    manager = JobManager()
    from mediaforge.jobs import Job
    job = Job(id="test", kind="render")
    manager._jobs[job.id] = job
    local = {"path": "retained.mp4", "token": "registered", "media": {"video": True}}
    monkeypatch.setattr(editor, "render", lambda *a, **k: local)
    def fail(*a, **k):
        raise p.PublishError("Upload failed")
    monkeypatch.setattr(p, "upload", fail)
    with pytest.raises(p.PublishError, match="retained.mp4"):
        p.render_and_publish(JobContext(manager, job.id), provider="drive")
    assert job.result == local


def test_http_errors_never_expose_credentials(monkeypatch):
    def fail(*a, **k):
        raise HTTPError("https://example.com/?secret=token", 403, "denied", {}, io.BytesIO(b'{"error":"secret"}'))
    monkeypatch.setattr(p.urllib.request, "urlopen", fail)
    with pytest.raises(p.PublishError) as error:
        p._request("POST", "https://example.com/", token="secret", data={})
    assert "secret" not in str(error.value)
    assert "403" in str(error.value)


def test_routes_block_cross_origin_and_preflight_before_render(store, monkeypatch):
    from mediaforge.web import create_app
    client = create_app().test_client()
    response = client.post("/api/connections/x", json={"token": "secret"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.post("/api/connections/x", data="token=secret").status_code == 415
    response = client.post("/api/renders", json={"destination": "drive", "project": {}})
    assert response.status_code == 400
    assert "Connect" in response.json["error"]
    assert client.get("/api/connections").headers["Cache-Control"] == "no-store"
    assert client.post("/api/uploads", json={"token": "missing", "destination": "drive"}).status_code == 404


def test_social_export_validation_requires_video_format_and_explicit_x_publish(store):
    store.put("x", {"access_token": "token"})
    with pytest.raises(ValueError, match="MP4"):
        p.validate_destination("x", "mp3", {"publish": True})
    with pytest.raises(ValueError, match="Publish"):
        p.validate_destination("x", "mp4", {})
    with pytest.raises(ValueError, match="280"):
        p.validate_destination("x", "mp4", {"publish": True, "description": "x" * 281})


@pytest.mark.parametrize("provider,folder_id,expected_scope,remembered", [
    ("drive", "", "https://www.googleapis.com/auth/drive.file", False),
    ("drive", "chosen-folder", "https://www.googleapis.com/auth/drive", False),
    ("drive", "remembered-app-folder", "https://www.googleapis.com/auth/drive.file", True),
    ("youtube", "", "https://www.googleapis.com/auth/youtube.upload", False),
])
def test_google_oauth_state_pkce_and_folder_consent(store, monkeypatch, provider, folder_id, expected_scope, remembered):
    from urllib.parse import parse_qs, urlsplit, urlencode
    from urllib.request import urlopen
    callbacks = []
    if remembered:
        store.put(provider, {"client_id": "id", "folder_id": folder_id, "existing_folder_access": False})
    def open_browser(url):
        params = parse_qs(urlsplit(url).query)
        assert params["scope"] == [expected_scope]
        assert params["code_challenge_method"] == ["S256"]
        redirect = params["redirect_uri"][0]
        assert urlsplit(redirect).hostname == "127.0.0.1"
        def callback():
            # An unrelated site cannot complete this sign-in with a guessed state.
            try:
                urlopen(redirect + "?state=wrong&code=stolen", timeout=5)
            except HTTPError as error:
                assert error.code == 400
            response = urlopen(redirect + "?" + urlencode({"state": params["state"][0], "code": "verified"}), timeout=5)
            assert response.status == 200
        thread = threading.Thread(target=callback)
        callbacks.append(thread)
        thread.start()
        return True
    def exchange(method, url, values):
        assert values["code"] == "verified"
        assert len(values["code_verifier"]) >= 43
        return {"access_token": "new-token", "refresh_token": "refresh", "expires_in": 3600}
    monkeypatch.setattr(p.webbrowser, "open", open_browser)
    monkeypatch.setattr(p, "_form", exchange)
    p.authorize_google(Progress(), provider=provider, folder_id=folder_id,
                       credentials={"installed": {"client_id": "id", "client_secret": "secret"}})
    for thread in callbacks:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert store.get(provider)["folder_id"] == folder_id
    assert store.status()[provider]["connected"]
