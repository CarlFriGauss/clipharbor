import threading

from mediaforge import web
from mediaforge.jobs import JobManager
from mediaforge.runtime import data_root


def desktop_app(monkeypatch):
    app = web.create_app()
    app.config.update(TESTING=True, DESKTOP_PORT=12345, DESKTOP_TOKEN="test-token", SHUTDOWN_CALLBACK=lambda: None)
    monkeypatch.setattr(web, "jobs", JobManager())
    return app


def test_desktop_requires_local_authenticated_session(monkeypatch):
    app = desktop_app(monkeypatch)
    client = app.test_client()
    base = "http://127.0.0.1:12345"
    assert client.get("/api/projects", base_url=base).status_code == 401
    assert client.get("/launch/wrong", base_url=base).status_code == 403
    assert client.get("/launch/test-token", base_url=base).status_code == 302
    assert client.get("/", base_url=base).status_code == 200
    assert client.post("/api/desktop/quit", base_url=base, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/", base_url="http://evil.example:12345").status_code == 403


def test_quit_refuses_active_work(monkeypatch):
    app = desktop_app(monkeypatch)
    done = threading.Event()
    web.jobs.start("test", lambda context: done.wait(5) or {})
    client = app.test_client()
    base = "http://127.0.0.1:12345"
    client.get("/launch/test-token", base_url=base)
    try:
        assert client.post("/api/desktop/quit", base_url=base).status_code == 409
    finally:
        done.set()


def test_per_user_storage_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPHARBOR_DATA_DIR", str(tmp_path))
    assert data_root() == tmp_path
