"""Error envelope: every non-2xx response in this service uses this shape."""

from fastapi.responses import JSONResponse

STATUS_TO_CODE = {
    400: "invalid_json",
    401: "unauthorized",
    404: "not_found",
    409: "idempotency_conflict",
    413: "payload_too_large",
    422: "invalid_diff",
    429: "rate_limited",
}


class ApiError(Exception):
    """Raised deliberately anywhere in the app to produce an envelope response."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        super().__init__(message)


def envelope(status_code: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )
