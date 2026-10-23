"""Optional cloud exports using only the Python standard library."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .runtime import data_root
from .credential_store import SecureCredentialStore, CredentialStoreError
from .google_config import google_client, GoogleConfigurationError

CHUNK = 4 * 1024 * 1024
DESTINATIONS = {"local", "drive", "youtube", "x", "facebook"}
SCOPES = {
    "drive": "https://www.googleapis.com/auth/drive.file",
    "youtube": "https://www.googleapis.com/auth/youtube.upload",
}


class PublishError(RuntimeError):
    def __init__(self, message, *, status=None, oauth_error=None):
        super().__init__(message)
        self.status = status
        self.oauth_error = oauth_error


class Connections:
    def __init__(self, path=None, vault=None):
        self.path = Path(path) if path else data_root() / ".connections" / "accounts.dat"
        self.lock = threading.RLock()
        self.vault = vault if vault is not None else SecureCredentialStore(self.path)

    def _read(self):
        try:
            data = json.loads(self.vault.read())
            if not isinstance(data, dict):
                raise ValueError
            return data
        except CredentialStoreError as error:
            raise PublishError(str(error)) from None
        except ValueError:
            raise PublishError("The saved connection is damaged. Sign in again.") from None

    def get(self, provider):
        with self.lock:
            return dict(self._read().get(provider, {}))

    def put(self, provider, value):
        with self.lock:
            data = self._read()
            if value:
                data[provider] = value
            else:
                data.pop(provider, None)
            try:
                self.vault.write(json.dumps(data).encode())
            except CredentialStoreError as error:
                raise PublishError(str(error)) from None

    def status(self):
        with self.lock:
            accounts = self._read()
        status = {}
        for provider in ("drive", "youtube", "x", "facebook"):
            account = accounts.get(provider, {})
            needs_reconnect = bool(account.get("needs_reconnect")) or bool(account.get("refresh_expires_at") and account["refresh_expires_at"] <= time.time())
            configured = False
            if provider in SCOPES:
                try:
                    google_client(account)
                    configured = True
                except GoogleConfigurationError:
                    pass
            status[provider] = {
                "connected": not needs_reconnect and bool(account.get("access_token") or account.get("refresh_token")),
                "needsReconnect": needs_reconnect,
                "googleConfigured": configured,
                "folderName": account.get("folder_name", "ClipHarbor Exports"),
                "folderId": account.get("folder_id", ""),
                "pageId": account.get("page_id", ""),
            }
        return status


connections = Connections()
_account_locks = {provider: threading.RLock() for provider in DESTINATIONS}
_connection_versions = {provider: 0 for provider in DESTINATIONS}


def _request(method, url, *, token=None, data=None, headers=None, raw=False, allow=(), timeout=90):
    hdr = dict(headers or {})
    if token:
        hdr["Authorization"] = "Bearer " + token
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        hdr["Content-Type"] = "application/json"
    authorization = hdr.pop("Authorization", None)
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    if authorization:
        # urllib omits unredirected headers when building a redirect request.
        # A service redirect must never forward a user's bearer token elsewhere.
        req.add_unredirected_header("Authorization", authorization)
    try:
        response = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in allow:
            response = exc
        else:
            # Never return request URLs, credentials, or provider bodies containing them.
            oauth_error = None
            if urllib.parse.urlsplit(url).hostname == "oauth2.googleapis.com":
                try:
                    code = json.loads(exc.read(8192)).get("error")
                    if isinstance(code, str) and code in {"invalid_grant", "invalid_client", "invalid_token", "access_denied"}:
                        oauth_error = code
                except (ValueError, AttributeError):
                    pass
            raise PublishError(f"The service returned HTTP {exc.code}. Check connection permissions, account limits and API access, then retry.", status=exc.code, oauth_error=oauth_error) from None
    except (OSError, urllib.error.URLError):
        raise PublishError("The service could not be reached. Check your connection and retry.") from None
    with response:
        body = response.read()
        if raw:
            return response.status, dict(response.headers), body
        return json.loads(body) if body else {}


def _form(method, url, values, **kwargs):
    return _request(method, url, data=urllib.parse.urlencode(values).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}, **kwargs)


def access_token(provider):
    with _account_locks[provider]:
        return _access_token(provider)


def _require_reconnect(provider, account):
    for key in ("access_token", "refresh_token", "expires_at", "refresh_expires_at"):
        account.pop(key, None)
    account["needs_reconnect"] = True
    connections.put(provider, account)


def _access_token(provider):
    account = connections.get(provider)
    if not account:
        raise PublishError("Connect this destination in Export before uploading.")
    if account.get("needs_reconnect") or (account.get("refresh_expires_at") and account["refresh_expires_at"] <= time.time()):
        _require_reconnect(provider, account)
        raise PublishError("Google's saved authorization has expired or been revoked. Sign in again in either Download or Export.")
    if provider in SCOPES and account.get("refresh_token") and account.get("expires_at", 0) < time.time() + 60:
        values = {"client_id": account["client_id"], "refresh_token": account["refresh_token"], "grant_type": "refresh_token"}
        if account.get("client_secret"):
            values["client_secret"] = account["client_secret"]
        try:
            response = _form("POST", "https://oauth2.googleapis.com/token", values)
        except PublishError as error:
            if error.oauth_error in {"invalid_grant", "invalid_token"}:
                _require_reconnect(provider, account)
                raise PublishError("Google's saved authorization has expired or been revoked. Sign in again in either Download or Export.") from None
            raise
        if not response.get("access_token"):
            raise PublishError("Google could not renew this connection. Please try again.")
        account.update(access_token=response["access_token"], expires_at=time.time() + response.get("expires_in", 3600))
        if response.get("refresh_token"):
            account["refresh_token"] = response["refresh_token"]
        if response.get("refresh_token_expires_in"):
            account["refresh_expires_at"] = time.time() + response["refresh_token_expires_in"]
        connections.put(provider, account)
    token = account.get("access_token")
    if not token:
        raise PublishError("Your connection has expired. Reconnect in Export.")
    return token


def authorize_google(context, *, provider, credentials=None, folder_id=""):
    if provider not in SCOPES:
        raise ValueError("Unknown Google destination")
    folder_id = str(folder_id).strip() if provider == "drive" else ""
    if folder_id and not re.fullmatch(r"[\w-]+", folder_id):
        raise ValueError("Use a Google Drive folder ID, not a folder URL.")
    credentials = credentials or google_client(connections.get(provider))
    connections.vault.ensure_available()
    with _account_locks[provider]:
        connection_version = _connection_versions[provider]
    installed = credentials.get("installed", {})
    client_id, client_secret = installed.get("client_id"), installed.get("client_secret")
    if not client_id:
        raise ValueError("Google sign-in has not been configured by the ClipHarbor publisher.")
    previous = connections.get(provider)
    known_app_folder = (folder_id and folder_id == previous.get("folder_id")
                        and previous.get("client_id") == client_id
                        and not previous.get("existing_folder_access"))
    existing_folder_access = bool(folder_id) and not known_app_folder
    requested_scope = "https://www.googleapis.com/auth/drive" if existing_folder_access else SCOPES[provider]
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if urllib.parse.urlsplit(self.path).path != "/callback" or not secrets.compare_digest(query.get("state", [""])[0], nonce):
                self.send_error(400, "Invalid sign-in response")
                return
            result.update(code=query.get("code", [None])[0], error=query.get("error", [None])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(b"<p>Return to ClipHarbor to finish connecting. You may close this tab.</p>")

    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/callback"
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
            "scope": requested_scope, "access_type": "offline", "prompt": "consent",
            "state": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
        })
        context.update(5, "Complete Google sign-in in your browser")
        if not webbrowser.open(url):
            raise PublishError("Could not open the browser for Google sign-in.")
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
        if not result.get("code"):
            raise PublishError("Google sign-in was cancelled or timed out. Try connecting again.")
    values = {
        "client_id": client_id, "code": result["code"],
        "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code",
    }
    if client_secret:
        values["client_secret"] = client_secret
    response = _form("POST", "https://oauth2.googleapis.com/token", values)
    if not response.get("refresh_token"):
        raise PublishError("Google did not grant offline access. Reconnect and allow the requested permission.")
    account = {
        "client_id": client_id, "client_secret": client_secret,
        "access_token": response["access_token"], "refresh_token": response["refresh_token"],
        "expires_at": time.time() + response.get("expires_in", 3600),
        "folder_name": previous.get("folder_name", "ClipHarbor Exports"), "folder_id": folder_id, "existing_folder_access": existing_folder_access,
    }
    if response.get("refresh_token_expires_in"):
        account["refresh_expires_at"] = time.time() + response["refresh_token_expires_in"]
    with _account_locks[provider]:
        if _connection_versions[provider] != connection_version:
            try:
                _form("POST", "https://oauth2.googleapis.com/revoke", {"token": response["refresh_token"]}, timeout=15)
            except PublishError:
                pass
            raise PublishError("This connection was disconnected while sign-in was open. Start sign-in again if needed.")
        connections.put(provider, account)
    return {"provider": provider, "connected": True}


def disconnect_account(provider):
    if provider not in DESTINATIONS - {"local"}:
        raise ValueError("Unknown destination")
    with ExitStack() as stack:
        for name in sorted(SCOPES if provider in SCOPES else {provider}):
            stack.enter_context(_account_locks[name])
        account = connections.get(provider)
        removed = [provider]
        if provider in SCOPES and account.get("client_id"):
            project = account["client_id"].split("-", 1)[0]
            for name in SCOPES:
                other = connections.get(name).get("client_id", "")
                if name != provider and (other == account["client_id"] or (project.isdigit() and other.startswith(project + "-"))):
                    removed.append(name)
        for name in removed:
            _connection_versions[name] += 1
            connections.put(name, None)
        revoked = None
        token = account.get("refresh_token") or account.get("access_token")
        if provider in SCOPES and token:
            try:
                _form("POST", "https://oauth2.googleapis.com/revoke", {"token": token}, timeout=15)
                revoked = True
            except PublishError:
                revoked = False
    return {"ok": True, "disconnected": removed, "revoked": revoked,
            "warning": "The connection was removed from ClipHarbor. Google could not be reached to revoke access; you can remove ClipHarbor in your Google account's connections." if revoked is False else None}


def connect_token(provider, token, page_id=""):
    token = str(token).strip()
    if not token or len(token) > 8192 or any(c.isspace() for c in token):
        raise ValueError("Enter a valid user access token.")
    if provider == "x":
        _request("GET", "https://api.x.com/2/users/me", token=token)
    elif provider == "facebook":
        if not re.fullmatch(r"\d+", page_id):
            raise ValueError("Enter the numeric Facebook Page ID.")
        page = _request("GET", f"https://graph.facebook.com/v26.0/{page_id}?fields=id,name", token=token)
        if page.get("id") != page_id:
            raise ValueError("The token does not match this Facebook Page.")
    else:
        raise ValueError("Use Google sign-in for this destination.")
    connections.put(provider, {"access_token": token, "page_id": page_id})


def validate_destination(provider, output_format, options=None):
    if provider not in DESTINATIONS:
        raise ValueError("Unknown export destination")
    if provider == "local":
        return
    if not connections.status()[provider]["connected"]:
        raise ValueError("Connect this destination before starting the export.")
    if provider != "drive" and output_format != "mp4":
        raise ValueError("Choose MP4 for social video exports.")
    options = options or {}
    if provider == "youtube" and options.get("privacy", "private") not in {"private", "unlisted", "public"}:
        raise ValueError("Unknown YouTube visibility.")
    if provider == "x" and len(str(options.get("description", ""))) > 280:
        raise ValueError("X post text must be at most 280 characters.")
    if provider == "x" and options.get("publish") is not True:
        raise ValueError("Select Publish to X to create a post.")
    if provider == "drive":
        folder_id = str(options.get("folderId", "")).strip()
        if folder_id and not re.fullmatch(r"[\w-]+", folder_id):
            raise ValueError("Use a Google Drive folder ID, not a folder URL.")
        account = connections.get("drive")
        if folder_id and folder_id != account.get("folder_id") and not account.get("existing_folder_access"):
            raise ValueError("Reconnect Google Drive with this folder ID to authorize access to an existing folder.")


_folder_lock = threading.RLock()


def drive_folder(token, requested=""):
    with _folder_lock, _account_locks["drive"]:
        account = connections.get("drive")
        folder_id = requested or account.get("folder_id")
        if folder_id:
            folder = _request("GET", "https://www.googleapis.com/drive/v3/files/" + folder_id +
                              "?fields=id,name,mimeType,trashed&supportsAllDrives=true", token=token)
            if folder.get("trashed") or folder.get("mimeType") != "application/vnd.google-apps.folder":
                raise PublishError("The saved Google Drive folder is unavailable. Choose another folder.")
        else:
            query = urllib.parse.urlencode({
                "q": "name = 'ClipHarbor Exports' and mimeType = 'application/vnd.google-apps.folder' and trashed = false and 'root' in parents",
                "fields": "files(id,name)", "pageSize": 100,
            })
            folders = _request("GET", "https://www.googleapis.com/drive/v3/files?" + query, token=token).get("files", [])
            folder = folders[0] if folders else _request("POST", "https://www.googleapis.com/drive/v3/files",
                token=token, data={"name": "ClipHarbor Exports", "mimeType": "application/vnd.google-apps.folder"})
        account.update(folder_id=folder["id"], folder_name=folder["name"])
        connections.put("drive", account)
        return folder["id"]


def _google_upload(context, path, provider, metadata, token):
    total = path.stat().st_size
    if provider == "drive":
        url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true&fields=id,webViewLink,size,parents"
    else:
        url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    _, headers, _ = _request("POST", url, token=token, data=metadata, raw=True, headers={
        "X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(total),
    })
    session = next((v for k, v in headers.items() if k.lower() == "location"), "")
    parts = urllib.parse.urlsplit(session)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(".googleapis.com"):
        raise PublishError("Google did not return a valid upload session.")
    offset, failures = 0, 0
    with path.open("rb") as stream:
        while offset < total:
            stream.seek(offset)
            chunk = stream.read(CHUNK)
            try:
                status, hdr, body = _request("PUT", session, token=token, data=chunk, raw=True, allow=(308,),
                    headers={"Content-Type": mime, "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{total}"})
            except PublishError:
                failures += 1
                if failures > 3:
                    raise
                time.sleep(failures)
                # Ask how much arrived before resending, including an ambiguous final response.
                status, hdr, body = _request("PUT", session, token=token, data=b"", raw=True, allow=(308,),
                    headers={"Content-Range": f"bytes */{total}"})
            if status in (200, 201):
                result = json.loads(body)
                if not result.get("id"):
                    raise PublishError("Google did not confirm the uploaded file.")
                return result
            accepted = next((v for k, v in hdr.items() if k.lower() == "range"), "")
            match = re.fullmatch(r"bytes=0-(\d+)", accepted)
            next_offset = int(match.group(1)) + 1 if match else 0
            if next_offset <= offset:
                failures += 1
                if failures > 3:
                    raise PublishError("Google stopped accepting upload chunks. Retry the saved local file.")
            else:
                failures = 0
            offset = next_offset
            context.update(82 + 16 * offset / total, "Uploading to " + ("Google Drive" if provider == "drive" else "YouTube"))
    raise PublishError("Google did not confirm completion of the upload.")


def _multipart(fields, chunk, filename="video.mp4"):
    boundary = "ClipHarbor" + secrets.token_hex(16)
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="{filename}"\r\nContent-Type: video/mp4\r\n\r\n'.encode())
    return b"".join(parts) + chunk + f"\r\n--{boundary}--\r\n".encode(), "multipart/form-data; boundary=" + boundary


def _x_upload(context, path, token, description):
    base = "https://api.x.com/2/media/upload"
    media_id = _request("POST", base + "/initialize", token=token, data={
        "media_type": "video/mp4", "total_bytes": path.stat().st_size, "media_category": "tweet_video",
    })["data"]["id"]
    with path.open("rb") as stream:
        segment, sent = 0, 0
        while chunk := stream.read(CHUNK):
            data, mime = _multipart({"segment_index": segment}, chunk)
            _request("POST", base + f"/{media_id}/append", token=token, data=data, headers={"Content-Type": mime})
            segment += 1
            sent += len(chunk)
            context.update(82 + 13 * sent / path.stat().st_size, "Uploading video to X")
    response = _request("POST", base + f"/{media_id}/finalize", token=token, data=b"").get("data", {})
    deadline = time.monotonic() + 600
    while (info := response.get("processing_info")) and info.get("state") != "succeeded":
        if info.get("state") == "failed":
            raise PublishError("X could not process this video. Check the video limits for your account.")
        if time.monotonic() >= deadline:
            raise PublishError("X is still processing the video. No post was created; retry later.")
        context.update(97, "Waiting for X to process the video")
        time.sleep(min(30, max(1, int(info.get("check_after_secs", 2)))))
        response = _request("GET", base + "?" + urllib.parse.urlencode({"command": "STATUS", "media_id": media_id}), token=token).get("data", {})
    posted = _request("POST", "https://api.x.com/2/tweets", token=token,
        data={"text": description, "media": {"media_ids": [media_id]}})
    return {"id": posted["data"]["id"], "url": "https://x.com/i/status/" + posted["data"]["id"], "visibility": "published"}


def _facebook_upload(context, path, token, options):
    page_id = connections.get("facebook")["page_id"]
    # Stream multipart form data; memory use stays bounded even for large videos.
    boundary = "ClipHarbor" + secrets.token_hex(16)
    fields = {"title": str(options.get("title", path.stem))[:255],
              "description": str(options.get("description", "")), "published": "true" if options.get("publish") else "false"}
    prefix = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    prefix += f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="video.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()

    def body():
        yield prefix
        sent = 0
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK):
                yield chunk
                sent += len(chunk)
                context.update(82 + 16 * sent / path.stat().st_size, "Uploading to Facebook Page")
        yield suffix

    result = _request("POST", f"https://graph-video.facebook.com/v26.0/{page_id}/videos", token=token,
        data=body(), headers={"Content-Type": "multipart/form-data; boundary=" + boundary,
                             "Content-Length": str(len(prefix) + path.stat().st_size + len(suffix))})
    video_id = result.get("id")
    if not video_id:
        raise PublishError("Facebook did not confirm the video upload.")
    return {"id": video_id, "url": "https://www.facebook.com/" + video_id,
            "visibility": "published" if options.get("publish") else "unpublished"}


def upload(context, *, result, provider, options=None):
    options = options or {}
    if provider == "local":
        return result
    path = Path(result["path"])
    validate_destination(provider, path.suffix.lower().lstrip("."), options)
    if provider != "drive" and not result.get("media", {}).get("video"):
        raise ValueError("Social exports require a video.")
    token = access_token(provider)
    context.update(81, "Connecting to export destination")
    if provider == "drive":
        folder_id = drive_folder(token, str(options.get("folderId", "")).strip())
        remote = _google_upload(context, path, provider, {"name": path.name, "parents": [folder_id]}, token)
        # Read back size and parent so a successful job means the requested folder contains the complete file.
        check = _request("GET", f"https://www.googleapis.com/drive/v3/files/{remote['id']}?fields=id,size,parents,webViewLink&supportsAllDrives=true", token=token)
        if int(check.get("size", -1)) != path.stat().st_size or folder_id not in check.get("parents", []):
            raise PublishError("Drive could not verify the uploaded file size and folder.")
        delivery = {"id": remote["id"], "url": check.get("webViewLink", "https://drive.google.com/file/d/" + remote["id"] + "/view"),
                    "folderId": folder_id, "visibility": "Drive sharing unchanged"}
    elif provider == "youtube":
        privacy = options.get("privacy", "private")
        remote = _google_upload(context, path, provider, {
            "snippet": {"title": str(options.get("title") or path.stem)[:100], "description": str(options.get("description", ""))[:5000], "categoryId": "22"},
            "status": {"privacyStatus": privacy},
        }, token)
        delivery = {"id": remote["id"], "url": "https://www.youtube.com/watch?v=" + remote["id"],
                    "visibility": remote.get("status", {}).get("privacyStatus", privacy)}
    elif provider == "x":
        delivery = _x_upload(context, path, token, str(options.get("description", "")))
    else:
        delivery = _facebook_upload(context, path, token, options)
    return {**result, "delivery": {"provider": provider, **delivery}}


class _RenderProgress:
    def __init__(self, context):
        self.context = context

    def update(self, progress=None, message=None):
        self.context.update(None if progress is None else progress * .8, message)

    def write(self, line):
        self.context.write(line)


def render_and_publish(context, *, provider="local", delivery_options=None, **kwargs):
    from .editor import render
    result = render(context if provider == "local" else _RenderProgress(context), **kwargs)
    if provider == "local":
        return result
    try:
        return upload(context, result=result, provider=provider, options=delivery_options)
    except Exception as error:
        # Keep the rendered media in the job result for retry without rendering again.
        context.manager.update(context.job_id, result=result)
        raise PublishError(f"{error} Local export retained at {result['path']}. Use Retry upload in Activity.") from None


def retry_upload(context, *, result, provider, options):
    try:
        return upload(context, result=result, provider=provider, options=options)
    except Exception as error:
        context.manager.update(context.job_id, result=result)
        raise PublishError(f"{error} Local export retained at {result['path']}.") from None
