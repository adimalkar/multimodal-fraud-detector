# Phase 3b: offline PDF signature evidence

Status: opt-in implementation on the durable backend PR stack. This phase extends the [PDF structure path](PHASE3_PDF_EVIDENCE.md) without changing its stored `pdf-evidence-v1` results.

## What it reports

`pdf-evidence-v2` runs the same bounded structure check, then asks pinned `pyHanko==0.37.0` to inspect up to eight embedded signatures. Each signature has a separate cryptographic integrity result, trust result, coverage state, post-signature-update observation, modification level, and document permission result. Trust roots come only from an explicit local PEM/DER bundle. With no bundle, trust is `not_configured`; the worker does not fall back to operating-system TLS roots. Certificate fetching is disabled, and online revocation is not checked. A valid signature says nothing about the accuracy of an invoice or other claim. An unsigned document is ordinary. A later incremental update may be benign; the reviewer sees the update and permission observations without an automatic fraud label. These distinctions follow [pyHanko's validation API](https://docs.pyhanko.eu/en/latest/lib-guide/validation/general-api.html) and [revision analysis guidance](https://docs.pyhanko.eu/en/latest/lib-guide/validation/diff-analysis.html).

The worker verifies the original SHA-256 before and after analysis. The signature parser runs in a child process with a minimal environment that excludes provider and storage credentials, 512 MiB address-space and 12 CPU-second limits, plus a 25-second parent timeout. The result contains no signer name, certificate bytes, document text, parser exception prose, or local paths. Signature verification is skipped if the structure check was incomplete. The child still shares the worker container's filesystem and user; deployment-level isolation is a later hardening task.

The top-level result remains `manual_review`, classification `Unknown`, and zero paid model calls. `document_field_consistency` remains inconclusive. This phase does not classify AI-generated images inside a PDF, run OCR, verify C2PA, or validate document facts.

## Deployment order

1. Deploy the new worker with `pyHanko==0.37.0` and confirm it is healthy. Existing `queued_pdf` jobs continue to use v1.
2. On the web service, set `PDF_EVIDENCE_PIPELINE_ENABLED=1` and `PDF_SIGNATURE_PIPELINE_ENABLED=1`. New PDF jobs store `pdf-evidence-v2` and enter internal state `queued_pdf_v2`; old workers do not claim that state. Clients continue to see `queued`.
3. On the worker, optionally set `PDF_SIGNATURE_TRUST_ROOTS_PATH` to an absolute path to a reviewed, locally mounted PEM/DER trust bundle no larger than 1 MiB. Configure trust policy for the issuers and document types you actually accept. A missing or invalid bundle gives a typed verification error, not implicit trust. The result records the bundle SHA-256, since rotating roots changes interpretation; rerun validation before combining trusted-signature counts in analytics.
4. Keep the feature flag off if the worker or trust policy is not ready. Turning it off routes new submissions to v1; already queued v2 jobs retain their version. Do not enable a public fraud verdict from this flag.

## Local gate and next milestone

`tests/test_pdf_signature_evidence.py` creates real signed PDFs and checks unsigned, valid without roots, valid with explicit roots, byte-altered signature, incremental revision, invalid trust bundle, and child environment isolation. `tests/test_durable_backend.py` checks the versioned queue, idempotency, no provider prerequisite, and zero billed model calls. These fixtures establish behavior, not field accuracy or fraud-detection quality.

Next: bounded PDF rendering and OCR with page coordinates, then a declared invoice or receipt schema and deterministic field rules. Before promotion, measure signature-state correctness against a larger corpus with multiple issuers and revision types, parser error/coverage, p95 runtime, and document-field false positives. The [implementation plan](MULTIMODAL_DETECTION_IMPLEMENTATION_PLAN.md) remains the release gate.
