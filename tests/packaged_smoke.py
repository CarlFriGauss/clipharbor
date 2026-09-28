"""Run a frozen build with no developer tools on PATH; do not touch user data."""
import argparse
import http.cookiejar
import http.server
import functools
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import threading
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--graphical-setup", action="store_true")
    args = parser.parse_args()
    exe = args.executable.resolve()
    with tempfile.TemporaryDirectory(prefix="clipharbor-smoke-") as temporary:
        root = Path(temporary)
        env = dict(os.environ, CLIPHARBOR_DATA_DIR=str(root),
                   PATH=str(Path(os.environ["SystemRoot"]) / "System32"))
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        command = [str(exe), "--no-browser", "--port", "0"]
        if args.graphical_setup:
            command.append("--setup-ui")
        process = subprocess.Popen(command, env=env,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for _ in range(1200):
                if (root / "instance.json").is_file():
                    break
                if process.poll() is not None:
                    raise RuntimeError((root / "logs/clipharbor.log").read_text())
                time.sleep(.5)
            info = json.loads((root / "instance.json").read_text())
            gui_runtime = None
            if args.graphical_setup:
                gui_runtime = next((line for line in (root / "logs/clipharbor.log").read_text().splitlines()
                                    if "Graphical setup ready (Tcl=" in line), None)
                assert gui_runtime, "Graphical setup was not exercised"
            base = f"http://127.0.0.1:{info['port']}"
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def api(path, data=None):
                payload = json.dumps(data).encode() if data is not None else None
                request = urllib.request.Request(base+path, data=payload, headers={"Content-Type": "application/json"})
                with opener.open(request, timeout=60) as response:
                    return json.load(response)
            with opener.open(base+"/launch/"+info["token"]) as response:
                assert b"ClipHarbor" in response.read()
            assert api("/api/health")["desktop"] is True
            # Second launch must reuse the running app, not create a second server.
            subprocess.run([str(exe), "--no-browser"], env=env, check=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert json.loads((root/"instance.json").read_text())["pid"] == process.pid
            saved = api("/api/projects", {"name": "Installer smoke", "project": {"assets": [], "clips": []}})
            assert api("/api/projects/"+saved["id"])["name"] == "Installer smoke"
            tools = exe.parent / "_internal/tools"
            assert not (tools / "ffmpeg.exe").exists(), "Do not redistribute the upstream binary"
            media_tools = root / "tools" / "autobuild-2024-12-31-13-02"
            media = root / "test.wav"
            subprocess.run([str(media_tools/"ffmpeg.exe"), "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=500:duration=1", str(media)], env=env, check=True)
            asset = api("/api/assets/register", {"assets": [{"id": "test", "path": str(media)}]})["assets"][0]
            assert api("/api/waveform/"+asset["token"])["samples"]
            job = api("/api/renders", {"project": {"assets": [{"id": "test", "path": str(media), "audio": True}],
                          "clips": [{"assetId": "test", "kind": "audio", "in": .1, "out": .8, "start": 0, "speed": 1}]},
                          "outputDirectory": str(root), "filename": "test-cut", "outputFormat": "mp3"})
            for _ in range(100):
                status = api("/api/jobs/"+job["id"])
                if status["status"] not in ("queued", "running"):
                    break
                time.sleep(.1)
            assert status["status"] == "completed", status
            assert abs(status["result"]["media"]["duration"]-.7) < .08
            # Exercise yt-dlp and postprocessing from a local media URL, without
            # relying on a changing third-party service or anyone's cookies.
            source_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root)))
            serving = threading.Thread(target=source_server.serve_forever, daemon=True)
            serving.start()
            try:
                url = f"http://127.0.0.1:{source_server.server_port}/test.wav"
                inspected = api("/api/inspect-url", {"url": url})
                assert inspected["title"] and inspected["webpageUrl"] == url
                download = api("/api/downloads", {"url": url, "outputDirectory": str(root/"downloads"), "outputFormat": "mp3"})
                for _ in range(200):
                    downloaded = api("/api/jobs/"+download["id"])
                    if downloaded["status"] not in ("queued", "running"):
                        break
                    time.sleep(.1)
                assert downloaded["status"] == "completed", downloaded
            finally:
                source_server.shutdown()
                source_server.server_close()
            assert subprocess.check_output([str(tools/"node.exe"), "--version"], env=env).startswith(b"v22")
            api("/api/desktop/quit", {})
            assert process.wait(timeout=20) == 0
            assert (root/"projects"/f"{saved['id']}.json").is_file()
            print(json.dumps({"ok": True, "version": info["version"], "export": status["result"]["media"]["duration"],
                              "graphical_setup": args.graphical_setup,
                              "gui_runtime": gui_runtime,
                              "checks": ["isolated PATH", "authenticated launch", "single instance", "save/open project",
                                         "first-run media tools", "waveform", "MP3 export", "inspect/download", "bundled Node", "clean quit"]}))
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
