from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from mediaforge.jobs import Job, JobManager


def test_concurrent_repeated_exports_start_one_job():
    manager = JobManager()
    release = threading.Event()
    calls = []

    def deliver(context):
        calls.append(context.job_id)
        release.wait(3)
        return {"delivered": True}

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            jobs = list(pool.map(lambda _: manager.start_once("same-dialog", "share", deliver), range(24)))
        assert len({job.id for job in jobs}) == 1
        assert manager.start_once("same-dialog", "share", deliver) is jobs[0]
    finally:
        release.set()
    for _ in range(100):
        if jobs[0].status == "completed":
            break
        time.sleep(.01)
    assert calls == [jobs[0].id]
    assert manager.start_once("same-dialog", "share", deliver) is jobs[0]


def test_retry_stays_linked_after_completion_but_a_failed_child_can_be_retried():
    manager = JobManager()
    source = Job(id="a" * 32, kind="share", status="failed", result={"path": "test.mp4"})
    manager._jobs[source.id] = source
    def failed_attempt(context):
        raise ValueError("Before posting")
    child = manager.start_retry(source.id, "share", failed_attempt)
    assert manager.start_retry(source.id, "share", lambda context: pytest.fail("Repeated retry ran")) is child
    assert source.public()["retryJobId"] == child.id
    for _ in range(100):
        if child.status == "failed":
            break
        time.sleep(.01)
    assert child.status == "failed"
    grandchild = manager.start_retry(child.id, "share", lambda context: {})
    assert grandchild.id != child.id
    assert manager.start_retry(source.id, "share", lambda context: pytest.fail("Old parent ran again")) is child


@pytest.mark.parametrize("status,uncertain", [("completed", False), ("running", False), ("failed", True)])
def test_retry_rejects_completed_active_and_uncertain_posts(status, uncertain):
    manager = JobManager()
    source = Job(id="b" * 32, kind="share", status=status, result={"browserPostingUncertain": uncertain})
    manager._jobs[source.id] = source
    with pytest.raises(ValueError):
        manager.start_retry(source.id, "share", lambda context: pytest.fail("Unsafe retry ran"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    from mediaforge import web
    manager = JobManager()
    monkeypatch.setattr(web, "jobs", manager)
    monkeypatch.setattr(web, "registry", web.MediaRegistry())
    monkeypatch.setattr(web, "validate_destination", lambda *args: None)
    monkeypatch.setattr(web, "snapshot_destination", lambda provider, options: dict(options))
    monkeypatch.setattr(web, "probe", lambda path: {"video": True, "name": path.name})
    monkeypatch.setattr(web, "retry_upload", lambda context, **kwargs: kwargs["result"])
    path = tmp_path / "test.mp4"
    path.write_bytes(b"test")
    token = web.registry.add(path)
    return web.create_app().test_client(), manager, path, token


def test_upload_endpoint_returns_same_export_and_retry_jobs(client):
    http, manager, path, token = client
    payload = {"token": token, "destination": "facebook_browser", "deliveryOptions": {"audience": "only_me"}, "requestId": "c" * 32}
    first = http.post("/api/uploads", json=payload)
    second = http.post("/api/uploads", json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json["id"] == second.json["id"]
    source = Job(id="d" * 32, kind="share", status="failed", result={"path": str(path)})
    manager._jobs[source.id] = source
    payload.pop("requestId")
    payload["retryOf"] = source.id
    retry = http.post("/api/uploads", json=payload)
    repeated = http.post("/api/uploads", json=payload)
    assert retry.status_code == repeated.status_code == 202
    assert retry.json["id"] == repeated.json["id"]
    assert http.get("/api/jobs/" + source.id).json["retryJobId"] == retry.json["id"]


def test_retry_endpoint_rejects_a_different_local_file_and_malformed_ids(client):
    http, manager, path, token = client
    source = Job(id="e" * 32, kind="share", status="failed", result={"path": str(path.with_name("other.mp4"))})
    manager._jobs[source.id] = source
    assert http.post("/api/uploads", json={"token": token, "destination": "local", "retryOf": source.id}).status_code == 400
    assert http.post("/api/uploads", json={"token": token, "destination": "local", "requestId": []}).status_code == 400
    assert source.retry_job_id is None
