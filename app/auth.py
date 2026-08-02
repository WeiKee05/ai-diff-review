"""Bearer token authentication for all /v1 routes."""

import secrets

from fastapi import Header

from app import config
from app.errors import ApiError


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    """Reject the request unless a valid bearer token is present."""
    if not config.API_TOKEN:
        # Fail closed: a misconfigured server denies everything rather than
        # accidentally serving unauthenticated traffic.
        raise ApiError(401, "unauthorized", "Server is missing API_TOKEN configuration.")

    if authorization is None:
        raise ApiError(401, "unauthorized", "Missing Authorization header.")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "unauthorized", "Authorization header must use the Bearer scheme.")

    # compare_digest avoids leaking token contents through response timing.
    if not secrets.compare_digest(token.strip(), config.API_TOKEN):
        raise ApiError(401, "unauthorized", "Invalid bearer token.")
