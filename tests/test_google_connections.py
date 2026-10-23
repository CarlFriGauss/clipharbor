from __future__ import annotations

import base64
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

import pytest

from mediaforge import google_config, publishing as p
from mediaforge.credential_store import SecureCredentialStore, CredentialStoreError
from mediaforge.jobs import Job


@pytest.fixture
def account_store(tmp_path, monkeypatch):
    store = p.Connections(tmp_path / "private" / "accounts.dat")
    monkeypatch.setattr(p, "connections", store)
    # The web API and both upload features use the very same provider store.
    from mediaforge import web
    monkeypatch.setattr(web, "connections", store)
    monkeypatch.delenv("CLIPHARBOR_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CLIPHARBOR_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CLIPHARBOR_GOOGLE_CLIENT_FILE", raising=False)
    monkeypatch.setattr(google_config, "RESOURCE_ROOT", tmp_path)
    return store


def saved_account(**changes):
    return {"client_id": "1234-desktop.apps.googleusercontent.com", "client_secret": "app-registration",
            "refresh_token": "private-refresh-token", "access_token": "expired-access-token",
            "expires_at": 0, "folder_id": "dedicated", **changes}


def test_clean_source_checkout_uses_publisher_identity_without_a_user_account(account_store, tmp_path):
    registration = tmp_path / "publisher" / "google-oauth-client.json"
    registration.parent.mkdir()
    registration.write_text(json.dumps({"installed": {"client_id": "publisher.apps.googleusercontent.com", "client_secret": "public-native-client"}}))
    assert google_config.google_client()["installed"]["client_id"] == "publisher.apps.googleusercontent.com"
    assert account_store.status()["youtube"]["googleConfigured"]
    assert account_store.status()["drive"]["googleConfigured"]
    assert not any(account["connected"] for account in account_store.status().values())


def test_one_connection_survives_restart_and_serves_both_features(account_store, monkeypatch):
    from mediaforge import web
    account_store.put("drive", saved_account())
    restarted = p.Connections(account_store.path)
    monkeypatch.setattr(p, "connections", restarted)
    monkeypatch.setattr(web, "connections", restarted)
    monkeypatch.setattr(p.webbrowser, "open", lambda *a: pytest.fail("A remembered account must not reopen Google sign-in"))
    refreshes = []
    def refresh(*args):
        refreshes.append(args)
        return {"access_token": "renewed-access", "expires_in": 3600}
    monkeypatch.setattr(p, "_form", refresh)
    assert p.access_token("drive") == "renewed-access"
    assert p.access_token("drive") == "renewed-access"
    assert len(refreshes) == 1
    calls = []
    def start(kind, target, **kwargs):
        calls.append((kind, kwargs["provider"]))
        return Job(id=kind, kind=kind)
    monkeypatch.setattr(web.jobs, "start", start)
    client = web.create_app().test_client()
    assert client.post("/api/renders", json={"destination": "drive", "project": {}, "outputFormat": "mp4"}).status_code == 202
    assert client.post("/api/downloads", json={"destination": "drive", "url": "https://example.com/video", "outputFormat": "mp4"}).status_code == 202
    assert calls == [("render", "drive"), ("download", "drive")]
    status = client.get("/api/connections").json
    assert status["drive"]["connected"]
    assert status["drive"]["folderId"] == "dedicated"
    assert "private-refresh-token" not in json.dumps(status)


def test_simultaneous_export_and_download_only_refresh_once(account_store, monkeypatch):
    account_store.put("drive", saved_account())
    refreshes = []
    def refresh(*args):
        refreshes.append(args)
        time.sleep(.03)
        return {"access_token": "renewed-access", "refresh_token": "rotated-refresh", "expires_in": 3600}
    monkeypatch.setattr(p, "_form", refresh)
    with ThreadPoolExecutor(max_workers=6) as executor:
        assert list(executor.map(lambda _: p.access_token("drive"), range(6))) == ["renewed-access"] * 6
    assert len(refreshes) == 1
    assert p.Connections(account_store.path).get("drive")["refresh_token"] == "rotated-refresh"
    if p.os.name == "nt":
        assert b"rotated-refresh" not in account_store.path.read_bytes()


