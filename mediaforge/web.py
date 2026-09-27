from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file, redirect, g
from werkzeug.exceptions import HTTPException

from .downloader import download, inspect_url
from .editor import render
from .ffmpeg import probe, require_tools, x_compatibility
from .jobs import jobs
from .projects import ProjectStore
from .waveform import extract_waveform
from .playback import editing_source
from .runtime import RESOURCE_ROOT, VERSION, data_root, downloads_directory


ROOT = RESOURCE_ROOT


class MediaRegistry:
    def __init__(self) -> None:
        self._paths: dict[str, Path] = {}
        self._lock = threading.RLock()

    def add(self, path: str | Path) -> str:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"File not found: {resolved}")
        with self._lock:
            existing = next((token for token, item in self._paths.items() if item == resolved), None)
            if existing:
                return existing
            token = secrets.token_urlsafe(24)
            self._paths[token] = resolved
            return token

    def get(self, token: str) -> Path | None:
        with self._lock:
            return self._paths.get(token)


registry = MediaRegistry()
projects = ProjectStore(data_root() / "projects")


def _json() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required")
    return data


def _dialog(kind: str) -> list[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("Native file dialogs are not available in this Python installation") from exc
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if kind == "folder":
            selected = filedialog.askdirectory(title="Choose output folder", mustexist=True)
            return [selected] if selected else []
        if kind == "cookies":
            selected = filedialog.askopenfilename(
                title="Choose Netscape cookies file",
                filetypes=[("Cookie text files", "*.txt"), ("All files", "*.*")],
            )
            return [selected] if selected else []
        selected = filedialog.askopenfilenames(
            title="Choose media files",
            filetypes=[
                ("Media", "*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.mp3 *.m4a *.wav *.flac *.aac *.ogg *.opus"),
                ("All files", "*.*"),
            ],
        )
        return list(selected)
    finally:
        root.destroy()


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    lifecycle_lock = threading.RLock()
    active_requests = 0
    closing = False

    @app.before_request
    def protect_desktop():
        nonlocal active_requests
        token = app.config.get("DESKTOP_TOKEN")
        if not token:
            return None
        expected = f"127.0.0.1:{app.config['DESKTOP_PORT']}"
        if request.host != expected or request.headers.get("Origin", f"http://{expected}") != f"http://{expected}":
            return jsonify({"error": "Only the local ClipHarbor window may access this app"}), 403
        if request.endpoint not in {"launch_desktop", "health", "static"}:
            if not secrets.compare_digest(request.cookies.get("clipharbor-session", ""), token):
                return jsonify({"error": "Open ClipHarbor using its desktop shortcut"}), 401
        if request.endpoint in {"waveform", "prepare_playback", "inspect", "dialog"}:
            with lifecycle_lock:
                if closing:
                    return jsonify({"error": "ClipHarbor is closing"}), 503
                active_requests += 1
                g.counted_request = True

    @app.teardown_request
    def release_desktop_request(error):
        nonlocal active_requests
        if getattr(g, "counted_request", False):
            with lifecycle_lock:
                active_requests -= 1

    @app.get("/launch/<token>")
    def launch_desktop(token):
        expected = app.config.get("DESKTOP_TOKEN", "")
        if not expected or not secrets.compare_digest(token, expected):
            return jsonify({"error": "This launch link has expired. Use the desktop shortcut."}), 403
        response = redirect("/")
        response.set_cookie("clipharbor-session", expected, httponly=True, samesite="Strict")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.post("/api/desktop/quit")
    def quit_desktop():
        nonlocal closing
        callback = app.config.get("SHUTDOWN_CALLBACK")
        if not callback:
            return jsonify({"error": "Stop the development server in its terminal"}), 400
        with lifecycle_lock:
            if active_requests or not jobs.begin_shutdown():
                return jsonify({"error": "Work is still running. Wait for downloads, exports, audio preparation and dialogs to finish, then quit."}), 409
            closing = True
        threading.Timer(.5, callback).start()
        return jsonify({"ok": True})

    @app.errorhandler(Exception)
    def handle_error(error: Exception):
        if isinstance(error, HTTPException):
            return jsonify({"error": error.description}), error.code
        app.logger.exception("Request failed: %s %s", request.method, request.path)
        return jsonify({"error": str(error)}), 400

    @app.get("/")
    def index():
        return render_template("index.html"), {"Cache-Control": "no-cache"}

    @app.get("/api/health")
    def health():
        require_tools()
        downloads = downloads_directory()
        return jsonify({
            "ok": True,
            "defaultOutput": str(downloads if downloads.exists() else Path.home()),
            "version": VERSION,
            "desktop": bool(app.config.get("DESKTOP_TOKEN")),
            "instance": app.config.get("DESKTOP_TOKEN"),
        })

    @app.post("/api/dialog/<kind>")
    def dialog(kind: str):
        if kind not in {"folder", "files", "cookies"}:
            raise ValueError("Unknown dialog type")
        paths = _dialog(kind)
        if kind != "files":
            return jsonify({"paths": paths})
        assets = []
        for raw_path in paths:
            path = Path(raw_path).resolve()
            media = probe(path)
            token = registry.add(path)
            media["xCompatibility"] = x_compatibility(media) if media.get("video") else None
            assets.append({"id": secrets.token_hex(8), "path": str(path), "token": token, "media": media})
        return jsonify({"paths": paths, "assets": assets})

    @app.post("/api/inspect-url")
    def inspect():
        data = _json()
        return jsonify(inspect_url(str(data.get("url", "")).strip(), data.get("cookieFile") or None))

    @app.post("/api/assets/register")
    def register_assets():
        data = _json()
        restored = []
        for item in data.get("assets") or []:
            path = Path(str(item.get("path", ""))).expanduser().resolve()
            if not path.is_file():
                continue
            media = probe(path)
            media["xCompatibility"] = x_compatibility(media) if media.get("video") else None
            restored.append({
                "id": str(item.get("id") or secrets.token_hex(8)),
                "path": str(path),
                "token": registry.add(path),
                "media": media,
            })
        return jsonify({"assets": restored})

    @app.get("/api/projects")
    def list_projects():
        return jsonify({"projects": projects.list()})

    @app.post("/api/projects")
    def save_project():
        data = _json()
        saved = projects.save(
            name=str(data.get("name", "")),
            project=data.get("project") or {},
            project_id=str(data["id"]) if data.get("id") else None,
        )
        return jsonify(saved)

    @app.get("/api/projects/<project_id>")
    def get_project(project_id: str):
        return jsonify(projects.get(project_id))

    @app.delete("/api/projects/<project_id>")
    def delete_project(project_id: str):
        projects.delete(project_id)
        return jsonify({"ok": True})

    @app.post("/api/downloads")
    def start_download():
        data = _json()
        job = jobs.start(
            "download",
            download,
            url=str(data.get("url", "")).strip(),
            output_directory=str(data.get("outputDirectory", "")).strip(),
            output_format=str(data.get("outputFormat", "original")),
            x_compatible=bool(data.get("xCompatible", False)),
            audio_format_id=str(data.get("audioFormatId")) if data.get("audioFormatId") else None,
            audio_track_label=str(data.get("audioTrackLabel")) if data.get("audioTrackLabel") else None,
            cookie_file=data.get("cookieFile") or None,
            register=registry.add,
        )
        return jsonify(job.public()), 202

    @app.post("/api/renders")
    def start_render():
        data = _json()
        job = jobs.start(
            "render",
            render,
            project=data.get("project") or {},
            output_directory=str(data.get("outputDirectory", "")).strip(),
            filename=str(data.get("filename", "ClipHarbor export")),
            output_format=str(data.get("outputFormat", "mp4")),
            save_project=bool(data.get("saveProject", False)),
            register=registry.add,
        )
        return jsonify(job.public()), 202

    @app.get("/api/waveform/<token>")
    def waveform(token: str):
        path = registry.get(token)
        if not path or not path.is_file():
            return jsonify({"error": "Media is no longer available"}), 404
        samples = request.args.get("samples", default=120_000, type=int)
        start = request.args.get("start", default=0, type=float)
        duration = request.args.get("duration", default=None, type=float)
        return jsonify(extract_waveform(path, samples, start, duration))

    @app.post("/api/playback/<token>")
    def prepare_playback(token: str):
        path = registry.get(token)
        if not path or not path.is_file():
            return jsonify({"error": "Media is no longer available"}), 404
        prepared = editing_source(path)
        return jsonify({"url": f"/api/media/{registry.add(prepared)}", "indexed": prepared != path})

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id: str):
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job.public())

    @app.get("/api/media/<token>")
    def media(token: str):
        path = registry.get(token)
        if not path or not path.is_file():
            return jsonify({"error": "Media is no longer available"}), 404
        return send_file(path, conditional=True, as_attachment=False, download_name=path.name)

    @app.post("/api/reveal/<token>")
    def reveal_media(token: str):
        path = registry.get(token)
        if not path or not path.is_file():
            return jsonify({"error": "Media is no longer available"}), 404
        if sys.platform == "win32":
            command = ["explorer.exe", str(path.parent)]
        elif sys.platform == "darwin":
            command = ["open", str(path.parent)]
        else:
            command = ["xdg-open", str(path.parent)]
        subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return jsonify({"ok": True, "folder": str(path.parent)})

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local ClipHarbor application")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the app in the default browser")
    args = parser.parse_args()
    require_tools()
    if args.open:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
    create_app().run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
    return 0
