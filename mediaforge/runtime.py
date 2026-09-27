"""Separate read-only installed resources from writable per-user state."""
import os
import sys
from pathlib import Path

VERSION = "0.5.0"
RESOURCE_ROOT = Path(__file__).resolve().parent.parent


def data_root() -> Path:
    override = os.environ.get("CLIPHARBOR_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ClipHarbor"
    return RESOURCE_ROOT


def configure_tools() -> None:
    if getattr(sys, "frozen", False):
        tools = RESOURCE_ROOT / "tools"
        os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")


def downloads_directory() -> Path:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            folder = Path(os.path.expandvars(value))
            if folder.is_dir():
                return folder
        except OSError:
            pass
    folder = Path.home() / "Downloads"
    return folder if folder.is_dir() else Path.home()
