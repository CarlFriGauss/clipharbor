from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProjectStore:
    """Small on-disk store for named editor workspaces."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._lock = threading.RLock()

    def _path(self, project_id: str) -> Path:
        if not project_id or any(char not in "0123456789abcdef" for char in project_id.lower()):
            raise ValueError("Invalid project identifier")
        return self.directory / f"{project_id.lower()}.json"

    def list(self) -> list[dict[str, Any]]:
        self.directory.mkdir(parents=True, exist_ok=True)
        projects: list[dict[str, Any]] = []
        with self._lock:
            for path in self.directory.glob("*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    projects.append({
                        "id": str(record["id"]),
                        "name": str(record["name"]),
                        "updatedAt": str(record["updatedAt"]),
                        "assetCount": len((record.get("project") or {}).get("assets") or []),
                        "clipCount": len((record.get("project") or {}).get("clips") or []),
                    })
                except (OSError, ValueError, KeyError, TypeError):
                    continue
        return sorted(projects, key=lambda item: item["updatedAt"], reverse=True)

    def get(self, project_id: str) -> dict[str, Any]:
        path = self._path(project_id)
        with self._lock:
            if not path.is_file():
                raise FileNotFoundError("Project not found")
            return json.loads(path.read_text(encoding="utf-8"))

    def save(self, name: str, project: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
        clean_name = " ".join(str(name).split()).strip()
        if not clean_name:
            raise ValueError("Project name is required")
        if len(clean_name) > 120:
            raise ValueError("Project name is too long")
        if not isinstance(project, dict):
            raise ValueError("Project data must be an object")
        identifier = project_id or secrets.token_hex(12)
        path = self._path(identifier)
        record = {
            "version": 1,
            "id": identifier,
            "name": clean_name,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "project": project,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
            temporary.replace(path)
        return {key: record[key] for key in ("id", "name", "updatedAt")}

    def delete(self, project_id: str) -> None:
        path = self._path(project_id)
        with self._lock:
            if not path.is_file():
                raise FileNotFoundError("Project not found")
            path.unlink()
