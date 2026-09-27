# Phase 1 durable backend rollout

Status: implementation behind `DURABLE_JOBS_ENABLED=1`; **not enabled on the existing Render service**. The current site keeps its legacy API path until the production prerequisites below are configured and verified. This is a private-beta service-token boundary, not a public consumer login system.

## What this phase adds

- PostgreSQL-backed tenant-scoped jobs and batch children, with an explicit schema version, atomic daily job and reserved-cost quotas, idempotency keys, and `FOR UPDATE SKIP LOCKED` worker claims. PostgreSQL failure does not fall back to local SQLite in durable mode. The worker is a separate process and sends a database heartbeat; submissions and readiness reject when it is absent. `inline` execution is only for local development.
- Original-byte SHA-256 and private object keys. Uploads are bounded and checked against their declared extension's file signature before enqueueing. R2/S3 is required outside explicit local development mode. A batch has one parent and multiple independently claimed child jobs.
- Static bearer tokens mapped to tenant IDs for private beta. Job polling and deletion are owner-scoped. Arbitrary URL ingestion, public presigned uploads, the synchronous endpoint, and global analytics are disabled in durable mode because they could bypass ownership or expose other tenants' data. The existing frontend currently calls the backend directly and needs a server-side authenticated route before this mode can serve public visitors.
- A processing lease and billing boundary. Expired in-flight work becomes `WORKER_INTERRUPTED_REVIEW_REQUIRED` and is **never automatically retried**, since a provider call may already have been charged. Transient local I/O failures before billing can retry once; other failures require review. Completed results retain the legacy response shape plus a versioned, explicitly inconclusive task record and `manual_review` decision.
- Tenant deletion and a worker retention pass (default seven days) remove original evidence and job rows. The deletion path also cleans up any legacy analytics row previously written for that job. If deletion fails, the row stays in `deleting` for a later retry. A minimal tenant/time/cost usage ledger remains for the daily quota and is pruned after 90 days by default; it stores no filename, media or result. Durable job results are the only new analysis records in this mode; tenant-scoped analytics requires a separate design.

The account/provider hard spending limit remains essential. A per-job reservation and tenant budget are **admission controls**, not an exact upper bound on a provider invoice: image-token pricing, retries inside a provider, and missing usage reports can exceed the estimate. Do not claim guaranteed cost containment from the app quota alone.

## Local verification

Use a private development token of at least 32 characters. Keep it out of Git and browser code.

```bash
export DURABLE_JOBS_ENABLED=1
export DURABLE_ALLOW_LOCAL=1
export DURABLE_EXECUTION_MODE=inline
export DURABLE_SQLITE_PATH=/tmp/fraudsight-dev/jobs.db
export DURABLE_ARTIFACT_BACKEND=local
export DURABLE_ARTIFACT_DIR=/tmp/fraudsight-dev/evidence
export ANALYSIS_TOKENS_JSON='{"dev":"replace-with-a-random-token-of-at-least-32-characters"}'
uvicorn backend.app:app --reload
```

Submit with `Authorization: Bearer <token>`, then poll `/api/jobs/{job_id}` or `/api/batch/{batch_id}`. `Idempotency-Key` is optional and scoped to the tenant. `DELETE /api/jobs/{job_id}` and `DELETE /api/batch/{batch_id}` erase completed, failed or queued evidence; processing work returns 409 until it ends. Local `inline` mode still stores queue state and originals durably, but the process itself performs the work after the HTTP response. Run `python -m backend.durable_worker --once` against the same local database and artifact directory to exercise separate-process consumption.

## Production cutover checklist

1. Provision a persistent PostgreSQL database and private R2/S3 bucket. Configure the same `DURABLE_DATABASE_URL`, storage credentials/bucket and `OPENROUTER_API_KEY` on the web service and separate worker service. Add a bucket lifecycle rule **longer than job retention** for abandoned uploads: a web-process crash after object upload but before queue insertion can otherwise leave an unreferenced object. Do not use the ephemeral web filesystem or the SQLite fallback for production jobs.
2. Configure `ANALYSIS_TOKENS_JSON` only on the backend; create a server-side frontend route/session boundary that holds the tenant token. Never ship it as `NEXT_PUBLIC_*`, in browser JavaScript, or in a public presigned URL. Set `CORS_ALLOWED_ORIGINS` to the exact permitted origin(s) if direct cross-origin requests are retained for authenticated internal clients.
3. Set a provider account/key hard spend cap and verify it independently. Choose `DURABLE_DAILY_JOBS_PER_TENANT`, `DURABLE_DAILY_RESERVED_USD`, `DURABLE_RESERVE_PER_JOB_USD`, `DURABLE_MAX_BATCH_BYTES`, `DURABLE_RETENTION_DAYS`, and `DURABLE_USAGE_RETENTION_DAYS` for the private pilot. Reserve estimates must be revisited after Phase 0 measures actual provider-reported cost.
4. Deploy a **worker service** using `python -m backend.durable_worker` with the same database/storage credentials; leave `DURABLE_EXECUTION_MODE=external` on the web service. The current `render.yaml` describes only a web service and does not provision this worker or a database. Its build no longer seeds a local SQLite dataset; the durable worker initializes its PostgreSQL schema at startup. Enable `DURABLE_JOBS_ENABLED=1` only after the worker and frontend auth boundary are live.
5. Verify a restart, concurrent worker claim, tenant isolation, quota rejection, deletion and storage outage on staging. Then submit a capped real image job and confirm the original hash, model usage, job result, and deletion. Keep all results in manual review; no measured detector accuracy follows from these infrastructure tests.

Existing in-memory jobs cannot be recovered after the legacy web process exits. Historical `evidence` rows remain separate from durable jobs; the durable response carries `pipeline_version=screening-v1`. Tenant-scoped analytics and user login are required before public rollout. No live migration or production cutover is performed by this PR.

Reference: [PostgreSQL locking and `SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html).
