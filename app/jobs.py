"""In-memory job store and background review pipeline.

Single process by design: the store is a plain dict, so the service must run
with one worker. Jobs do not survive a restart — an accepted tradeoff, since
the brief requires no durability.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal

from app import config
from app.diff_parser import parse_unified_diff
from app.rules import Finding, check_line, order_and_dedupe

Status = Literal["queued", "running", "done", "failed"]

# Caps concurrent processing. Acquired inside the task, never in the endpoint,
# so submissions always return immediately.
_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)

_jobs: dict[str, "Job"] = {}


@dataclass
class Job:
    job_id: str
    status: Status = "queued"
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    input_bytes: int = 0
    chunks: int = 1
    cache_hit: bool = False
    max_findings: int = 100

    def to_dict(self) -> dict:
        body: dict = {
            "jobId": self.job_id,
            "status": self.status,
            "usage": {
                "inputBytes": self.input_bytes,
                "chunks": self.chunks,
                "cacheHit": self.cache_hit,
            },
        }
        if self.status == "done":
            body["findings"] = [f.to_dict() for f in self.findings[: self.max_findings]]
        if self.status == "failed" and self.error:
            body["error"] = self.error
        return body


def create_job(input_bytes: int, max_findings: int) -> Job:
    job = Job(
        job_id=uuid.uuid4().hex,
        input_bytes=input_bytes,
        max_findings=max_findings,
    )
    _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def scan_diff(diff: str) -> list[Finding]:
    """Pure, synchronous scan. No I/O, no shared state — safe in a thread."""
    findings: list[Finding] = []
    for parsed in parse_unified_diff(diff):
        contents = [a.content for a in parsed.added_lines]
        for index, added in enumerate(parsed.added_lines):
            findings.extend(
                check_line(
                    path=parsed.path,
                    line=added.line,
                    content=added.content,
                    following=contents[index + 1 :],
                )
            )
    return order_and_dedupe(findings)


async def run_job(job: Job, diff: str) -> None:
    """Background worker. Never raises: failure is recorded on the job."""
    async with _semaphore:
        job.status = "running"
        try:
            # to_thread keeps CPU-bound scanning off the event loop, so other
            # requests stay responsive and jobs genuinely interleave.
            job.findings = await asyncio.to_thread(scan_diff, diff)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - a job must never crash the app
            job.status = "failed"
            job.error = f"Review failed: {type(exc).__name__}"
