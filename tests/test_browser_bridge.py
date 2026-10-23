import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from mediaforge import browser_bridge as bridge, web
from mediaforge.jobs import JobManager

ROOT = Path(__file__).resolve().parent.parent


def test_extension_identity_and_permissions_match_native_host():
    manifest = json.loads((ROOT / "browser-extension/manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    assert "".join(chr(97 + int(char, 16)) for char in digest) == bridge.EXTENSION_ID
    native = json.loads((ROOT / "browser-extension/native-host.json").read_text())
    assert native["name"] == bridge.HOST_NAME
    assert native["allowed_origins"] == [bridge.EXTENSION_ORIGIN]
    assert native["path"] == "ClipHarborBridge.exe"
    assert "host_permissions" not in manifest
    assert "content_scripts" not in manifest
    assert not {"cookies", "history", "tabs", "webRequest", "clipboardRead"}.intersection(manifest["permissions"])
    assert manifest["version"] == bridge.VERSION


def test_native_protocol_roundtrip_and_partial_reads():
    value = {"protocol": 1, "action": "download", "url": "https://example.com/فيديو"}
    stream = io.BytesIO()
    bridge.write_message(stream, value)
    class ShortReader(io.BytesIO):
        def read(self, length=-1):
            return super().read(min(length, 7) if self.tell() >= 4 else length)
    assert bridge.read_message(ShortReader(stream.getvalue())) == value
    assert bridge.read_message(io.BytesIO()) is None
    for malformed in [b"x", struct.pack("=I", bridge.MAX_MESSAGE + 1), struct.pack("=I", 20) + b"{}", struct.pack("=I", 1) + b"!"]:
        with pytest.raises(bridge.BridgeError):
            bridge.read_message(io.BytesIO(malformed))


def test_unknown_origin_cannot_start_engine(tmp_path):
    import os
    result = subprocess.run([sys.executable, str(ROOT / "browser_bridge.py"), "chrome-extension://other/"],
        env=dict(os.environ, CLIPHARBOR_DATA_DIR=str(tmp_path)), input=b"", capture_output=True, timeout=10)
    assert result.returncode == 1 and not result.stdout
    assert not (tmp_path / "instance.json").exists()


@pytest.mark.parametrize("url", ["file:///private.mp4", "javascript:alert(1)", "blob:https://example.com/x", "https://user:password@example.com/x", "https://example.com:invalid/video", "https://example.com/\nvideo", None])
def test_invalid_source_is_rejected_before_startup(monkeypatch, url):
    monkeypatch.setattr(bridge, "ensure_desktop", lambda: pytest.fail("Invalid requests must not start the app"))
    with pytest.raises(bridge.BridgeError):
        bridge.handle({"protocol": 1, "action": "download", "url": url, "destination": "local", "outputFormat": "mp4"})


def test_bridge_submits_only_supported_download_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "data_root", lambda: tmp_path)
    monkeypatch.setattr(bridge, "downloads_directory", lambda: tmp_path / "safe-output")
    calls = []
    class Client:
        def api(self, path, payload=None, **kwargs):
            calls.append((path, payload))
            return {"id": "a" * 32, "status": "queued", "progress": 0, "log": ["internal"], "result": None}
    monkeypatch.setattr(bridge, "ensure_desktop", lambda: (Client(), {"version": bridge.VERSION}))
    response = bridge.handle({"protocol": 1, "action": "download", "url": "https://example.com/video",
        "destination": "drive", "outputFormat": "mp3", "xCompatible": True,
        "cookieFile": "private-cookies.txt", "outputDirectory": "untrusted-override", "deliveryOptions": {"folderId": "override"}})
    path, payload = calls[0]
    assert path == "/api/downloads" and payload["destination"] == "drive"
    assert payload["outputDirectory"] == str(tmp_path / "safe-output")
    assert payload["deliveryOptions"] == {} and payload["xCompatible"] is False
    assert "cookieFile" not in payload and "log" not in response["job"]
    assert bridge.settings()["destination"] == "drive"


def test_public_job_omits_local_session_and_media_tokens():
    result = bridge.public_job({"id": "a" * 32, "status": "completed", "log": ["private"], "result": {
        "token": "media-secret", "cloudDownloadId": "cloud", "path": "/temporary/private.mp4",
        "media": {"name": "video.mp4"}, "delivery": {"provider": "drive", "url": "https://drive.google.com/file/d/test/view"}}})
    assert result["path"] is None and result["name"] == "video.mp4" and result["driveUrl"]
    assert "media-secret" not in json.dumps(result) and "private" not in json.dumps(result)


def test_activity_discovers_background_jobs_and_stays_authenticated(monkeypatch):
    manager = JobManager()
    monkeypatch.setattr(web, "jobs", manager)
    app = web.create_app()
    app.config.update(TESTING=True, DESKTOP_TOKEN="test-token", DESKTOP_PORT=12345)
    client = app.test_client()
    base = "http://127.0.0.1:12345"
    assert client.get("/api/jobs", base_url=base).status_code == 401
    assert client.get("/launch/test-token?view=https://evil.example", base_url=base).location == "/"
    assert client.get("/launch/test-token?view=activity", base_url=base).location == "/#activity"
    job = manager.start("download", lambda context: {"path": "download.mp4"})
    response = client.get("/api/jobs", base_url=base)
    assert response.json["jobs"][0]["id"] == job.id
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/api/jobs", base_url=base, headers={"Origin": bridge.EXTENSION_ORIGIN}).status_code == 403
    assert client.get("/api/jobs", base_url="http://evil.example:12345").status_code == 403


def test_host_uses_only_valid_local_sessions():
    for record in [{"port": "https://evil.example", "token": "x" * 32}, {"port": 0, "token": "x" * 32},
                   {"port": 8765, "token": "x\r\nInjected: value"}]:
        with pytest.raises(bridge.BridgeError):
            bridge.DesktopClient(record)


def test_damaged_preferences_fall_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "data_root", lambda: tmp_path)
    for value in ([], {"destination": [], "outputFormat": {}, "outputDirectory": "bad\npath"}, "bad-json"):
        (tmp_path / "browser-downloads.json").write_text(json.dumps(value), encoding="utf-8")
        assert bridge.settings()["destination"] == "local"
        assert bridge.settings()["outputFormat"] == "mp4"


def test_source_lock_prevents_duplicate_engines(tmp_path):
    from mediaforge.desktop import InstanceLock
    first, second = InstanceLock(tmp_path / "lock"), InstanceLock(tmp_path / "lock")
    try:
        assert first.acquire()
        assert not second.acquire()
    finally:
        first.close()
        second.close()
