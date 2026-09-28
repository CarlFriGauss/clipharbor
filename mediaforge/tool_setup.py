"""First-run desktop media tools, fetched directly from the upstream distributor."""
import hashlib
import logging
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
from urllib.request import urlopen
import zipfile

from .runtime import data_root

RELEASE = "autobuild-2024-12-31-13-02"
URL = (f"https://github.com/BtbN/FFmpeg-Builds/releases/download/{RELEASE}/"
       "ffmpeg-N-118197-gbb85423142-win64-gpl.zip")
SHA256 = "147c66f8f123270693fcfceaaf5b3cd2aed3836637ce1f411153f83fbd5eeca3"
FILES = {
    "ffmpeg.exe": "256c95a113a4d222a487644e04aa535c313572994a2f78568662133e7d6d7b3a",
    "ffprobe.exe": "b4e85f27d83f615d2344f91e868caea5dabe2386524bf195eed35f2106166bbd",
}


def tool_directory():
    return data_root() / "tools" / RELEASE


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _digest(stream)


def _digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def ready():
    root = tool_directory()
    return all((root / name).is_file() and digest(root / name) == checksum
               for name, checksum in FILES.items())


def install(report, cancelled):
    """Verify archive and individual binaries; publish only a complete installation."""
    destination = tool_directory()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="setup-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        archive = stage / "download.zip"
        with urlopen(URL, timeout=30) as response, archive.open("wb") as output:
            total = int(response.headers.get("Content-Length", 0))
            received = 0
            while True:
                if cancelled.is_set():
                    raise InterruptedError("Setup cancelled. Open ClipHarbor again to retry.")
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                received += len(block)
                report(f"Downloading media tools: {received // 1048576} MB"
                       + (f" of {total // 1048576} MB" if total else ""))
        report("Checking downloaded files…")
        if digest(archive) != SHA256:
            raise RuntimeError("Download verification failed. Please try again.")
        with zipfile.ZipFile(archive) as source:
            for name, checksum in FILES.items():
                entries = [p for p in source.namelist() if p.endswith("/bin/" + name)]
                if len(entries) != 1:
                    raise RuntimeError("Unexpected media tool archive")
                with source.open(entries[0]) as input_file, (stage / name).open("wb") as output:
                    shutil.copyfileobj(input_file, output)
                if digest(stage / name) != checksum:
                    raise RuntimeError("Media tool verification failed")
            for entry in source.namelist():
                if entry.endswith("/LICENSE.txt"):
                    (stage / "LICENSE.txt").write_bytes(source.read(entry))
        if cancelled.is_set():
            raise InterruptedError("Setup cancelled. Open ClipHarbor again to retry.")
        destination.mkdir(exist_ok=True)
        for name in [*FILES, "LICENSE.txt"]:
            if (stage / name).exists():
                os.replace(stage / name, destination / name)


def ensure_media_tools(graphical=True):
    if ready():
        return
    if not graphical:
        install(lambda _: None, threading.Event())
        return
    import tkinter as tk
    from tkinter import ttk
    window = tk.Tk()
    window.title("ClipHarbor — First-time setup")
    window.geometry("520x210")
    window.resizable(False, False)
    ttk.Label(window, text="Getting ClipHarbor ready", font=("Segoe UI", 16)).pack(pady=(18, 8))
    ttk.Label(window, text="Downloading media tools from GitHub. This happens only once.\n"
              "Please stay connected to the internet.", justify="center").pack()
    status = tk.StringVar(value="Connecting…")
    ttk.Label(window, textvariable=status).pack(pady=10)
    progress = ttk.Progressbar(window, mode="indeterminate", length=450)
    progress.pack()
    progress.start()
    events = queue.Queue()
    cancelled = threading.Event()
    errors = []

    def work():
        try:
            install(lambda message: events.put(("status", message)), cancelled)
        except Exception as error:
            events.put(("error", error))
        finally:
            events.put(("done", None))

    def cancel():
        cancelled.set()
        status.set("Cancelling…")

    def poll():
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == "status" and not cancelled.is_set():
                status.set(value)
            elif kind == "error":
                errors.append(value)
            elif kind == "done":
                window.destroy()
                return
        window.after(100, poll)

    ttk.Button(window, text="Cancel", command=cancel).pack(pady=10)
    window.protocol("WM_DELETE_WINDOW", cancel)
    window.update_idletasks()
    logging.info("Graphical setup ready (Tcl=%s, Tk=%s)",
                 window.tk.call("package", "present", "Tcl"),
                 window.tk.call("package", "present", "Tk"))
    threading.Thread(target=work, daemon=True).start()
    window.after(100, poll)
    window.mainloop()
    if errors:
        raise errors[0]
