from __future__ import annotations

import threading
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

_log = logging.getLogger(__name__)


class JobCancelled(RuntimeError):
    pass


def diagnostic_source(value: str) -> str:
    """Keep source identity locally, excluding credentials and signed queries."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "(invalid source URL)"
    query = urlencode({"v": parse_qs(parsed.query)["v"][0]}) if parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"} and "v" in parse_qs(parsed.query) else ""
    return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, query, ""))


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
    retry_job_id: str | None = None
    cancel_requested: bool = False

    def public(self) -> dict[str, Any]:
        value = {
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
        if self.retry_job_id:
            value["retryJobId"] = self.retry_job_id
        if self.kind == "download":
            value["canCancel"] = self.status in {"queued", "running"} and self.result is None and not self.cancel_requested
            value["cancelRequested"] = self.cancel_requested
        return value


class JobContext:
    def __init__(self, manager: "JobManager", job_id: str):
        self.manager = manager
        self.job_id = job_id

    def update(self, progress: float | None = None, message: str | None = None) -> None:
        self.check_cancelled()
        self.manager.update(self.job_id, progress=progress, message=message)

    def write(self, line: str) -> None:
        self.check_cancelled()
        self.manager.write(self.job_id, line)

    def check_cancelled(self) -> None:
        job = self.manager.get(self.job_id)
        if job and job.cancel_requested:
            raise JobCancelled("Download cancelled")


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._closing = False
        self._submissions: dict[str, str] = {}

    def start_once(self, key: str, kind: str, target: Callable[..., dict[str, Any]], **kwargs: Any) -> Job:
        """A repeated request for one explicit export returns its existing job."""
        with self._lock:
            existing = self._submissions.get(key)
            if existing:
                return self._jobs[existing]
            job = self.start(kind, target, **kwargs)
            self._submissions[key] = job.id
            return job

    def start_retry(self, source_id: str, kind: str, target: Callable[..., dict[str, Any]], **kwargs: Any) -> Job:
        with self._lock:
            source = self._jobs.get(source_id)
            if not source or source.status != "failed" or source.kind not in {"upload", "share", "render"}:
                raise ValueError("Choose a failed export to retry.")
            if (source.result or {}).get("browserPostingUncertain"):
                raise ValueError("Check Facebook before starting another export; this post may already exist.")
            if source.retry_job_id:
                return self._jobs[source.retry_job_id]
            job = self.start(kind, target, **kwargs)
            source.retry_job_id = job.id
            return job

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
        _log.info("Job %s (%s) started: source=%s, format=%s, X-compatible=%s, audio=%s, subtitle=%s/%s, subtitle-display=%s, burn-size=%s", job_id,
                  self._jobs[job_id].kind, diagnostic_source(str(kwargs.get("url") or "")),
                  kwargs.get("output_format"), kwargs.get("x_compatible"), kwargs.get("audio_format_id"), kwargs.get("subtitle_source"), kwargs.get("subtitle_language"), kwargs.get("subtitle_mode", "embed"), kwargs.get("burn_size", "source"))
        try:
            JobContext(self, job_id).check_cancelled()
            result = target(JobContext(self, job_id), *args, **kwargs)
            self.update(job_id, status="completed", progress=100, message="Complete", result=result)
            _log.info("Job %s completed", job_id)
        except Exception as exc:  # surfaced to the local UI with useful context
            if isinstance(exc, JobCancelled) or self._jobs[job_id].cancel_requested:
                self.update(job_id, status="cancelled", message="Cancelled")
                _log.info("Job %s cancelled", job_id)
                return
            self.write(job_id, traceback.format_exc())
            self.update(job_id, status="failed", message="Failed", error=str(exc))
            _log.exception("Job %s failed", job_id)

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.kind != "download" or job.status not in {"queued", "running"}:
                raise ValueError("Choose an active download to cancel")
            if job.result is not None:
                raise ValueError("The source download has finished; wait for its upload to finish")
            job.cancel_requested = True
            job.message = "Cancelling download…"
            _log.info("Job %s cancellation requested", job_id)
            return job

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

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.public() for job in sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)[:100]
                    if job.kind != "connection"]

    def begin_shutdown(self) -> bool:
        with self._lock:
            if any(job.status in {"queued", "running"} for job in self._jobs.values()):
                return False
            self._closing = True
            return True


jobs = JobManager()
