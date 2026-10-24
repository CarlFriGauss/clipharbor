"""Small native-messaging companion. Media work stays in the desktop process.

Only the packaged extension can call this protocol. Desktop session cookies and
Google tokens never cross the native-messaging boundary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

from .runtime import VERSION, RESOURCE_ROOT, data_root, downloads_directory

HOST_NAME = "com.clipharbor.downloader"
EXTENSION_ID = "nopjlekidanihaoahnpcnkacdpgljejl"
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
FACEBOOK_EXTENSION_ID = "ngiefopmfphpgkoipgnipbajpmjcimag"
FACEBOOK_ORIGIN = f"chrome-extension://{FACEBOOK_EXTENSION_ID}/"
FACEBOOK_ACTIONS = {"browserRegister", "browserPoll", "browserReport", "browserStatus"}
MAX_MESSAGE = 64 * 1024
FORMATS = {"mp4", "original", "mkv", "webm", "mov", "mp3", "m4a", "wav"}


class BridgeError(ValueError):
    pass


def media_url(value):
    if not isinstance(value, str) or len(value) > 16_384 or any(ord(c) < 32 for c in value):
        raise BridgeError("Choose a complete http:// or https:// video link.")
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        parsed.port  # Reject malformed ports before invoking a downloader.
    except ValueError:
        raise BridgeError("Choose a complete http:// or https:// video link without embedded credentials.") from None
    return value.strip()


def settings():
    result = {"destination": "local", "outputFormat": "mp4", "outputDirectory": str(downloads_directory()), "xCompatible": False}
    try:
        saved = json.loads((data_root() / "browser-downloads.json").read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            return result
        if isinstance(saved.get("destination"), str) and saved["destination"] in {"local", "drive"}:
            result["destination"] = saved["destination"]
        if isinstance(saved.get("outputFormat"), str) and saved["outputFormat"] in FORMATS:
            result["outputFormat"] = saved["outputFormat"]
        if isinstance(saved.get("outputDirectory"), str) and 0 < len(saved["outputDirectory"]) < 4096 and not any(ord(c) < 32 for c in saved["outputDirectory"]):
            result["outputDirectory"] = saved["outputDirectory"]
        result["xCompatible"] = saved.get("xCompatible") is True
    except (OSError, ValueError, AttributeError):
        pass
    return result


def save_settings(value):
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".browser-downloads-{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(root / "browser-downloads.json")
    finally:
        temporary.unlink(missing_ok=True)


class DesktopClient:
    def __init__(self, info):
        port, token = info.get("port"), info.get("token")
        if type(port) is not int or not 0 < port < 65536 or not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", token):
            raise BridgeError("ClipHarbor's local session is unavailable. Open the app and retry.")
        self.base = f"http://127.0.0.1:{port}"
        self.token = token
        # Always bypass proxy settings for this local connection.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(self, path, payload=None, timeout=15):
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base + path, data=body, headers={
            "Content-Type": "application/json", "Cookie": "clipharbor-session=" + self.token,
        })
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                message = json.load(error).get("error")
            except (ValueError, AttributeError):
                message = None
            raise BridgeError(message or f"ClipHarbor could not complete the request ({error.code}).") from None

    def verify(self):
        health = self.api("/api/health", timeout=2)
        if health.get("instance") != self.token or not health.get("desktop"):
            raise BridgeError("Waiting for the ClipHarbor desktop engine.")
        return health


def running_client():
    try:
        info = json.loads((data_root() / "instance.json").read_text(encoding="utf-8"))
        client = DesktopClient(info)
        health = client.verify()
        return client, health
    except (OSError, ValueError, KeyError):
        return None


def ensure_desktop():
    running = running_client()
    if running:
        return running
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).with_name("ClipHarbor.exe")
        command = [str(executable), "--no-browser", "--setup-ui"]
    else:
        command = [sys.executable, str(RESOURCE_ROOT / "desktop.py"), "--no-browser"]
    # Detach from the short-lived messaging host and its stdin/stdout pipes.
    process = subprocess.Popen(command, cwd=str(RESOURCE_ROOT), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        running = running_client()
        if running:
            return running
        if process.poll() not in (None, 0):
            break
        time.sleep(.15)
    raise BridgeError("ClipHarbor is still starting or needs first-time setup. Open ClipHarbor, finish setup, then try again.")


def job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise BridgeError("This download is no longer available.")
    return value


def public_job(job):
    result = job.get("result") or {}
    delivery = result.get("delivery") or {}
    return {key: job.get(key) for key in ("id", "status", "progress", "message", "error")} | {
        "name": (result.get("media") or {}).get("name", ""),
        "path": result.get("path") if not result.get("cloudDownloadId") else None,
        "driveUrl": delivery.get("url") if delivery.get("provider") == "drive" else None,
    }


def handle(message):
    if not isinstance(message, dict) or message.get("protocol") != 1:
        raise BridgeError("Update the ClipHarbor extension and desktop app together.")
    action = message.get("action")
    if action not in {"status", "download", "job", "open", "chooseFolder", "chooseDriveFolder", "reveal", *FACEBOOK_ACTIONS}:
        raise BridgeError("Unknown extension action.")
    # Validate before starting a process or touching a website.
    if action == "download":
        url = media_url(message.get("url"))
        if message.get("destination") not in {"local", "drive"} or message.get("outputFormat") not in FORMATS:
            raise BridgeError("Choose a supported format and destination.")
    if action in {"job", "reveal"}:
        identifier = job_id(message.get("jobId"))
    if action in {"browserPoll", "browserReport"}:
        running = running_client()
        if not running:
            if action == "browserPoll":
                return {"task": None}
            raise BridgeError("ClipHarbor closed. The browser task must stop; check Facebook before retrying.")
        client, health = running
    else:
        client, health = ensure_desktop()
    try:
        compatible = tuple(int(part) for part in health["version"].split(".")) >= (0, 8, 0)
    except (KeyError, ValueError, AttributeError):
        compatible = False
    if not compatible:
        raise BridgeError("Quit the older ClipHarbor app, install version 0.8.0 or newer, then try again.")
    if action == "status":
        drive = client.api("/api/connections")["drive"]
        return {"version": health["version"], "settings": settings(),
                "drive": {key: drive[key] for key in ("connected", "needsReconnect", "folderName")}}
    if action == "download":
        prefs = settings() | {"destination": message["destination"], "outputFormat": message["outputFormat"],
                              "xCompatible": message.get("xCompatible") is True}
        job = client.api("/api/downloads", {"url": url, **prefs,
            "deliveryOptions": {}, "xCompatible": prefs["outputFormat"] == "mp4" and prefs["xCompatible"]})
        save_settings(prefs)
        return {"job": public_job(job)}
    if action == "job":
        return {"job": public_job(client.api("/api/jobs/" + identifier))}
    if action == "chooseFolder":
        paths = client.api("/api/dialog/folder", {}, timeout=300).get("paths", [])
        prefs = settings()
        if paths:
            prefs["outputDirectory"] = paths[0]
            save_settings(prefs)
        return {"settings": prefs}
    if action == "chooseDriveFolder":
        return {"job": public_job(client.api("/api/connections/drive/folder-picker", {}))}
    if action == "browserRegister":
        return {"facebook": client.api("/api/browser/facebook/register", {key: message.get(key) for key in ("browserId", "profileUrl", "name")})}
    if action == "browserStatus":
        return {"facebook": client.api("/api/browser/facebook")}
    if action == "browserPoll":
        return client.api("/api/browser/facebook/poll", {"browserId": message.get("browserId")})
    if action == "browserReport":
        return client.api("/api/browser/facebook/report", {key: message.get(key) for key in ("browserId", "taskId", "lease", "phase", "message", "url")})
    if action == "reveal":
        result = client.api("/api/jobs/" + identifier).get("result") or {}
        token = result.get("token", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", token) or result.get("cloudDownloadId"):
            raise BridgeError("This local file is unavailable. Open Activity in ClipHarbor for details.")
        client.api("/api/reveal/" + token, {})
        return {}
    target = message.get("view", "activity")
    if target not in {"activity", "download", "drive"}:
        raise BridgeError("Unknown ClipHarbor view.")
    if not webbrowser.open(client.base + "/launch/" + client.token + "?view=" + target):
        raise BridgeError("Open ClipHarbor using its desktop shortcut.")
    return {}


def read_message(stream):
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise BridgeError("Incomplete extension message.")
    length = struct.unpack("=I", header)[0]
    if not 0 < length <= MAX_MESSAGE:
        raise BridgeError("Extension message is too large.")
    body = bytearray()
    while len(body) < length:
        chunk = stream.read(length - len(body))
        if not chunk:
            raise BridgeError("Incomplete extension message.")
        body.extend(chunk)
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise BridgeError("Invalid extension message.") from None
    return value


def write_message(stream, value):
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_MESSAGE:
        body = json.dumps({"ok": False, "error": "Response is too large. Open Activity in ClipHarbor."}).encode()
    stream.write(struct.pack("=I", len(body)) + body)
    stream.flush()


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {EXTENSION_ORIGIN, FACEBOOK_ORIGIN}:
        return 1
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    input_stream, output_stream = sys.stdin.buffer, sys.stdout.buffer
    while True:
        try:
            message = read_message(input_stream)
            if message is None:
                return 0
        except BridgeError as error:
            write_message(output_stream, {"ok": False, "error": str(error)})
            return 1
        try:
            if isinstance(message, dict) and ((message.get("action") in FACEBOOK_ACTIONS) != (sys.argv[1] == FACEBOOK_ORIGIN)):
                raise BridgeError("This extension is not allowed to perform that action.")
            response = {"ok": True, **handle(message)}
        except BridgeError as error:
            response = {"ok": False, "error": str(error)}
        except Exception:
            # Do not send raw exceptions, session secrets, or tracebacks into the browser.
            response = {"ok": False, "error": "ClipHarbor could not complete this request. Open the app and retry; see its local log if needed."}
        write_message(output_stream, response)


if __name__ == "__main__":
    raise SystemExit(main())
