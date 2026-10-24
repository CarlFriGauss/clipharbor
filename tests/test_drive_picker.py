import json
import threading
from urllib.parse import parse_qs, urlsplit, urlencode
from urllib.request import urlopen

import pytest

from mediaforge import publishing as p


@pytest.fixture
def store(tmp_path, monkeypatch):
    value = p.Connections(tmp_path / "accounts.dat")
    monkeypatch.setattr(p, "connections", value)
    value.put("drive", {"client_id": "client", "access_token": "previous-access", "refresh_token": "previous-refresh", "folder_id": "previous", "folder_name": "Previous"})
    return value


class Context:
    def update(self, *args):
        pass


def picker_response(monkeypatch, *, selection="chosen", error=None):
    parameters = []
    threads = []
    def open_browser(url):
        query = parse_qs(urlsplit(url).query)
        parameters.append(query)
        callback = {"state": query["state"][0], "picked_file_ids": selection}
        callback.update({"error": error} if error else {"code": "authorization-code"})
        target = query["redirect_uri"][0] + "?" + urlencode(callback)
        thread = threading.Thread(target=lambda: urlopen(target, timeout=5).close())
        threads.append(thread); thread.start()
        return True
    monkeypatch.setattr(p.webbrowser, "open", open_browser)
    monkeypatch.setattr(p, "_form", lambda *a, **k: {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600})
    return parameters, threads


def test_picker_limits_scope_and_remembers_selected_folder(store, monkeypatch):
    params, threads = picker_response(monkeypatch)
    def metadata(method, url, **kwargs):
        assert "files/chosen?" in url and kwargs["token"] == "new-access"
        return {"id": "chosen", "name": "Selected destination", "mimeType": "application/vnd.google-apps.folder", "capabilities": {"canAddChildren": True}}
    monkeypatch.setattr(p, "_request", metadata)
    result = p.authorize_google(Context(), provider="drive", credentials={"installed": {"client_id": "client"}}, pick_folder=True)
    for thread in threads:
        thread.join(5)
    assert params[0]["scope"] == [p.SCOPES["drive"]]
    assert params[0]["allow_folder_selection"] == ["true"] and params[0]["allow_multiple"] == ["false"]
    assert params[0]["trigger_onepick"] == ["true"]
    assert result["folderId"] == "chosen" and store.get("drive")["folder_name"] == "Selected destination"
    assert not store.get("drive")["existing_folder_access"]
    assert "new-refresh" not in json.dumps(result)


@pytest.mark.parametrize("selection", ["", "one,two", "../../private", "https://example.com/folder"])
def test_invalid_picker_selection_keeps_previous_connection(store, monkeypatch, selection):
    picker_response(monkeypatch, selection=selection)
    monkeypatch.setattr(p, "_request", lambda *a, **k: pytest.fail("Invalid selections must not call Drive"))
    with pytest.raises(p.PublishError):
        p.authorize_google(Context(), provider="drive", credentials={"installed": {"client_id": "client"}}, pick_folder=True)
    assert store.get("drive")["refresh_token"] == "previous-refresh"
    assert store.get("drive")["folder_id"] == "previous"


def test_cancel_and_readonly_folder_keep_previous_default(store, monkeypatch):
    picker_response(monkeypatch, error="access_denied")
    with pytest.raises(p.PublishError):
        p.authorize_google(Context(), provider="drive", credentials={"installed": {"client_id": "client"}}, pick_folder=True)
    picker_response(monkeypatch)
    monkeypatch.setattr(p, "_request", lambda *a, **k: {"id": "chosen", "name": "Read-only", "mimeType": "application/vnd.google-apps.folder", "capabilities": {"canAddChildren": False}})
    with pytest.raises(p.PublishError, match="permission"):
        p.authorize_google(Context(), provider="drive", credentials={"installed": {"client_id": "client"}}, pick_folder=True)
    assert store.get("drive")["folder_id"] == "previous"


def test_queued_destination_does_not_follow_later_default_changes(store, monkeypatch):
    options = p.snapshot_destination("drive", {})
    store.put("drive", {**store.get("drive"), "folder_id": "new-default"})
    assert options["folderId"] == "previous" and options["useAppFolder"] is False
    monkeypatch.setattr(p, "_request", lambda *a, **k: {"id": "previous", "name": "Previous", "mimeType": "application/vnd.google-apps.folder"})
    assert p.drive_folder("token", options["folderId"], remember=False) == "previous"
    assert store.get("drive")["folder_id"] == "new-default"
