from __future__ import annotations

import array
import math
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any


from .ffmpeg import probe
from .playback import editing_source

_CACHE: dict[tuple, dict[str, Any]] = {}
_CACHE_LOCK = threading.RLock()
_DECODE_SLOTS = threading.Semaphore(2)


def extract_waveform(path: str | Path, samples: int = 120_000,
                     start: float = 0, duration: float | None = None) -> dict[str, Any]:
    """Stream a peak envelope with exact time bins and optional detail windows."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Media file not found: {source}")
    start = float(start)
    if not math.isfinite(start) or start < 0:
        raise ValueError("Waveform start must be a nonnegative time")
    length = float(duration) if duration is not None else max(0, probe(source)["duration"] - start)
    if not math.isfinite(length) or length <= 0:
        raise ValueError("Waveform duration must be positive")
    samples = max(256, min(200_000, int(samples)))
    stat = source.stat()
    key = (str(source), stat.st_mtime_ns, stat.st_size, samples, start, length)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    # The same packet index is used for playback, detailed windows and export.
    decoded_source = editing_source(source)

    rate, channels = 48_000, 2
    preroll = min(start, .25)
    bin_frames = max(1, math.ceil(length * rate / samples))
    bin_bytes = bin_frames * channels * 2
    peaks: list[float] = []
    # Preserve both channels instead of cancelling opposite-phase stereo by
    # downmixing. Reduce PCM immediately; never hold a whole recording in RAM.
    with _DECODE_SLOTS, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-ss", str(start-preroll), "-i", str(decoded_source),
             "-ss", str(preroll), "-t", str(length), "-map", "0:a:0", "-ac", str(channels),
             "-ar", str(rate), "-f", "s16le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=errors,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            assert process.stdout is not None
            while block := process.stdout.read(bin_bytes):
                pcm = array.array("h")
                pcm.frombytes(block[:len(block) // 2 * 2])
                if sys.byteorder != "little":
                    pcm.byteswap()
                peaks.append(max(abs(min(pcm, default=0)), abs(max(pcm, default=0))) / 32768.0)
            if process.wait():
                errors.seek(0)
                raise RuntimeError(errors.read().decode("utf-8", errors="replace") or "Could not read audio")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()

    highest = max(peaks, default=0.0)
    result = {"sampleRate": rate, "start": start, "binDuration": bin_frames / rate,
              "duration": length, "samples": [round(v / highest, 5) if highest else 0 for v in peaks],
              "peak": highest}

    with _CACHE_LOCK:
        if len(_CACHE) >= 12:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = result
    return result
