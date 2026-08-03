"""Provider abstraction and LLM graceful degradation."""

import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.diff_parser import parse_unified_diff
from app.main import app
from app.providers import ProviderError, _parse_model_findings, llm_provider

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {config.API_TOKEN}"}

DIFF = "--- a/p.js\n+++ b/p.js\n@@ -1,1 +1,3 @@\n a\n+  eval(x);\n+  console.log(1);\n"


def wait_done(job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/v1/reviews/{job_id}", headers=AUTH).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.1)
    raise AssertionError("timeout")


def test_mock_is_the_default_provider():
    job_id = client.post("/v1/reviews", headers=AUTH, json={"diff": DIFF}).json()["jobId"]
    body = wait_done(job_id)
    assert body["status"] == "done"
    assert len(body["findings"]) == 2


def test_unknown_provider_is_rejected():
    r = client.post(
        "/v1/reviews",
        headers=AUTH,
        json={"diff": DIFF, "options": {"provider": "nonsense"}},
    )
    assert r.status_code == 422


def test_missing_api_key_raises_provider_error(monkeypatch):
    """Graceful degradation: unconfigured provider fails clearly, doesn't crash."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(ProviderError) as exc:
        llm_provider(parse_unified_diff(DIFF))
    assert "not configured" in str(exc.value)


def test_llm_failure_produces_failed_job_not_a_crash(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    r = client.post(
        "/v1/reviews",
        headers=AUTH,
        json={"diff": DIFF, "options": {"provider": "llm"}},
    )
    assert r.status_code == 202

    body = wait_done(r.json()["jobId"])
    assert body["status"] == "failed"
    assert "error" in body
    assert body["error"]


def test_hallucinated_positions_are_dropped():
    """A finding on a line not in the diff must not become output."""
    files = parse_unified_diff(DIFF)
    raw = '[{"ruleId":"MOCK-001","path":"p.js","line":999,"title":"fake"}]'
    assert _parse_model_findings(raw, {("p.js", 2): "  eval(x);"}) == []


def test_valid_model_output_is_accepted():
    raw = '[{"ruleId":"MOCK-001","path":"p.js","line":2,"title":"eval usage"}]'
    findings = _parse_model_findings(raw, {("p.js", 2): "  eval(x);"})
    assert len(findings) == 1
    assert findings[0].id == "MOCK-001:p.js:2"
    assert findings[0].evidence == "  eval(x);"


def test_unknown_rule_ids_are_dropped():
    raw = '[{"ruleId":"MADE-UP","path":"p.js","line":2,"title":"x"}]'
    assert _parse_model_findings(raw, {("p.js", 2): "  eval(x);"}) == []


def test_non_json_output_raises_provider_error():
    with pytest.raises(ProviderError):
        _parse_model_findings("I'm afraid I can't do that", {})
