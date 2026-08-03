"""AI Diff Review Service — application entry point."""

import logging
import time

import asyncio
import json

from app import jobs
from app.diff_parser import parse_unified_diff
from app.models import ReviewRequest


from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.auth import require_bearer_token
from app.errors import STATUS_TO_CODE, ApiError, envelope


from app import cache


from fastapi.responses import StreamingResponse


logger = logging.getLogger("diffreview")

_STARTED_AT = time.monotonic()

app = FastAPI(title="AI Diff Review Service", version=config.APP_VERSION)


# --------------------------------------------------------------------------
# Error handlers: every non-2xx response leaves through one of these.
# --------------------------------------------------------------------------

@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    return envelope(exc.status_code, exc.code, exc.message, exc.headers)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    code = STATUS_TO_CODE.get(exc.status_code, "internal")
    return envelope(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return envelope(422, "invalid_diff", "Request body failed validation.")


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    # Log the real cause, return nothing revealing to the caller.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return envelope(500, "internal", "Internal server error.")


# --------------------------------------------------------------------------
# Public routes
# --------------------------------------------------------------------------

@app.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict:
    return {
        "status": "ok",
        "version": config.APP_VERSION,
        "uptimeSeconds": round(time.monotonic() - _STARTED_AT, 3),
    }


@app.api_route("/spec", methods=["GET", "HEAD"])
def spec() -> dict:
    return {
        "specVersion": config.SPEC_VERSION,
        "providers": config.PROVIDERS,
        "limits": {
            "maxPayloadBytes": config.MAX_PAYLOAD_BYTES,
            "chunkBytes": config.CHUNK_BYTES,
            "maxConcurrentJobs": config.MAX_CONCURRENT_JOBS,
            "rateLimitPerMinute": config.RATE_LIMIT_PER_MINUTE,
        },
    }


# --------------------------------------------------------------------------
# Protected routes: auth is attached to the router, so every route added
# below inherits it automatically.
# --------------------------------------------------------------------------

v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_bearer_token)])


@v1.post("/reviews", status_code=202)
async def submit_review(request: Request) -> dict:
    # 1. Size first — before parsing, so a huge body is cheap to reject.
    raw = await request.body()
    if len(raw) > config.MAX_PAYLOAD_BYTES:
        raise ApiError(413, "payload_too_large", "Diff exceeds the maximum payload size.")

    # 2. JSON validity.
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError(400, "invalid_json", "Request body is not valid JSON.")

    if not isinstance(payload, dict):
        raise ApiError(400, "invalid_json", "Request body must be a JSON object.")

    body = ReviewRequest.model_validate(payload)

    # 3. Diff must be present, non-empty, and parseable.
    if not body.diff or not body.diff.strip():
        raise ApiError(422, "invalid_diff", "Field 'diff' is required and must not be empty.")

    if not parse_unified_diff(body.diff):
        raise ApiError(422, "invalid_diff", "Body could not be parsed as a unified diff.")

    # 4. Idempotency: same key + same body -> same job; different body -> 409.
    provider = body.options.provider
    key = cache.content_hash(body.diff, provider)
    idem_key = request.headers.get("Idempotency-Key")

    if idem_key:
        existing = cache.lookup_idempotency(idem_key)
        if existing is not None:
            stored_hash, stored_job_id = existing
            if stored_hash != key:
                raise ApiError(
                    409,
                    "idempotency_conflict",
                    "Idempotency-Key already used with a different body.",
                )
            prior = jobs.get_job(stored_job_id)
            if prior is not None:
                return {"jobId": prior.job_id, "status": prior.status}

    job = jobs.create_job(
        input_bytes=len(body.diff.encode("utf-8")),
        max_findings=body.options.maxFindings,
    )
    if idem_key:
        cache.store_idempotency(idem_key, key, job.job_id)

    asyncio.create_task(jobs.run_job(job, body.diff, key))

    return {"jobId": job.job_id, "status": "queued"}


@v1.get("/reviews/{job_id}")
def get_review(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise ApiError(404, "not_found", "No job with that id.")
    return job.to_dict()

@v1.get("/reviews/{job_id}/stream")
async def stream_review(job_id: str, request: Request):
    job = jobs.get_job(job_id)
    if job is None:
        raise ApiError(404, "not_found", "No job with that id.")

    async def event_source():
        """Replay is the default: both live and finished jobs read the same log.

        Polling at 50ms rather than using an asyncio.Event — simpler, and the
        latency is irrelevant against a 30s budget.
        """
        sent = 0
        while True:
            if await request.is_disconnected():
                return

            while sent < len(job.events):
                entry = job.events[sent]
                sent += 1
                yield f"event: {entry['event']}\ndata: {json.dumps(entry['data'])}\n\n"
                if entry["event"] == "done":
                    return

            if job.status in ("done", "failed") and sent >= len(job.events):
                return

            await asyncio.sleep(0.05)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stop proxies buffering the stream
        },
    )


app.include_router(v1)
