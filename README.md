# AI Diff Review Service

An HTTP API that accepts a unified diff, reviews it asynchronously against
a set of rules, and returns structured findings. Built for the Xsolla
AI-First Engineering Intern take-home assessment.

Full architecture and design rationale: see [SUBMISSION.md](./SUBMISSION.md).

## Live service

- **Base URL:** https://ai-diff-review-zx8m.onrender.com
- **Docs (interactive):** https://ai-diff-review-zx8m.onrender.com/docs

## Running locally

Requires Python 3.13+.

```bash
git clone https://github.com/WeiKee05/ai-diff-review.git
cd ai-diff-review

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
API_TOKEN=choose-any-string-for-local-testing
GEMINI_API_KEY=your-gemini-key-here      # optional, only needed for the llm provider
GEMINI_MODEL=gemini-flash-latest         # optional, defaults to this value
```

Run the server:

```bash
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

Run the test suite:

```bash
pytest -v
```

## API summary

All `/v1/*` routes require `Authorization: Bearer <API_TOKEN>`.
`/health` and `/spec` are public.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/spec` | Machine-readable capability declaration |
| POST | `/v1/reviews` | Submit a diff for review; returns a `jobId` immediately |
| GET | `/v1/reviews/{jobId}` | Poll job status and findings |
| GET | `/v1/reviews/{jobId}/stream` | Server-Sent Events stream of the same job, with replay support |

### Example: submit and poll

```bash
TOKEN="your-token"
BASE="http://localhost:8000"

JOB=$(curl -s -X POST $BASE/v1/reviews \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"diff":"--- a/x.js\n+++ b/x.js\n@@ -1,1 +1,3 @@\n a\n+  eval(x);\n+  console.log(1);\n"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['jobId'])")

curl -s -H "Authorization: Bearer $TOKEN" $BASE/v1/reviews/$JOB | python3 -m json.tool
```

### Providers

Set `"options": {"provider": "mock"}` (default) or `"options": {"provider": "llm"}`
in the request body. `mock` is deterministic and requires no external
configuration. `llm` calls Google Gemini and requires `GEMINI_API_KEY` to be
set; if unreachable or unconfigured, the job fails gracefully with a
descriptive error rather than crashing.

## Deployment

Deployed on Render (free tier), configuration in `render.yaml`. Kept awake
across the scoring window via an UptimeRobot ping to `/health` every 5
minutes. Runs as a single uvicorn worker — the job store, cache, and
idempotency registry are in-process, so a second worker would split them.

## Project structure

```
app/
  main.py          entry point, routes, error handlers
  config.py        single source of truth for limits declared in /spec
  auth.py          bearer token check
  errors.py        error envelope
  diff_parser.py   unified diff -> added lines with positions
  rules.py         the nine mock provider rules
  providers.py     mock and llm review providers
  jobs.py          async job store and background worker
  chunking.py      splits large diffs on file boundaries
  cache.py         result cache and idempotency registry
  ratelimit.py     token-bucket rate limiter
tests/             59 tests covering every layer + full HTTP integration
NOTES.md           running build log and design decisions
SUBMISSION.md       architecture, verification, AI usage, next steps
```
