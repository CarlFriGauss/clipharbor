from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import webbrowser

from .runtime import VERSION, configure_tools, data_root


class InstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def acquire(self) -> bool:
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            self.file.close()
            self.file = None
            return False

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def show_error(message: str) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "ClipHarbor", 0x10)
    elif sys.stderr:
        print(message, file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="ClipHarbor desktop launcher")
    parser.add_argument("--no-browser", action="store_true", help="Diagnostics only")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
        logs / "clipharbor.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")])
    lock = InstanceLock(root / "instance.lock")
    info_path = root / "instance.json"
    if not lock.acquire():
        for _ in range(100):
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
                # Fixed localhost construction: never open an arbitrary URL from disk.
                url = f"http://127.0.0.1:{int(info['port'])}/launch/{info['token']}"
                from urllib.request import urlopen
                with urlopen(f"http://127.0.0.1:{int(info['port'])}/api/health", timeout=.5) as response:
                    if json.load(response).get("instance") != info["token"]:
                        raise ValueError("Waiting for this instance")
                if not args.no_browser:
                    webbrowser.open(url)
                return 0
            except (OSError, ValueError, KeyError):
                time.sleep(.1)
        if not args.no_browser:
            show_error("ClipHarbor is already starting. Please wait, then open it again.")
        return 1
    server = None
    try:
        from .tool_setup import ensure_media_tools
        ensure_media_tools(graphical=not args.no_browser)
        configure_tools()
        from .ffmpeg import require_tools
        require_tools()
        from .web import create_app
        from waitress import create_server
        stop = threading.Event()
        token = secrets.token_urlsafe(32)
        app = create_app()
        app.config.update(DESKTOP_TOKEN=token, SHUTDOWN_CALLBACK=stop.set)
        try:
            server = create_server(app, host="127.0.0.1", port=args.port, threads=8)
        except OSError:
            if args.port == 0:
                raise
            server = create_server(app, host="127.0.0.1", port=0, threads=8)
        port = int(server.effective_port)
        app.config["DESKTOP_PORT"] = port
        info = {"port": port, "token": token, "pid": os.getpid(), "version": VERSION}
        temporary = info_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(info), encoding="utf-8")
        temporary.replace(info_path)
        thread = threading.Thread(target=server.run, name="clipharbor-http", daemon=True)
        thread.start()
        logging.info("ClipHarbor %s listening on localhost:%s", VERSION, port)
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/launch/{token}")
        while not stop.wait(.5):
            if not thread.is_alive():
                raise RuntimeError("The local server stopped unexpectedly")
        logging.info("Clean shutdown requested")
        return 0
    except Exception as error:
        logging.exception("ClipHarbor startup failed")
        if not args.no_browser:
            show_error(f"ClipHarbor could not start.\n\n{error}\n\nOpen the app again to retry.\nDetails: {logs / 'clipharbor.log'}")
        return 1
    finally:
        if server:
            server.close()
            server.task_dispatcher.shutdown(timeout=10)
        info_path.unlink(missing_ok=True)
        lock.close()
