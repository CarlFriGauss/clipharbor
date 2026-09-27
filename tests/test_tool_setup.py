import hashlib
import io
import threading
import zipfile

import pytest

from mediaforge import tool_setup as setup


def archive():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        output.writestr("release/bin/ffmpeg.exe", b"test-tool")
        output.writestr("release/LICENSE.txt", b"license")
    return stream.getvalue()


def prepare(monkeypatch, tmp_path):
    data = archive()
    monkeypatch.setenv("CLIPHARBOR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(setup, "FILES", {"ffmpeg.exe": hashlib.sha256(b"test-tool").hexdigest()})
    monkeypatch.setattr(setup, "SHA256", hashlib.sha256(data).hexdigest())
    def response(*args, **kwargs):
        stream = io.BytesIO(data)
        stream.headers = {"Content-Length": str(len(data))}
        return stream
    monkeypatch.setattr(setup, "urlopen", response)


def test_verified_install_reused_and_corruption_detected(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)
    setup.ensure_media_tools(graphical=False)
    assert setup.ready()
    monkeypatch.setattr(setup, "urlopen", lambda *a, **k: pytest.fail("Downloaded again"))
    setup.ensure_media_tools(graphical=False)
    (setup.tool_directory() / "ffmpeg.exe").write_bytes(b"corrupt")
    assert not setup.ready()


def test_bad_hash_never_installs(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(setup, "SHA256", "wrong")
    with pytest.raises(RuntimeError, match="verification"):
        setup.install(lambda _: None, threading.Event())
    assert not setup.ready()


def test_cancel_never_installs(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(InterruptedError):
        setup.install(lambda _: None, cancelled)
    assert not setup.ready()
