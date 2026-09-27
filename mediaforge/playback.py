"""Accurately indexed audio for browser playback, waveform windows and editing.

Raw MP3 seeking in browsers can use an approximate byte/time table. A long VBR
recording can then play seconds away from currentTime. MP4 stores timestamps
for every packet; copying the MP3 packets into it fixes seeking without a lossy
encode or a whole-recording PCM buffer. Originals always remain untouched.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
import threading
import uuid
from pathlib import Path

from .ffmpeg import probe
from .runtime import data_root

CACHE_ROOT = data_root() / ".cache" / "audio-index-v1"
_LOCKS = [threading.Lock() for _ in range(32)]
_SLOTS = threading.Semaphore(2)
_LOG = logging.getLogger(__name__)


def editing_source(path: str | Path, media: dict | None = None) -> Path:
    source = Path(path).expanduser().resolve()
    stat = source.stat()
    media = media if media is not None else probe(source)
    if media.get("format") != "mp3":
        return source
    fingerprint = f"{source}|{stat.st_size}|{stat.st_mtime_ns}"
    key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    target = CACHE_ROOT / f"{key}.mp4"
    with _LOCKS[int(key[:8], 16) % len(_LOCKS)]:
        if target.is_file() and target.stat().st_size:
            return target
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        temporary = CACHE_ROOT / f"{key}.{uuid.uuid4().hex}.partial"
        try:
            _LOG.info("Preparing packet-indexed audio: %s", source)
            with _SLOTS:
                result = subprocess.run(
                    ["ffmpeg", "-v", "error", "-nostdin", "-i", str(source),
                     "-map", "0:a:0", "-c:a", "copy", "-map_metadata", "-1",
                     "-movflags", "+faststart", "-f", "mp4", "-y", str(temporary)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            if result.returncode:
                raise RuntimeError("Could not prepare precise audio playback: " + result.stderr[-2000:])
            indexed = probe(temporary)
            if not indexed.get("audio") or indexed["audio"]["codec"] != "mp3":
                raise RuntimeError("Indexed audio validation failed")
            # Refuse to publish a cache made from a source modified during indexing.
            after = source.stat()
            if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError("Source changed while preparing audio. Please reopen it.")
            temporary.replace(target)
            _LOG.info("Packet-indexed audio ready: %s", target.name)
        finally:
            temporary.unlink(missing_ok=True)
    return target
