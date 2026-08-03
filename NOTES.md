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


## Step 4 — diff parser
- Hand-rolled rather than using the `unidiff` library: the parser is the thing
  being evaluated, and I need per-file raw text preserved for chunking later.
- Structure comes from hunk-header arithmetic (read exactly new_count body
  lines), never from scanning content for `diff --git`. This is what makes
  injected diff syntax inert — it's architectural, not a filter.
- Line numbers: context and added lines advance the counter, removed lines
  don't, because removed lines aren't in the new file.
- Strip only the first character of a body line so indentation survives in
  `evidence`.
- ParsedFile keeps `raw_text` per file — needed on Day 3 for chunking on file
  boundaries. Deciding this now avoided a rewrite.
- pytest.ini with `pythonpath = .` so tests import `app` without setup.


## Step 5 — mock provider rules
- One finding per rule per line: each rule is a yes/no question about the line,
  not a count of occurrences. Confirmed by the id format (ruleId:path:line),
  which couldn't distinguish two hits on the same line anyway.
- MOCK-002 regex taken verbatim from the brief — it defines correctness, so
  "improving" it would be diverging from the spec.
- MOCK-003 requires all three conditions: string literal, SQL keyword inside it
  (whole-word, so "deleted_at" doesn't fire), and a + outside any literal.
- MOCK-004 only sees added lines. A catch whose body lies outside the diff is
  treated as non-empty rather than guessed at. Documented limitation.
- Known edge: MOCK-005's [=!]=\s*null also matches the == inside ===.
  Accepted — the brief specifies "== null or != null" literally.
- Ordering/dedup applied once over the whole collection, not per line, because
  chunking will produce findings in batches that need merging.
