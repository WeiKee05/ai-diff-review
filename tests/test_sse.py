"""SSE streaming and replay."""

import json
import time

from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {config.API_TOKEN}"}

DIFF = (
    "--- a/s.js\n+++ b/s.js\n@@ -1,1 +1,4 @@\n a\n"
    "+  eval(x);\n+  console.log(1);\n+  // TODO fix\n"
)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Turn a raw SSE body into (event_name, data) pairs."""
    events = []
    for block in text.strip().split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name is not None:
            events.append((name, data))
    return events


def submit_and_finish(diff=DIFF):
    job_id = client.post("/v1/reviews", headers=AUTH, json={"diff": diff}).json()["jobId"]
    deadline = time.time() + 10
    while time.time() < deadline:
        if client.get(f"/v1/reviews/{job_id}", headers=AUTH).json()["status"] in (
            "done",
            "failed",
        ):
            return job_id
        time.sleep(0.05)
    raise AssertionError("job never finished")


def test_stream_requires_auth():
    assert client.get("/v1/reviews/anything/stream").status_code == 401


def test_stream_unknown_job_is_404():
    r = client.get("/v1/reviews/nope/stream", headers=AUTH)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_stream_content_type():
    job_id = submit_and_finish()
    with client.stream("GET", f"/v1/reviews/{job_id}/stream", headers=AUTH) as r:
        assert "text/event-stream" in r.headers["content-type"]


def test_stream_has_status_findings_and_done():
    job_id = submit_and_finish()
    events = parse_sse(client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH).text)

    names = [name for name, _ in events]
    assert "status" in names
    assert names.count("finding") == 3
    assert names[-1] == "done"


def test_done_event_carries_total_and_usage():
    job_id = submit_and_finish()
    events = parse_sse(client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH).text)

    name, data = events[-1]
    assert name == "done"
    assert data["total"] == 3
    assert data["usage"]["chunks"] == 1
    assert "inputBytes" in data["usage"]


def test_findings_are_ordered_in_stream():
    job_id = submit_and_finish()
    events = parse_sse(client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH).text)

    ids = [d["id"] for n, d in events if n == "finding"]
    assert ids == sorted(ids, key=lambda i: (i.split(":")[1], int(i.split(":")[2]), i))


def test_replay_is_identical():
    """The scored requirement: reconnecting must give the same stream."""
    job_id = submit_and_finish()

    first = client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH).text
    second = client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH).text
    third = client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH).text

    assert first == second == third
    assert parse_sse(first)[-1][0] == "done"


def test_stream_matches_polled_findings():
    job_id = submit_and_finish()
    polled = client.get(f"/v1/reviews/{job_id}", headers=AUTH).json()["findings"]
    streamed = [d for n, d in parse_sse(
        client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH).text
    ) if n == "finding"]

    assert polled == streamed
