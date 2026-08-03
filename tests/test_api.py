"""End-to-end tests against the HTTP layer."""

import time

from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {config.API_TOKEN}"}

DIFF = "--- a/x.js\n+++ b/x.js\n@@ -1,1 +1,3 @@\n a\n+  eval(x);\n+  console.log(1);\n"


def _wait_for_done(job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/v1/reviews/{job_id}", headers=AUTH).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_submit_and_poll():
    resp = client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF})
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"

    body = _wait_for_done(resp.json()["jobId"])
    assert body["status"] == "done"
    assert [f["id"] for f in body["findings"]] == [
        "MOCK-001:x.js:2",
        "MOCK-007:x.js:3",
    ]
    assert body["usage"]["chunks"] == 1
    assert body["usage"]["cacheHit"] is False


def test_auth_required():
    assert client.post("/v1/reviews", json={"diff": DIFF}).status_code == 401
    assert client.get("/v1/reviews/anything").status_code == 401


def test_error_taxonomy():
    r = client.post("/v1/reviews", headers=AUTH, content="not json")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_json"

    r = client.post("/v1/reviews", headers=AUTH, json={"diff": ""})
    assert r.json()["error"]["code"] == "invalid_diff"

    r = client.post("/v1/reviews", headers=AUTH, json={"diff": "prose"})
    assert r.status_code == 422

    r = client.get("/v1/reviews/nope", headers=AUTH)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_payload_too_large():
    huge = "x" * (config.MAX_PAYLOAD_BYTES + 1)
    r = client.post("/v1/reviews", headers=AUTH, json={"diff": huge})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_public_routes_need_no_token():
    assert client.get("/health").status_code == 200
    assert client.get("/spec").status_code == 200


def test_spec_matches_config():
    limits = client.get("/spec").json()["limits"]
    assert limits["maxConcurrentJobs"] == config.MAX_CONCURRENT_JOBS
    assert limits["rateLimitPerMinute"] == config.RATE_LIMIT_PER_MINUTE
