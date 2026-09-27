from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 2),
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "log": self.log[-80:],
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


class JobContext:
    def __init__(self, manager: "JobManager", job_id: str):
        self.manager = manager
        self.job_id = job_id

    def update(self, progress: float | None = None, message: str | None = None) -> None:
        self.manager.update(self.job_id, progress=progress, message=message)

    def write(self, line: str) -> None:
        self.manager.write(self.job_id, line)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._closing = False

    def start(self, kind: str, target: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            if self._closing:
                raise RuntimeError("ClipHarbor is closing")
            self._jobs[job.id] = job

        thread = threading.Thread(
            target=self._run,
            args=(job.id, target, args, kwargs),
            daemon=True,
            name=f"mediaforge-{kind}-{job.id[:7]}",
        )
        thread.start()
        return job

    def _run(
        self,
        job_id: str,
        target: Callable[..., dict[str, Any]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        self.update(job_id, status="running", message="Starting")
        try:
            result = target(JobContext(self, job_id), *args, **kwargs)
            self.update(job_id, status="completed", progress=100, message="Complete", result=result)
        except Exception as exc:  # surfaced to the local UI with useful context
            self.write(job_id, traceback.format_exc())
            self.update(job_id, status="failed", message="Failed", error=str(exc))

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                if value is not None:
                    setattr(job, key, value)
            job.updated_at = time.time()

    def write(self, job_id: str, line: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            clean = line.strip()
            if clean:
                job.log.append(clean)
                del job.log[:-200]
            job.updated_at = time.time()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def begin_shutdown(self) -> bool:
        with self._lock:
            if any(job.status in {"queued", "running"} for job in self._jobs.values()):
                return False
            self._closing = True
            return True


jobs = JobManager()
