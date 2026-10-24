"""Register this source checkout's native bridge for Chrome and Edge (per user)."""
import argparse
import json
import os
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mediaforge.browser_bridge import HOST_NAME, EXTENSION_ORIGIN, FACEBOOK_ORIGIN
from mediaforge.runtime import data_root


def manifest_locations():
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library/Application Support"
        return [base / browser / "NativeMessagingHosts" / f"{HOST_NAME}.json"
                for browser in ("Google/Chrome", "Microsoft Edge", "Chromium")]
    base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [base / browser / "NativeMessagingHosts" / f"{HOST_NAME}.json"
            for browser in ("google-chrome", "microsoft-edge", "chromium")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unregister", action="store_true")
    args = parser.parse_args()
    directory = data_root() / "browser-bridge"
    manifest = directory / f"{HOST_NAME}.json"
    if args.unregister:
        if os.name == "nt":
            import winreg
            for vendor in (r"Google\Chrome", r"Microsoft\Edge"):
                key_name = rf"Software\{vendor}\NativeMessagingHosts\{HOST_NAME}"
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
                        current = winreg.QueryValue(key, None)
                    # Never remove a newer installer/other checkout's registration.
                    if Path(current) == manifest:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_name)
                except FileNotFoundError:
                    pass
        else:
            for location in manifest_locations():
                try:
                    if json.loads(location.read_text())["path"] == str(directory / "launch-bridge"):
                        location.unlink()
                except FileNotFoundError:
                    pass
        print("Removed matching source bridge registrations. Media and account connections were kept.")
        return
    if not (ROOT / "browser_bridge.py").is_file():
        parser.error("Run this script from the complete ClipHarbor source checkout, not the extension-only ZIP.")
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        launcher = directory / "launch-bridge.cmd"
        def batch_quote(path):
            value = str(path)
            if any(char in value for char in '\r\n"'):
                raise ValueError("This source path cannot be used by the Windows bridge launcher.")
            return '"' + value.replace('%', '%%') + '"'
        launcher.write_text("@echo off\r\nsetlocal DisableDelayedExpansion\r\nchcp 65001 >nul\r\n" + batch_quote(sys.executable) + " " + batch_quote(ROOT / "browser_bridge.py") + " %*\r\n", encoding="utf-8")
    else:
        launcher = directory / "launch-bridge"
        launcher.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(ROOT / "browser_bridge.py")) + ' "$@"\n', encoding="utf-8")
        launcher.chmod(0o700)
    record = json.dumps({"name": HOST_NAME, "description": "ClipHarbor source browser bridge", "path": str(launcher),
                         "type": "stdio", "allowed_origins": [EXTENSION_ORIGIN, FACEBOOK_ORIGIN]}, indent=2)
    manifest.write_text(record, encoding="utf-8")
    if os.name == "nt":
        import winreg
        for vendor in (r"Google\Chrome", r"Microsoft\Edge"):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\{vendor}\NativeMessagingHosts\{HOST_NAME}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest))
    else:
        for location in manifest_locations():
            location.parent.mkdir(parents=True, exist_ok=True)
            location.write_text(record, encoding="utf-8")
    print("Registered this checkout's bridge for Chrome and Edge.")
    print("Load unpacked extension folder:", ROOT / "browser-extension")


if __name__ == "__main__":
    main()
