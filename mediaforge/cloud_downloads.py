"""Cloud-only downloads with isolated staging and recoverable failed uploads."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
from pathlib import Path

from .downloader import download
from .publishing import PublishError, _RenderProgress, upload, validate_destination
from .runtime import data_root

_lock = threading.RLock()
_active: set[str] = set()


def staging_root() -> Path:
    return data_root() / ".cache" / "cloud-downloads"


def _directory(download_id: str) -> Path:
    if not re.fullmatch(r"download-[A-Za-z0-9_-]+", download_id):
        raise ValueError("Invalid cloud download ID")
    root = staging_root().resolve()
    directory = (root / download_id).resolve()
    if directory.parent != root:
        raise ValueError("Invalid cloud download directory")
    return directory


def _save(result: dict) -> None:
    directory = _directory(result["cloudDownloadId"])
    temporary = directory / "pending.json.tmp"
    temporary.write_text(json.dumps(result), encoding="utf-8")
    temporary.replace(directory / "pending.json")


def _load(download_id: str) -> dict:
    directory = _directory(download_id)
    result = json.loads((directory / "pending.json").read_text(encoding="utf-8"))
    if not isinstance(result, dict) or not isinstance(result.get("media"), dict):
        raise ValueError("Invalid saved cloud download")
    if result.get("incomplete"):
        return {**result, "cloudDownloadId": download_id, "path": None, "token": None}
    if not isinstance(result.get("path"), str):
        raise ValueError("Invalid temporary download path")
    path = Path(result["path"]).resolve()
    if path.parent != directory or path.name in {"pending.json", "pending.json.tmp"}:
        raise ValueError("Invalid temporary download path")
    if not path.is_file() and not result.get("delivery"):
        raise FileNotFoundError("The temporary download is no longer available")
    return {**result, "cloudDownloadId": download_id, "path": str(path)}


def _remove(download_id: str) -> None:
    """Keep the recovery record until every other temporary file has been removed."""
    directory = _directory(download_id)
    manifest = directory / "pending.json"
    receipt = manifest.read_bytes() if manifest.exists() else None
    try:
        for child in directory.iterdir():
            if child == manifest:
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        manifest.unlink(missing_ok=True)
        directory.rmdir()
    except OSError:
        if receipt is not None and directory.is_dir() and not manifest.exists():
            manifest.write_bytes(receipt)
        raise


def pending_downloads() -> list[dict]:
    with _lock:
        pending = []
        for manifest in staging_root().glob("download-*/pending.json"):
            if manifest.parent.name in _active:
                continue
            try:
                pending.append(_load(manifest.parent.name))
            except (OSError, ValueError, KeyError):
                continue
        return pending


def _deliver(context, result: dict) -> dict:
    context.manager.update(context.job_id, result=result)
    try:
        delivered = upload(context, result=result, provider="drive", options=result.get("deliveryOptions"))
    except Exception as error:
        context.manager.update(context.job_id, result=result)
        raise PublishError(f"{error} Temporary download retained. Retry upload or discard it in Activity.") from None
    # Persist the receipt before cleanup so a locked file never leads to a second upload.
    delivered["cleanupPending"] = True
    context.manager.update(context.job_id, result=delivered)
    _save(delivered)
    context.update(99, "Upload verified; removing temporary files")
    try:
        _remove(result["cloudDownloadId"])
    except OSError:
        return {**delivered, "cleanupWarning": "Saved to Google Drive. Temporary files could not be removed; use Remove temporary files in Activity."}
    return {**delivered, "path": None, "token": None, "localAvailable": False, "cleanupPending": False}


def download_to_destination(context, *, provider="local", delivery_options=None, **kwargs):
    if provider not in {"local", "drive"}:
        raise ValueError("Unknown download destination")
    validate_destination(provider, kwargs["output_format"], delivery_options)
    if provider == "local":
        return download(context, **kwargs)
    root = staging_root()
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="download-", dir=root))
    download_id = directory.name
    with _lock:
        _active.add(download_id)
    try:
        try:
            _save({"cloudDownloadId": download_id, "downloadDestination": "drive", "incomplete": True,
                   "path": None, "token": None, "media": {"name": "Interrupted cloud download"}})
            # These files must never become editable project sources: upload cleanup removes them.
            result = download(_RenderProgress(context), **{**kwargs, "output_directory": str(directory), "register": lambda path: None})
            result = {**result, "cloudDownloadId": download_id, "downloadDestination": "drive",
                      "deliveryOptions": delivery_options or {}}
            _save(result)
        except Exception:
            _remove(download_id)
            raise
        return _deliver(context, result)
    finally:
        with _lock:
            _active.discard(download_id)


def reserve_retry(download_id: str) -> dict:
    with _lock:
        if download_id in _active:
            raise ValueError("This cloud download is already running")
        result = _load(download_id)
        if result.get("incomplete"):
            raise ValueError("This source download was interrupted. Discard it and start a new download.")
        if result.get("delivery"):
            raise ValueError("This file is already uploaded. Remove its temporary files instead.")
        validate_destination("drive", Path(result["path"]).suffix.lstrip("."), result.get("deliveryOptions"))
        _active.add(download_id)
        return result


def release_retry(download_id: str) -> None:
    with _lock:
        _active.discard(download_id)


def retry_cloud_download(context, *, result: dict) -> dict:
    try:
        return _deliver(context, result)
    finally:
        release_retry(result["cloudDownloadId"])


def discard_download(download_id: str) -> None:
    with _lock:
        if download_id in _active:
            raise ValueError("Wait for this cloud download to finish before removing temporary files")
        _load(download_id)
        _remove(download_id)
