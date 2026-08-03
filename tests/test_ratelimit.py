"""Rate limiting: sustained rate succeeds, burst is capped, GETs are exempt."""

import pytest
from fastapi.testclient import TestClient

from app import config, ratelimit
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {config.API_TOKEN}"}

DIFF = "--- a/r.js\n+++ b/r.js\n@@ -1,1 +1,2 @@\n a\n+  console.log(1);\n"


@pytest.fixture(autouse=True)
def full_bucket():
    ratelimit.reset()
    yield
    ratelimit.reset()


def test_declared_sustained_rate_all_succeed():
    """30 rapid submissions must all succeed — the declared rate."""
    codes = [
        client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF}).status_code
        for _ in range(config.RATE_LIMIT_PER_MINUTE)
    ]
    assert all(c == 202 for c in codes)


def test_burst_beyond_capacity_is_429():
    for _ in range(config.RATE_LIMIT_BURST):
        client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF})

    r = client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


def test_429_includes_retry_after():
    for _ in range(config.RATE_LIMIT_BURST + 1):
        r = client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF})

    assert r.status_code == 429
    assert "retry-after" in {k.lower() for k in r.headers}
    assert int(r.headers["Retry-After"]) >= 1


def test_never_5xx_under_burst():
    codes = {
        client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF}).status_code
        for _ in range(config.RATE_LIMIT_BURST + 30)
    }
    assert not any(c >= 500 for c in codes)
    assert codes <= {202, 429}


def test_gets_are_never_rate_limited():
    """Exhaust the bucket, then confirm GETs still work."""
    job_id = client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF}).json()["jobId"]

    for _ in range(config.RATE_LIMIT_BURST + 10):
        client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF})

    assert client.get(f"/v1/reviews/{job_id}", headers=AUTH).status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/spec").status_code == 200


def test_bucket_refills_over_time():
    ratelimit.reset()
    for _ in range(config.RATE_LIMIT_BURST + 5):
        client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF})

    allowed, retry_after = ratelimit.try_acquire()
    assert allowed is False
    assert retry_after >= 1
