"""AI Diff Review Service — application entry point."""

import logging
import time

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.auth import require_bearer_token
from app.errors import STATUS_TO_CODE, ApiError, envelope

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

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": config.APP_VERSION,
        "uptimeSeconds": round(time.monotonic() - _STARTED_AT, 3),
    }


@app.get("/spec")
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


@v1.get("/ping")
def ping() -> dict:
    """TEMPORARY — proves auth works. Remove before submission."""
    return {"pong": True}


app.include_router(v1)
