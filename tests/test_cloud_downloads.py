from __future__ import annotations

from pathlib import Path

import pytest

from mediaforge import cloud_downloads as cloud, publishing
from mediaforge.jobs import Job, JobContext, JobManager


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, "data_root", lambda: tmp_path)
    class MemoryVault:
        value = b"{}"
        def read(self):
            return self.value
        def write(self, value):
            self.value = value
    store = publishing.Connections(tmp_path / "connections" / "accounts.dat", vault=MemoryVault())
    store.put("drive", {"access_token": "token", "folder_id": "folder"})
    monkeypatch.setattr(publishing, "connections", store)
    manager = JobManager()
    job = Job(id="download-test", kind="download")
    manager._jobs[job.id] = job
    context = JobContext(manager, job.id)
    local = tmp_path / "local-output"
    local.mkdir()
    original = local / "existing.mp4"
    original.write_bytes(b"do not change")

    def download(context, **kwargs):
        directory = Path(kwargs["output_directory"])
        (directory / "leftover.part").write_bytes(b"partial")
        path = directory / "video.mp4"
        path.write_bytes(b"video")
        context.update(96, "Processing")
        return {"path": str(path), "token": kwargs["register"](path), "media": {"name": path.name, "size": 5, "kind": "video", "video": True}}

    monkeypatch.setattr(cloud, "download", download)
    kwargs = {"output_directory": str(local), "output_format": "mp4", "url": "https://example.com/video", "register": lambda path: "registered"}
    yield context, job, kwargs, store
    cloud._active.clear()


def delivered(context, *, result, **kwargs):
    assert Path(result["path"]).is_file()
    return {**result, "delivery": {"provider": "drive", "url": "https://drive.google.com/file/d/uploaded/view", "visibility": "Drive sharing unchanged"}}


def fail_upload(*args, **kwargs):
    raise publishing.PublishError("Network interrupted")


def test_cloud_download_verifies_upload_then_cleans_only_its_staging(setup, monkeypatch):
    context, job, kwargs, store = setup
    observed = []
    monkeypatch.setattr(publishing, "access_token", lambda provider: "token")
    monkeypatch.setattr(publishing, "drive_folder", lambda *args, **kwargs: "folder")
    monkeypatch.setattr(publishing, "_google_upload", lambda *args: {"id": "uploaded"})

    def verify(method, url, **options):
        observed.append(list(cloud.staging_root().glob("download-*/video.mp4")))
        return {"id": "uploaded", "size": "5", "parents": ["folder"]}

    monkeypatch.setattr(publishing, "_request", verify)
    result = cloud.download_to_destination(context, provider="drive", **kwargs)
    assert observed[0] and result["delivery"]["provider"] == "drive"
    assert result["path"] is None and result["token"] is None
    assert result["localAvailable"] is False
    assert not list(cloud.staging_root().iterdir())
    assert (Path(kwargs["output_directory"]) / "existing.mp4").read_bytes() == b"do not change"
    assert not (Path(kwargs["output_directory"]) / "video.mp4").exists()


def test_local_download_uses_output_folder_and_never_uploads(setup, monkeypatch):
    context, job, kwargs, store = setup
    monkeypatch.setattr(cloud, "upload", lambda *a, **k: pytest.fail("Local download attempted upload"))
    result = cloud.download_to_destination(context, **kwargs)
    assert Path(result["path"]).parent == Path(kwargs["output_directory"])
    assert result["token"] == "registered"
    assert not cloud.staging_root().exists()


def test_failed_upload_survives_reload_and_retries_without_downloading(setup, monkeypatch):
    context, job, kwargs, store = setup
    monkeypatch.setattr(cloud, "upload", fail_upload)
    with pytest.raises(publishing.PublishError, match="Retry upload"):
        cloud.download_to_destination(context, provider="drive", delivery_options={"folderId": "folder"}, **kwargs)
    pending = cloud.pending_downloads()
    assert len(pending) == 1
    assert job.result == pending[0]
    assert Path(pending[0]["path"]).read_bytes() == b"video"
    assert pending[0]["token"] is None
    monkeypatch.setattr(cloud, "download", lambda *a, **k: pytest.fail("Retry downloaded again"))
    monkeypatch.setattr(cloud, "upload", delivered)
    result = cloud.reserve_retry(pending[0]["cloudDownloadId"])
    assert cloud.pending_downloads() == []
    done = cloud.retry_cloud_download(context, result=result)
    assert done["localAvailable"] is False
    assert not list(cloud.staging_root().iterdir())


def test_failed_verification_keeps_the_only_complete_copy(setup, monkeypatch):
    context, job, kwargs, store = setup
    monkeypatch.setattr(publishing, "access_token", lambda provider: "token")
    monkeypatch.setattr(publishing, "drive_folder", lambda *args, **kwargs: "folder")
    monkeypatch.setattr(publishing, "_google_upload", lambda *args: {"id": "uploaded"})
    monkeypatch.setattr(publishing, "_request", lambda *a, **k: {"size": "4", "parents": ["folder"]})
    with pytest.raises(publishing.PublishError, match="verify"):
        cloud.download_to_destination(context, provider="drive", **kwargs)
    assert Path(job.result["path"]).is_file()


def test_failed_source_download_removes_partial_files(setup, monkeypatch):
    context, job, kwargs, store = setup
    def broken(context, **kwargs):
        (Path(kwargs["output_directory"]) / "video.part").write_bytes(b"partial")
        raise RuntimeError("Source unavailable")
    monkeypatch.setattr(cloud, "download", broken)
    with pytest.raises(RuntimeError, match="Source unavailable"):
        cloud.download_to_destination(context, provider="drive", **kwargs)
    assert not list(cloud.staging_root().iterdir())