def test_revoked_authorization_marks_shared_connection_for_signin(account_store, monkeypatch):
    account_store.put("drive", saved_account())
    def revoked(*args):
        raise p.PublishError("Revoked", status=400, oauth_error="invalid_grant")
    monkeypatch.setattr(p, "_form", revoked)
    with pytest.raises(p.PublishError, match="either Download or Export"):
        p.access_token("drive")
    assert not account_store.status()["drive"]["connected"]
    assert account_store.status()["drive"]["needsReconnect"]
    assert not account_store.get("drive").get("refresh_token")
    from mediaforge.web import create_app
    client = create_app().test_client()
    for endpoint in ("/api/renders", "/api/downloads"):
        assert client.post(endpoint, json={"destination": "drive"}).status_code == 400


def test_network_failure_keeps_valid_refresh_authorization(account_store, monkeypatch):
    account_store.put("drive", saved_account())
    def offline(*args):
        raise p.PublishError("Offline")
    monkeypatch.setattr(p, "_form", offline)
    with pytest.raises(p.PublishError, match="Offline"):
        p.access_token("drive")
    assert account_store.get("drive")["refresh_token"] == "private-refresh-token"
    assert not account_store.status()["drive"]["needsReconnect"]


def test_timed_authorization_requests_signin_again(account_store, monkeypatch):
    account_store.put("drive", saved_account(refresh_expires_at=time.time() - 1))
    monkeypatch.setattr(p, "_form", lambda *a: pytest.fail("Expired authorization must not be reused"))
    assert not account_store.status()["drive"]["connected"]
    with pytest.raises(p.PublishError, match="expired"):
        p.access_token("drive")


def test_disconnect_clears_all_same_google_project_connections(account_store, monkeypatch):
    account_store.put("drive", saved_account())
    account_store.put("youtube", saved_account(client_id="1234-youtube.apps.googleusercontent.com"))
    account_store.put("x", {"access_token": "different-service"})
    revocations = []
    monkeypatch.setattr(p, "_form", lambda *a, **k: revocations.append((a, k)) or {})
    from mediaforge.web import create_app
    result = create_app().test_client().delete("/api/connections/drive").json
    assert result["revoked"] is True
    assert set(result["disconnected"]) == {"drive", "youtube"}
    assert not account_store.status()["drive"]["connected"]
    assert not account_store.status()["youtube"]["connected"]
    assert account_store.status()["x"]["connected"]
    assert revocations[0][0][1] == "https://oauth2.googleapis.com/revoke"
    assert "private-refresh-token" not in json.dumps(result)


def test_offline_disconnect_still_removes_local_tokens(account_store, monkeypatch):
    account_store.put("drive", saved_account())
    def offline(*a, **k):
        raise p.PublishError("Offline")
    monkeypatch.setattr(p, "_form", offline)
    result = p.disconnect_account("drive")
    assert result["revoked"] is False
    assert result["warning"]
    assert account_store.get("drive") == {}


def test_publisher_registration_replaces_per_user_json_setup(account_store, monkeypatch):
    from mediaforge import web
    monkeypatch.setenv("CLIPHARBOR_GOOGLE_CLIENT_ID", "publisher.apps.googleusercontent.com")
    captured = []
    monkeypatch.setattr(web.jobs, "start", lambda *a, **k: captured.append(k) or Job(id="sign-in", kind="connection"))
    client = web.create_app().test_client()
    status = client.get("/api/connections").json
    assert status["drive"]["googleConfigured"]
    assert client.post("/api/connections/drive", json={}).status_code == 202
    assert captured[0]["credentials"]["installed"]["client_id"] == "publisher.apps.googleusercontent.com"
    assert client.post("/api/connections/drive", json={"credentials": {"installed": {"client_id": "injected"}}}).status_code == 400
    html = client.get("/").get_data(as_text=True)
    assert 'id="googleCredentials"' not in html
    assert 'id="downloadGoogleCredentials"' not in html
    assert "Sign in with Google" in html


def test_missing_publisher_registration_is_reported_honestly(account_store):
    from mediaforge.web import create_app
    client = create_app().test_client()
    assert not client.get("/api/connections").json["drive"]["googleConfigured"]
    response = client.post("/api/connections/drive", json={})
    assert response.status_code == 400
    assert "publisher" in response.json["error"]


def test_bundle_registration_file_loads_without_user_tokens(account_store, tmp_path, monkeypatch):
    (tmp_path / "google-oauth-client.json").write_text(json.dumps({"installed": {"client_id": "publisher", "client_secret": "registration"}}))
    assert google_config.google_client()["installed"]["client_id"] == "publisher"
    from mediaforge.web import create_app
    assert "registration" not in json.dumps(create_app().test_client().get("/api/connections").json)


