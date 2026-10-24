"""Run a frozen build with no developer tools on PATH; do not touch user data."""
import argparse
import http.cookiejar
import http.server
import functools
import json
import os
from pathlib import Path
import subprocess
import struct
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
            bridge_exe = exe.with_name("ClipHarborBridge.exe")
            assert bridge_exe.is_file()
            def extension(action, **fields):
                payload = json.dumps({"protocol": 1, "action": action, **fields}).encode()
                response = subprocess.run([str(bridge_exe), "chrome-extension://nopjlekidanihaoahnpcnkacdpgljejl/"],
                    input=struct.pack("=I", len(payload)) + payload, capture_output=True, env=env, check=True, timeout=65,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
                length = struct.unpack("=I", response[:4])[0]
                assert len(response) == 4 + length, "Native stdio contains extra data"
                value = json.loads(response[4:])
                assert value["ok"], value
                assert info["token"] not in response.decode(errors="replace"), "Desktop session must stay out of the extension"
                return value
            with opener.open(base+"/launch/"+info["token"]) as response:
                assert b"ClipHarbor" in response.read()
            assert api("/api/health")["desktop"] is True
            # A packaged build includes the publisher registration, never the
            # publisher's signed-in account. Both feature panels start signed out
            # with an isolated per-user data directory.
            accounts = api("/api/connections")
            assert not any(account["connected"] for account in accounts.values())
            google_registration = exe.parent / "_internal/google-oauth-client.json"
            assert accounts["drive"]["googleConfigured"] == google_registration.is_file()
            assert accounts["youtube"]["googleConfigured"] == google_registration.is_file()
            if google_registration.is_file():
                registration = json.loads(google_registration.read_text(encoding="utf-8"))
                assert set(registration) == {"installed"}
                assert set(registration["installed"]) <= {"client_id", "client_secret"}
                assert registration["installed"]["client_id"]
            assert not (exe.parent / "_internal/.connections").exists()
            for logo in ("drive", "youtube", "x", "facebook"):
                with opener.open(base+"/static/logos/"+logo+".svg") as response:
                    assert b"<svg" in response.read()
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
            render_request = {"project": {"assets": [{"id": "test", "path": str(media), "audio": True}],
                          "clips": [{"assetId": "test", "kind": "audio", "in": .1, "out": .8, "start": 0, "speed": 1}]},
                          "outputDirectory": str(root), "filename": "test-cut", "outputFormat": "mp3", "requestId": "a" * 32}
            job = api("/api/renders", render_request)
            assert api("/api/renders", render_request)["id"] == job["id"], "Repeated export must reuse its job"
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
                assert extension("status")["version"] == info["version"]
                browser_job = extension("download", url=url, destination="local", outputFormat="mp3")["job"]
                for _ in range(100):
                    browser_result = extension("job", jobId=browser_job["id"])["job"]
                    if browser_result["status"] not in ("queued", "running"):
                        break
                    time.sleep(.1)
                assert browser_result["status"] == "completed", browser_result
                assert Path(browser_result["path"]).is_file()
                assert browser_job["id"] in [job["id"] for job in api("/api/jobs")["jobs"]]
                # Caption discovery and muxing must work in the frozen build,
                # including the minimal native host, without external websites.
                subprocess.run([str(media_tools/"ffmpeg.exe"), "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=160x90:rate=10:duration=1", "-f", "lavfi", "-i", "sine=duration=1",
                    "-shortest", "-c:v", "libx264", "-c:a", "aac", str(root/"caption-source.mp4")], env=env, check=True, capture_output=True)
                (root/"fr.vtt").write_text("WEBVTT\n\n00:00.000 --> 00:00.900\nBonjour de ClipHarbor\n", encoding="utf-8")
                (root/"caption.html").write_text('<title>Caption smoke</title><video src="caption-source.mp4"><track kind="subtitles" srclang="fr" label="French" src="fr.vtt"></video>', encoding="utf-8")
                caption_url=f"http://127.0.0.1:{source_server.server_port}/caption.html"
                caption_info=extension("inspect", url=caption_url)["info"]
                assert caption_info["subtitleTracks"][0]["language"] == "fr"
                caption_job=extension("download", url=caption_url, destination="local", outputFormat="mp4", subtitleLanguage="fr", subtitleSource="manual")["job"]
                for _ in range(200):
                    captioned=api("/api/jobs/"+caption_job["id"])
                    if captioned["status"] not in ("queued", "running"):
                        break
                    time.sleep(.1)
                assert captioned["status"] == "completed", captioned
                assert captioned["result"]["subtitleTrack"]["language"] == "fr"
                assert captioned["result"]["media"]["subtitles"][0]["codec"] == "mov_text"
            finally:
                source_server.shutdown()
                source_server.server_close()
            assert subprocess.check_output([str(tools/"node.exe"), "--version"], env=env).startswith(b"v22")
            api("/api/desktop/quit", {})
            assert process.wait(timeout=20) == 0
            # A browser click can start the installed engine without opening its
            # editor or relying on developer Python/FFmpeg/Node installations.
            assert extension("status")["version"] == info["version"]
            new_info = json.loads((root / "instance.json").read_text())
            assert new_info["pid"] != process.pid
            new_client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            shutdown = urllib.request.Request(f"http://127.0.0.1:{new_info['port']}/api/desktop/quit", data=b"{}",
                headers={"Content-Type": "application/json", "Cookie": "clipharbor-session=" + new_info["token"]})
            with new_client.open(shutdown, timeout=10) as response:
                assert json.load(response)["ok"]
            for _ in range(100):
                if not (root / "instance.json").exists():
                    break
                time.sleep(.1)
            assert not (root / "instance.json").exists(), "Auto-started engine must shut down cleanly"
            assert (root/"projects"/f"{saved['id']}.json").is_file()
            print(json.dumps({"ok": True, "version": info["version"], "export": status["result"]["media"]["duration"],
                              "graphical_setup": args.graphical_setup,
                              "gui_runtime": gui_runtime,
                              "checks": ["isolated PATH", "authenticated launch", "publisher Google registration",
                                         "no bundled user account", "destination logos", "single instance", "save/open project",
                                         "first-run media tools", "waveform", "MP3 export", "export request deduplication", "inspect/download", "bundled Node", "native extension download",
                                         "extension progress", "shared Activity", "caption inspection via native host", "embedded subtitle download", "cold engine startup", "clean quit"]}))
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
