"""AI Diff Review Service — application entry point."""

import time

from fastapi import FastAPI

APP_VERSION = "0.1.0"
_STARTED_AT = time.monotonic()

app = FastAPI(title="AI Diff Review Service", version=APP_VERSION)


@app.get("/health")
def health() -> dict:
    """Public liveness check."""
    return {
        "status": "ok",
        "version": APP_VERSION,
        "uptimeSeconds": round(time.monotonic() - _STARTED_AT, 3),
    }


@app.get("/spec")
def spec() -> dict:
    """Public self-declaration. These numbers MUST match real behaviour."""
    return {
        "specVersion": "1.0",
        "providers": ["mock", "llm"],
        "limits": {
            "maxPayloadBytes": 1048576,
            "chunkBytes": 65536,
            "maxConcurrentJobs": 4,
            "rateLimitPerMinute": 30,
        },
    }
