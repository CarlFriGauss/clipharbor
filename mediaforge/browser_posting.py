"""Explicit Facebook export tasks for the user's optional browser companion.

No browser cookies or passwords enter the desktop app. A task is claimed once;
an interrupted publication is never automatically retried.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit, parse_qs, urlencode

from .runtime import data_root

AUDIENCES = {"only_me": "Only me", "friends": "Friends", "public": "Public"}


class BrowserPostingError(ValueError):
    def __init__(self, message, *, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def profile_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Open your own Facebook profile and connect the extension there.")
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.netloc != "www.facebook.com":
        raise ValueError("Use your own www.facebook.com profile.")
    path = parts.path.rstrip("/")
    if path == "/profile.php":
        identifier = parse_qs(parts.query).get("id", [""])[0]
        if not identifier.isascii() or not identifier.isdigit():
            raise ValueError("Open your own Facebook profile first.")
        return "https://www.facebook.com/profile.php?" + urlencode({"id": identifier})
    if not re.fullmatch(r"/[A-Za-z0-9.]{2,100}", path) or path.lower() in {
        "/login", "/checkpoint", "/reel", "/reels", "/watch", "/groups", "/pages", "/marketplace", "/settings", "/help", "/share", "/friends", "/gaming"}:
        raise ValueError("Open your own Facebook profile, rather than the feed or a video.")
    return "https://www.facebook.com" + path


def browser_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Reconnect the Facebook browser companion.")
    return value


class FacebookTasks:
    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.last_seen = {}
        self.tasks = {}

    def config(self):
        try:
            value = json.loads((data_root() / "browser-posting.json").read_text(encoding="utf-8"))
            browser_id(value["browserId"])
            value["profileUrl"] = profile_url(value["profileUrl"])
            if not isinstance(value["name"], str) or not 0 < len(value["name"]) <= 120:
                raise ValueError
            return value
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def register(self, identifier, url, name):
        identifier, url = browser_id(identifier), profile_url(url)
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 120 or any(ord(c) < 32 for c in name):
            raise ValueError("The profile name could not be verified. Open your own Facebook profile and retry.")
        with self.condition:
            if any(task["state"] in {"queued", "claimed", "posting"} for task in self.tasks.values()):
                raise ValueError("Finish the active Facebook export before changing its browser connection.")
            root = data_root()
            root.mkdir(parents=True, exist_ok=True)
            temporary = root / ".browser-posting.tmp"
            temporary.write_text(json.dumps({"browserId": identifier, "profileUrl": url, "name": name.strip()}), encoding="utf-8")
            temporary.replace(root / "browser-posting.json")
            self.last_seen[identifier] = time.monotonic()
        return self.status()

    def status(self):
        with self.condition:
            value = self.config()
            return {"configured": bool(value), "ready": bool(value) and time.monotonic() - self.last_seen.get(value.get("browserId"), -1000) < 90,
                    "name": value.get("name", ""), "profileUrl": value.get("profileUrl", "")}

    def require_ready(self):
        if not self.status()["ready"]:
            raise BrowserPostingError("Enable Facebook posting in the ClipHarbor extension from your own Facebook profile, then keep that browser open.")

    def poll(self, identifier):
        identifier = browser_id(identifier)
        with self.condition:
            config = self.config()
            if identifier != config.get("browserId"):
                return None
            self.last_seen[identifier] = time.monotonic()
            for task in self.tasks.values():
                if task["state"] == "queued":
                    task.update(state="claimed", seen=time.monotonic(), lease=secrets.token_urlsafe(24))
                    return {key: task[key] for key in ("id", "lease", "path", "caption", "audience", "profileUrl", "name")}
        return None

    def update(self, identifier, task_id, lease, phase, *, message="", url=""):
        identifier = browser_id(identifier)
        with self.condition:
            task = self.tasks.get(task_id)
            if not task or task["browserId"] != identifier or not isinstance(lease, str) or not secrets.compare_digest(task.get("lease", ""), lease):
                raise ValueError("This browser task is no longer available.")
            if task["state"] not in {"claimed", "posting"}:
                raise ValueError("This browser task already finished. It will not be posted again.")
            if phase not in {"working", "audience_verified", "posting", "completed", "failed"}:
                raise ValueError("Unknown browser task phase.")
            task["seen"] = time.monotonic()
            if phase == "audience_verified":
                task["audienceVerified"] = True
            if phase == "posting":
                if not task.get("audienceVerified"):
                    raise ValueError("The requested audience must be verified before posting.")
                task["state"] = "posting"
            if phase == "completed":
                if task["state"] != "posting":
                    raise ValueError("Facebook has not confirmed this publication.")
                parts = urlsplit(url)
                if parts.scheme != "https" or parts.netloc != "www.facebook.com" or len(url) > 2048:
                    raise ValueError("Facebook did not provide a valid result link.")
                task.update(state="completed", url=url)
            if phase == "failed":
                task["uncertain"] = task["state"] == "posting"
                task["state"] = "failed"
            task["message"] = str(message)[:1000]
            self.condition.notify_all()

    def run(self, context, result, options):
        self.require_ready()
        config = self.config()
        audience = options.get("audience", "only_me")
        if audience not in AUDIENCES:
            raise ValueError("Choose a Facebook audience.")
        path = Path(result["path"]).resolve()
        if not path.is_file() or path.suffix.lower() != ".mp4":
            raise ValueError("Facebook browser posting needs a completed local MP4.")
        identifier = secrets.token_hex(16)
        now = time.monotonic()
        task = {"id": identifier, "state": "queued", "browserId": config["browserId"], "profileUrl": config["profileUrl"],
                "name": config["name"], "path": str(path), "caption": str(options.get("description", ""))[:5000],
                "audience": audience, "created": now, "seen": now, "message": "Waiting for the browser extension"}
        with self.condition:
            # Avoid two tabs publishing concurrently to the same Facebook session.
            if any(item["state"] in {"queued", "claimed", "posting"} for item in self.tasks.values()):
                raise BrowserPostingError("Another Facebook export is still active. Wait for it to finish.")
            self.tasks[identifier] = task
            try:
                while task["state"] not in {"completed", "failed"}:
                    now = time.monotonic()
                    if (task["state"] == "queued" and now - task["created"] > 90) or now - task["seen"] > 120 or now - task["created"] > 1800:
                        task.update(uncertain=task["state"] == "posting", state="failed", message="The Facebook browser task stopped responding.")
                        break
                    context.update(98 if task["state"] == "posting" else 90, task["message"] or "Posting through your browser")
                    self.condition.wait(.5)
                if task["state"] != "completed":
                    uncertain = bool(task.get("uncertain"))
                    suffix = " Facebook may have posted it. Check your profile before trying again." if uncertain else " Your local video was kept; no automatic retry will be made."
                    raise BrowserPostingError(task["message"] + suffix, uncertain=uncertain)
                return {**result, "delivery": {"provider": "facebook_browser", "url": task["url"], "visibility": AUDIENCES[audience]}}
            finally:
                self.tasks.pop(identifier, None)


facebook_tasks = FacebookTasks()
