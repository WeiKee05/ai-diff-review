# Build notes

## Step 2 — scaffolding
- Python 3.13 + FastAPI + uvicorn, virtualenv for reproducible deps.
- /health and /spec are the only public routes; everything under /v1 will need auth.
- Chose time.monotonic() for uptime so clock adjustments can't make it go backwards.
- /spec limits are hardcoded for now — must move to a shared config so they can't
  drift from actual behaviour.

## AI tool usage
- Claude Code installed but not used yet; step 2 is boilerplate only.

## Step 3 — auth and error envelope
- Auth via router-level dependency on /v1, not middleware. Chose this because
  Starlette's BaseHTTPMiddleware complicates streaming responses, and an SSE
  endpoint is coming. Router-level (not per-route) means new /v1 routes are
  protected automatically.
- Known tradeoff: an unknown path under /v1 returns 404, not 401, because
  routing resolves before dependencies run. Acceptable — a nonexistent path
  isn't a protected route.
- secrets.compare_digest instead of == for constant-time comparison.
- Fails closed when API_TOKEN is unset: denies everything rather than serving
  unauthenticated traffic. Verified accidentally — a malformed .env produced
  401s on valid tokens, which is the correct failure direction.
- Four exception handlers (ApiError, StarletteHTTPException, RequestValidationError,
  bare Exception) so no error path can leak a non-envelope shape.
- Limits live in config.py; /spec reads from there so declared limits can't drift.
