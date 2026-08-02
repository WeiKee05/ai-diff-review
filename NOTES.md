# Build notes

## Step 2 — scaffolding
- Python 3.13 + FastAPI + uvicorn, virtualenv for reproducible deps.
- /health and /spec are the only public routes; everything under /v1 will need auth.
- Chose time.monotonic() for uptime so clock adjustments can't make it go backwards.
- /spec limits are hardcoded for now — must move to a shared config so they can't
  drift from actual behaviour.

## AI tool usage
- Claude Code installed but not used yet; step 2 is boilerplate only.
