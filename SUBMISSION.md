# SUBMISSION.md

## Architecture

FastAPI app with five layers:

1. **Parser** (`diff_parser.py`) — converts raw unified diff text into
   `(path, line, content)` triples for every added line. Structural
   boundaries (file sections, hunks) are determined by hunk-header
   arithmetic, never by scanning line content — this is what makes
   injected diff-like text inert.
2. **Rules** (`rules.py`) — the deterministic mock provider. Nine pattern
   checks against added lines, producing `Finding` objects.
3. **Providers** (`providers.py`) — swaps the analysis step only. `mock`
   uses the rules engine; `llm` sends the same added lines to Gemini and
   validates its output against the diff before trusting it. Everything
   else (parsing, chunking, ordering, caching, SSE) is provider-agnostic.
4. **Job pipeline** (`jobs.py`) — in-memory async job store. `POST
   /v1/reviews` returns immediately; a background `asyncio` task does the
   actual scan, capped at 4 concurrent via a semaphore.
5. **HTTP layer** (`main.py`) — routes, bearer auth (router-level
   dependency, not middleware, so SSE isn't affected), and a global error
   envelope covering all four failure paths.

Auth, rate limiting, and error handling are cross-cutting concerns applied
once at the router/app level rather than repeated per-route.

## Provider design

Both providers implement the same signature: given a list of parsed files
(added lines with positions), return a list of `Finding` objects. Nothing
outside `providers.py` knows which one ran.

**mock** — deterministic pattern matching against the nine rules in the
brief. This is what's scored; no external calls, no variance.

**llm** — sends added lines (path, line, content) to Gemini with a system
prompt describing the same nine rules and asking for JSON output. The
response is never trusted directly:

- Every `ruleId` is checked against the known rule table; unknown ids are
  dropped.
- Every `(path, line)` is checked against positions that actually exist
  in the diff; a hallucinated position is dropped rather than emitted.
- `severity`, `category`, and `evidence` are always taken from our own
  rule table and the actual diff content — never from the model's output
  — so a malformed or creative response can't corrupt the finding shape.

This means the model contributes judgement about *which* rule fires
*where*; everything structural about the resulting Finding is ours.

**Failure handling:** any provider failure (missing API key, network
error, timeout, non-200 response, unparseable output) raises a single
`ProviderError` with a human-readable message. `run_job` catches this
specifically and marks the job `failed` with that message — never a raw
stack trace, never a crash. Verified by unsetting `GEMINI_API_KEY` and
confirming a clean `failed` job, and separately by hitting a real
now-retired model name (`gemini-2.5-flash`), which produced a genuine
`404` end to end — an unplanned but useful real-world confirmation that
the failure path behaves as designed.

**Known limitation:** the mock provider's inertness against prompt
injection is structural (header-arithmetic parsing never interprets
content as instructions). The llm provider's inertness was verified
against crafted injection input and held, but it rests on the model's
instruction-following plus prompt framing, not a structural guarantee.

## Verification of cross-cutting behaviours

59 automated tests (`pytest`), covering every layer individually and the
full HTTP stack end to end via `TestClient`. Specific to the
cross-cutting requirements:

**Chunking** — `test_chunking_does_not_change_findings` scans the same
diff both chunked and unchunked and asserts identical, ordered finding
ids. `test_files_never_split_across_chunks` forces a tiny chunk limit and
confirms a file is never split across two chunks.

**Caching** — `test_identical_submission_is_cache_hit` submits the same
`{diff, options}` twice and asserts the second returns `cacheHit: true`
with identical findings. `maxFindings` is deliberately excluded from the
cache key, since it truncates on read and usage must reflect the full
scan regardless.

**Idempotency** — `test_same_key_same_body_returns_same_job` and
`test_same_key_different_body_is_409` cover both required behaviours of
the `Idempotency-Key` header, distinct from caching: idempotency returns
the *same* jobId; caching creates a new job that reports a cache hit.

**SSE replay** — `test_replay_is_identical` connects to a finished job's
stream three times and asserts byte-identical output. This works because
every job keeps its own event log (`Job.events`); live and replay
connections both just read that list — replay isn't a special code path.

**Rate limiting** — `test_declared_sustained_rate_all_succeed` confirms
30 rapid submissions all succeed (the declared sustained rate);
`test_burst_beyond_capacity_is_429` and `test_never_5xx_under_burst`
confirm the 429 path never degrades to a 5xx.

**Manual verification against the deployed service** (not just local
tests): full request/response cycles for `/health`, `/spec`, auth, the
mock provider, and the llm provider were run against the live Render URL
after each relevant deploy — see the two AI-suggestion corrections above,
both of which were only caught this way, not by local tests.

## AI tools used

**Claude** — used for the large majority of the
build. Design decisions (parser architecture, provider abstraction,
rate-limiter algorithm, etc.) were worked out in conversation before any
code was written, with reasoning and tradeoffs discussed explicitly.
Code was then written directly from that agreed design, reviewed, and
tested before moving to the next piece.

**Claude Code** — installed and authenticated, but not used to
autonomously generate features. Most implementation in this project came
through direct conversation rather than agentic delegation — a
deliberate choice to keep design ownership with me throughout, given
this project doubles as interview preparation.

**Discipline followed throughout:** design and reasoning happened before
implementation, not after; every file was read and tested (59 automated
tests) before moving on; two real AI-suggested details were wrong and
caught by testing against the running service rather than trusted at
face value:

1. **Render's `healthCheckPath: /health` setting.** Claude suggested
   pointing Render's health check at `/health` in `render.yaml`,
   reasoning that it already existed as a public endpoint. In
   production, this caused Render to intercept `GET /health` internally
   rather than forwarding it to the app — `/health` returned a
   plain-text 404 instead of the required JSON shape, while `/spec`
   (unaffected) worked correctly. That mismatch was the diagnostic clue.
   Rejected the setting and removed it entirely; `/health` now reaches
   the app like every other route.

2. **The Gemini model name (`gemini-2.5-flash`).** Claude picked this
   from general knowledge without checking it against my API key. It
   returned `404: "This model is no longer available to new users."` —
   a real API response, not a made-up limitation. Rather than guessing
   another name, I queried Google's `ListModels` endpoint directly with
   my key to get the actual list of callable models, then verified
   `gemini-flash-latest` returned a real 200. Also made the model name
   configurable via an environment variable so a future retirement
   doesn't require a redeploy mid-scoring-window.

**Pattern:** in both cases, the fix came from testing the actual running
service and reading the real error, not from re-guessing another AI
suggestion.

## What I'd do with more time

**Durable job storage.** Jobs, cache, and idempotency records are all
in-memory dicts, chosen deliberately for a 48-hour, single-process
service with no durability requirement in the brief. The real cost: a
Render restart loses everything in flight, and the service must run
with exactly one worker — two workers means two separate dicts, so a
client could submit to worker A and poll worker B and get a 404 for a
job that actually exists. With more time I'd put the store behind a
small interface and back it with Redis, which removes both constraints
at once: durability across restarts, and safety to scale to multiple
workers. The pipeline itself doesn't care where the data lives, only
`jobs.py` and `cache.py` would change.

**Per-client rate limiting.** The current limiter is a single global
token bucket, appropriate for a single-tenant service authenticated by
one bearer token. A multi-client version would key the bucket by token
or IP instead.

**MOCK-004's visibility limit.** The empty-catch rule only sees added
lines; a catch block whose body exists outside the diff is treated as
non-empty rather than guessed at. Correct given the constraint, but a
fuller implementation could optionally fetch surrounding file context
where available.

**LLM provider hardening.** Works and degrades gracefully, but a
production version would add retry-with-backoff for transient failures
(distinct from the permanent failures it already handles well), and
usage-based cost tracking now that requests are metered per call.

**Load testing.** All cross-cutting behaviours are unit- and
integration-tested, but I didn't run true concurrent load against the
deployed instance — real parallel traffic, not just automated-test-level
concurrency, would be the next thing I'd want to see before calling
concurrency handling fully proven.
