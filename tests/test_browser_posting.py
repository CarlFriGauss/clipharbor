from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest

from mediaforge import browser_posting as b


class Context:
    def update(self, *args):
        pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "data_root", lambda: tmp_path)
    manager = b.FacebookTasks()
    manager.register("a" * 32, "https://www.facebook.com/Example.Person/?sk=posts", "Example Person")
    path = tmp_path / "video.mp4"; path.write_bytes(b"test-video")
    return manager, {"path": str(path), "media": {"video": True}}


def claim(manager):
    for _ in range(100):
        value = manager.poll("a" * 32)
        if value:
            return value
        time.sleep(.01)
    pytest.fail("Task was not queued")


def test_only_chosen_browser_claims_once_and_confirms_after_audience(setup):
    manager, result = setup
    with ThreadPoolExecutor() as pool:
        future = pool.submit(manager.run, Context(), result, {"description": "My caption", "audience": "only_me"})
        assert manager.poll("b" * 32) is None
        task = claim(manager)
        assert task["caption"] == "My caption" and task["profileUrl"] == "https://www.facebook.com/Example.Person"
        assert manager.poll("a" * 32) is None
        with pytest.raises(ValueError, match="audience"):
            manager.update("a" * 32, task["id"], task["lease"], "posting")
        with pytest.raises(ValueError, match="not confirmed"):
            manager.update("a" * 32, task["id"], task["lease"], "completed", url=task["profileUrl"])
        manager.update("a" * 32, task["id"], task["lease"], "audience_verified")
        manager.update("a" * 32, task["id"], task["lease"], "posting")
        manager.update("a" * 32, task["id"], task["lease"], "completed", url=task["profileUrl"])
        delivered = future.result(timeout=3)
    assert delivered["delivery"]["visibility"] == "Only me"
    assert not manager.tasks


def test_interrupted_publication_is_uncertain_and_never_requeued(setup):
    manager, result = setup
    with ThreadPoolExecutor() as pool:
        future = pool.submit(manager.run, Context(), result, {})
        task = claim(manager)
        manager.update("a" * 32, task["id"], task["lease"], "audience_verified")
        manager.update("a" * 32, task["id"], task["lease"], "posting")
        manager.update("a" * 32, task["id"], task["lease"], "failed", message="Browser disconnected")
        with pytest.raises(b.BrowserPostingError) as caught:
            future.result(timeout=3)
        assert caught.value.uncertain and "may have posted" in str(caught.value)
    assert manager.poll("a" * 32) is None


def test_wrong_lease_and_result_host_are_rejected(setup):
    manager, result = setup
    with ThreadPoolExecutor() as pool:
        future = pool.submit(manager.run, Context(), result, {})
        task = claim(manager)
        with pytest.raises(ValueError):
            manager.update("a" * 32, task["id"], "wrong", "failed")
        manager.update("a" * 32, task["id"], task["lease"], "audience_verified")
        manager.update("a" * 32, task["id"], task["lease"], "posting")
        with pytest.raises(ValueError):
            manager.update("a" * 32, task["id"], task["lease"], "completed", url="https://evil.example/post")
        manager.update("a" * 32, task["id"], task["lease"], "failed", message="No receipt")
        with pytest.raises(b.BrowserPostingError):
            future.result(timeout=3)


@pytest.mark.parametrize("url", ["https://evil.example/name", "https://www.facebook.com/login", "https://www.facebook.com/groups/test", "http://www.facebook.com/name", "https://www.facebook.com/profile.php?id=invalid"])
def test_connection_accepts_only_explicit_facebook_profile_urls(url):
    with pytest.raises(ValueError):
        b.profile_url(url)


def test_stale_browser_cannot_start_publication(setup):
    manager, result = setup
    manager.last_seen.clear()
    with pytest.raises(b.BrowserPostingError, match="Enable"):
        manager.run(Context(), result, {})
    assert not manager.tasks