def test_oauth_error_description_never_leaks_tokens(account_store, monkeypatch):
    def denied(*a, **k):
        body = io.BytesIO(b'{"error":"invalid_grant","error_description":"private-refresh-token"}')
        raise HTTPError("https://oauth2.googleapis.com/token", 400, "bad", {}, body)
    monkeypatch.setattr(p.urllib.request, "urlopen", denied)
    with pytest.raises(p.PublishError) as caught:
        p._form("POST", "https://oauth2.googleapis.com/token", {"refresh_token": "private-refresh-token"})
    assert caught.value.oauth_error == "invalid_grant"
    assert "private-refresh-token" not in str(caught.value)


def test_bearer_tokens_are_not_forwarded_by_redirects(account_store, monkeypatch):
    requests = []
    def capture(request, **kwargs):
        requests.append(request)
        raise p.PublishError("Request captured")
    monkeypatch.setattr(p.urllib.request, "urlopen", capture)
    with pytest.raises(p.PublishError, match="captured"):
        p._request("GET", "https://www.googleapis.com/drive/v3/files", token="private-token")
    original = requests[0]
    assert original.get_header("Authorization") == "Bearer private-token"
    redirected = p.urllib.request.HTTPRedirectHandler().redirect_request(original, None, 302, "Moved", {}, "https://other.example/redirect")
    assert redirected.get_header("Authorization") is None


def test_disconnect_during_browser_signin_cannot_restore_connection(account_store, monkeypatch):
    from urllib.parse import parse_qs, urlsplit, urlencode
    from urllib.request import urlopen
    callbacks = []
    revoked = []
    def open_browser(url):
        query = parse_qs(urlsplit(url).query)
        callback_url = query["redirect_uri"][0] + "?" + urlencode({"state": query["state"][0], "code": "code"})
        thread = threading.Thread(target=lambda: urlopen(callback_url, timeout=5).close())
        callbacks.append(thread)
        thread.start()
        return True
    def exchange(method, url, values, **kwargs):
        if url.endswith("/revoke"):
            revoked.append(values["token"])
            return {}
        p.disconnect_account("drive")
        return {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
    monkeypatch.setattr(p.webbrowser, "open", open_browser)
    monkeypatch.setattr(p, "_form", exchange)
    class Context:
        def update(self, *args):
            pass
    with pytest.raises(p.PublishError, match="disconnected while sign-in was open"):
        p.authorize_google(Context(), provider="drive", credentials={"installed": {"client_id": "client"}})
    for thread in callbacks:
        thread.join(timeout=5)
    assert account_store.get("drive") == {}
    assert revoked == ["new-refresh"]


def test_no_plaintext_fallback_when_system_vault_is_unavailable(tmp_path, monkeypatch):
    vault = SecureCredentialStore(tmp_path / "accounts.dat")
    vault.platform = "linux"
    def unavailable(*a, **k):
        raise CredentialStoreError("Secure vault unavailable")
    monkeypatch.setattr(vault, "_run", unavailable)
    with pytest.raises(CredentialStoreError):
        vault.write(b'{"refresh_token":"private"}')
    assert not vault.path.exists()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_os_vault_receives_secret_on_stdin_not_process_arguments(tmp_path, monkeypatch, platform):
    vault = SecureCredentialStore(tmp_path / "accounts.dat")
    vault.platform = platform
    raw = b'{"refresh_token":"private"}'
    encoded = base64.b64encode(raw)
    calls = []
    monkeypatch.setattr(vault, "_run", lambda args, **kwargs: calls.append((args, kwargs)) or b"")
    monkeypatch.setattr(vault, "_native_read", lambda: encoded)
    vault.write(raw)
    args, kwargs = calls[0]
    assert encoded.decode() not in " ".join(args)
    assert encoded in kwargs["data"]
    assert not vault.path.exists()


def test_legacy_plaintext_moves_to_os_vault_before_file_removal(tmp_path, monkeypatch):
    raw = b'{"drive":{"refresh_token":"legacy"}}'
    path = tmp_path / "accounts.dat"
    path.write_bytes(raw)
    vault = SecureCredentialStore(path)
    vault.platform = "linux"
    native = []
    monkeypatch.setattr(vault, "_native_read", lambda: native[-1] if native else None)
    monkeypatch.setattr(vault, "_run", lambda args, **kwargs: native.append(kwargs["data"]) or b"")
    assert vault.read() == raw
    assert not path.exists()
    assert base64.b64decode(native[-1]) == raw
