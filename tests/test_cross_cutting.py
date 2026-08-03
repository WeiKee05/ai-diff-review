"""Chunking, caching, idempotency — the cross-cutting behaviours."""

import time

from fastapi.testclient import TestClient

from app import config
from app.chunking import chunk_files
from app.diff_parser import parse_unified_diff
from app.jobs import scan_diff
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {config.API_TOKEN}"}


def make_file_diff(name: str, body_lines: int = 2) -> str:
    lines = [f"--- a/{name}", f"+++ b/{name}", f"@@ -1,1 +1,{body_lines + 1} @@", " ctx"]
    for i in range(body_lines):
        lines.append(f"+  console.log({i});")
    return "\n".join(lines) + "\n"


def wait_done(job_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/v1/reviews/{job_id}", headers=AUTH).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("timeout")


def submit(diff, headers=None, **options):
    payload = {"diff": diff}
    if options:
        payload["options"] = options
    return client.post("/v1/reviews", headers={**AUTH, **(headers or {})}, json=payload)


# --- chunking -------------------------------------------------------------


def test_small_diff_is_one_chunk():
    files = parse_unified_diff(make_file_diff("a.js"))
    assert len(chunk_files(files)) == 1


def test_files_never_split_across_chunks():
    diff = "".join(make_file_diff(f"f{i}.js") for i in range(5))
    files = parse_unified_diff(diff)
    # Tiny limit forces one file per chunk.
    chunks = chunk_files(files, limit=10)
    assert len(chunks) == 5
    assert all(len(c) == 1 for c in chunks)


def test_chunking_does_not_change_findings():
    diff = "".join(make_file_diff(f"f{i}.js") for i in range(4))
    findings, chunks = scan_diff(diff)
    assert chunks == 1

    from app.rules import order_and_dedupe

    manual = []
    for parsed in parse_unified_diff(diff):
        from app.rules import check_line

        for a in parsed.added_lines:
            manual.extend(check_line(parsed.path, a.line, a.content))
    assert [f.id for f in findings] == [f.id for f in order_and_dedupe(manual)]


# --- caching --------------------------------------------------------------


def test_identical_submission_is_cache_hit():
    diff = make_file_diff("cache-test.js")

    first = wait_done(submit(diff).json()["jobId"])
    assert first["usage"]["cacheHit"] is False

    second = wait_done(submit(diff).json()["jobId"])
    assert second["usage"]["cacheHit"] is True
    assert second["findings"] == first["findings"]


def test_different_diff_is_not_a_cache_hit():
    wait_done(submit(make_file_diff("one.js")).json()["jobId"])
    other = wait_done(submit(make_file_diff("two.js")).json()["jobId"])
    assert other["usage"]["cacheHit"] is False


def test_max_findings_truncates_but_usage_is_full():
    diff = make_file_diff("trunc.js", body_lines=5)
    body = wait_done(submit(diff, maxFindings=2).json()["jobId"])
    assert len(body["findings"]) == 2


# --- idempotency ----------------------------------------------------------


def test_same_key_same_body_returns_same_job():
    diff = make_file_diff("idem.js")
    headers = {"Idempotency-Key": "key-abc"}

    first = submit(diff, headers=headers).json()["jobId"]
    second = submit(diff, headers=headers).json()["jobId"]
    assert first == second


def test_same_key_different_body_is_409():
    headers = {"Idempotency-Key": "key-conflict"}
    submit(make_file_diff("x.js"), headers=headers)

    resp = submit(make_file_diff("y.js"), headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_conflict"


def test_no_key_creates_separate_jobs():
    diff = make_file_diff("nokey.js")
    assert submit(diff).json()["jobId"] != submit(diff).json()["jobId"]