def test_discard_and_retry_cannot_race_an_active_upload(setup, monkeypatch):
    context, job, kwargs, store = setup
    monkeypatch.setattr(cloud, "upload", fail_upload)
    with pytest.raises(publishing.PublishError):
        cloud.download_to_destination(context, provider="drive", **kwargs)
    download_id = job.result["cloudDownloadId"]
    cloud.reserve_retry(download_id)
    with pytest.raises(ValueError, match="already running"):
        cloud.reserve_retry(download_id)
    with pytest.raises(ValueError, match="Wait"):
        cloud.discard_download(download_id)
    assert Path(job.result["path"]).is_file()
    cloud.release_retry(download_id)
    cloud.discard_download(download_id)
    assert cloud.pending_downloads() == []


def test_cleanup_failure_keeps_receipt_and_never_reuploads(setup, monkeypatch):
    context, job, kwargs, store = setup
    monkeypatch.setattr(cloud, "upload", delivered)
    remove = cloud._remove
    monkeypatch.setattr(cloud, "_remove", lambda *a, **k: (_ for _ in ()).throw(PermissionError("File locked")))
    result = cloud.download_to_destination(context, provider="drive", **kwargs)
    assert result["cleanupPending"] and result["cleanupWarning"]
    assert cloud.pending_downloads()[0]["delivery"]
    with pytest.raises(ValueError, match="already uploaded"):
        cloud.reserve_retry(result["cloudDownloadId"])
    monkeypatch.setattr(cloud, "_remove", remove)
    cloud.discard_download(result["cloudDownloadId"])
    assert not list(cloud.staging_root().iterdir())


@pytest.mark.parametrize("download_id", ["../outside", "download-../../outside", "outside", "download-"])
def test_cleanup_cannot_escape_staging(setup, download_id):
    with pytest.raises(ValueError, match="Invalid"):
        cloud.discard_download(download_id)


def test_download_routes_preflight_and_preserve_local_default(setup, monkeypatch):
    from mediaforge import web
    context, job, kwargs, store = setup
    monkeypatch.setattr(web, "connections", store)
    client = web.create_app().test_client()
    captured = []
    monkeypatch.setattr(web.jobs, "start", lambda *args, **kwargs: (captured.append((args, kwargs)) or job))
    data = {"url": "https://example.com/video", "outputFormat": "mp4"}
    assert client.post("/api/downloads", json={**data, "destination": "dropbox"}).status_code == 400
    assert client.post("/api/downloads", json=data).status_code == 400
    assert client.post("/api/downloads", json={**data, "destination": "drive", "deliveryOptions": "bad"}).status_code == 400
    assert not captured
    assert client.post("/api/downloads", json={**data, "destination": "drive"}).status_code == 202
    assert captured[-1][1]["provider"] == "drive"
    assert captured[-1][1]["output_directory"] == ""
    assert client.post("/api/downloads", json={**data, "outputDirectory": kwargs["output_directory"]}).status_code == 202
    assert captured[-1][1]["provider"] == "local"
    store.put("drive", None)
    assert client.post("/api/downloads", json={**data, "destination": "drive"}).status_code == 400
    assert len(captured) == 2


def test_cloud_download_routes_block_cross_origin_requests(setup):
    from mediaforge.web import create_app
    client = create_app().test_client()
    for path in ("/api/downloads", "/api/downloads/pending/download-test/retry"):
        assert client.post(path, json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.delete("/api/downloads/pending/download-test", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/downloads/pending").headers["Cache-Control"] == "no-store"


def test_interrupted_source_download_can_be_discarded_after_restart(setup):
    directory = cloud.staging_root() / "download-interrupted"
    directory.mkdir(parents=True)
    (directory / "source.part").write_bytes(b"partial")
    cloud._save({"cloudDownloadId": directory.name, "incomplete": True, "media": {"name": "Interrupted cloud download"}})
    pending = cloud.pending_downloads()
    assert pending[0]["incomplete"] and pending[0]["path"] is None
    with pytest.raises(ValueError, match="interrupted"):
        cloud.reserve_retry(directory.name)
    cloud.discard_download(directory.name)
    assert not directory.exists()


def test_partial_cleanup_preserves_receipt_when_media_was_already_removed(setup, monkeypatch):
    context, job, kwargs, store = setup
    monkeypatch.setattr(cloud, "upload", delivered)
    remove = cloud._remove
    def partially_remove(download_id):
        (cloud._directory(download_id) / "video.mp4").unlink()
        raise PermissionError("Another temporary file is locked")
    monkeypatch.setattr(cloud, "_remove", partially_remove)
    result = cloud.download_to_destination(context, provider="drive", **kwargs)
    assert not Path(result["path"]).exists()
    assert cloud.pending_downloads()[0]["delivery"]
    with pytest.raises(ValueError, match="already uploaded"):
        cloud.reserve_retry(result["cloudDownloadId"])
    monkeypatch.setattr(cloud, "_remove", remove)
    cloud.discard_download(result["cloudDownloadId"])
    assert cloud.pending_downloads() == []


def test_cleanup_leaves_manifest_when_a_temporary_file_is_locked(setup, monkeypatch):
    context, job, kwargs, store = setup
    monkeypatch.setattr(cloud, "upload", delivered)
    original_unlink = Path.unlink
    def locked_unlink(path, *args, **kwargs):
        if path.name == "leftover.part":
            raise PermissionError("File locked")
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", locked_unlink)
    result = cloud.download_to_destination(context, provider="drive", **kwargs)
    assert result["cleanupPending"]
    assert cloud.pending_downloads()[0]["delivery"]
    monkeypatch.setattr(Path, "unlink", original_unlink)
    cloud.discard_download(result["cloudDownloadId"])
    assert cloud.pending_downloads() == []
