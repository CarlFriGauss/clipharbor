"""Exercise app.py with the runtime/tools provided by the terminal bootstrap."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="clipharbor-app-test-") as directory:
    root = Path(directory)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with (root / "server.log").open("w+") as log:
        process = subprocess.Popen([sys.executable, str(args.source / "app.py"), "--port", str(port)],
                                   env=dict(os.environ, CLIPHARBOR_DATA_DIR=str(root)), stdout=log, stderr=log)
        def api(path, payload=None):
            request = urllib.request.Request(base + path,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        try:
            for _ in range(120):
                try:
                    health = api("/api/health")
                    break
                except OSError:
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    time.sleep(.25)
            else:
                raise RuntimeError("App did not become ready")
            with urllib.request.urlopen(base, timeout=30) as response:
                assert b"ClipHarbor" in response.read()
            source = root / "input.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=160x90:d=1",
                            "-f", "lavfi", "-i", "sine=frequency=500:duration=1", "-c:v", "libx264",
                            "-c:a", "aac", "-shortest", str(source)], check=True, timeout=60)
            asset = api("/api/assets/register", {"assets": [{"id": "test", "path": str(source)}]})["assets"][0]
            assert api("/api/waveform/" + asset["token"])["samples"]
            job = api("/api/renders", {"project": {"assets": [{"id": "test", "path": str(source), "audio": True}],
                "clips": [{"assetId": "test", "kind": "video", "in": .1, "out": .8, "start": 0, "speed": 1}]},
                "outputDirectory": str(root), "filename": "cut", "outputFormat": "mp4"})
            for _ in range(240):
                result = api("/api/jobs/" + job["id"])
                if result["status"] not in ("queued", "running"):
                    break
                time.sleep(.25)
            assert result["status"] == "completed", result
            assert abs(result["result"]["media"]["duration"] - .7) < .1
            print("Bootstrapped app.py launch, page, waveform and MP4 export passed.")
        finally:
            process.terminate()
            process.wait(timeout=15)
