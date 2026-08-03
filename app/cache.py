"""Result cache and idempotency registry.

Two distinct mechanisms:
  - cache: keyed on content hash; avoids recomputing identical work
  - idempotency: keyed on a client-supplied header; returns the original jobId
"""

from __future__ import annotations

import hashlib
import json

from app.rules import Finding

# content hash -> (findings, chunks)
_results: dict[str, tuple[list[Finding], int]] = {}

# idempotency key -> (content hash, job id)
_idempotency: dict[str, tuple[str, str]] = {}


def content_hash(diff: str, provider: str) -> str:
    """Hash the inputs that determine the result.

    maxFindings is deliberately excluded: it truncates the ordered list on
    read, and usage must still reflect the full scan.
    """
    payload = json.dumps({"diff": diff, "provider": provider}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_result(key: str) -> tuple[list[Finding], int] | None:
    return _results.get(key)


def store_result(key: str, findings: list[Finding], chunks: int) -> None:
    _results[key] = (findings, chunks)


def lookup_idempotency(idem_key: str) -> tuple[str, str] | None:
    return _idempotency.get(idem_key)


def store_idempotency(idem_key: str, hash_value: str, job_id: str) -> None:
    _idempotency[idem_key] = (hash_value, job_id)
