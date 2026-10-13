# Phase 0: offline evaluation foundation

This directory records *measured* detector behavior separately from the product API. No dataset or model result is bundled, and the current baseline is not validated. The first implemented task is authentic-versus-fully-generated **images**. Video and PDF evidence can be registered now, but their distinct labels and metrics will be implemented in their modality phases. Generic PDF fraud scoring is deliberately absent.

## Registry

Keep evidence files and the registry outside Git, in a private directory. Each JSONL line has this shape:

```json
{"item_id":"image-001","relative_path":"images/image-001.jpg","sha256":"<64-character SHA-256>","media_type":"image","label":"authentic","split":"pilot","source_group":"capture-session-001","rights":"consented","rights_reference":"consent-record-001","generator_family":null,"parent_id":null,"transformations":[]}
```

- `label`: `authentic`, `fully_generated`, `locally_edited`, `face_manipulated`, or `field_tampered`. Generated media require `generator_family`; PDFs require a document-specific label.
- `split`: `pilot`, `validation`, or locked `test`. A source group, identical file hash, or generator family cannot cross splits. The same source group should cover an original and all of its transformed versions. `parent_id` links a derived version to its registered original.
- `rights`: `consented` or `public_license`; `rights_reference` points to the permission or license record. The registry checks that a reference is present, but the dataset curator must verify that it actually grants the intended research/product use.
- Record the generator or edit tool/version and document subtype in a separate private provenance ledger until the task schemas are extended. Unknown-origin web assets cannot be treated as ground truth.

`load_registry` checks the current file SHA-256 and refuses paths escaping the data root. Keep the registry and run files private: identifiers and paths can reveal sensitive evidence sources.

Validate the registry without any model call:

```bash
python -m evaluation.registry --manifest /private/evidence/registry.jsonl --data-root /private/evidence
```

## Collect the current image baseline

First configure a hard spend cap on the OpenRouter account/key and use a local environment variable for `OPENROUTER_API_KEY`. The observed-cost option below is a **post-response stop rule**; it cannot prevent the first request from exceeding that amount. The provider hard cap is the pre-call money boundary. No requests run without the explicit flag.

```bash
python -m evaluation.run_baseline \
  --manifest /private/evidence/registry.jsonl \
  --data-root /private/evidence \
  --output /private/evidence/runs/baseline-v1.jsonl \
  --model-id google/gemma-4-26b-a4b-it \
  --max-calls 20 \
  --max-observed-cost-usd 2 \
  --account-hard-cap-confirmed
```

The runner processes only `pilot` images with authentic or fully-generated labels. It records file, registry, code and prompt hashes, model and pipeline version, classification, uncalibrated model confidence, provider usage, latency and error type. It omits image bytes and model prose. It stops on the first missing cost report or error; use a new output filename for each run. The runner is deliberately unsuitable for automated policy decisions. Provider routing may still vary behind a model ID and must be logged if the provider exposes it later.

## Score and compare

```bash
python -m evaluation.score \
  --manifest /private/evidence/registry.jsonl \
  --data-root /private/evidence \
  --predictions /private/evidence/runs/baseline-v1.jsonl \
  --split pilot
```

Use `--compare other-run.jsonl` to score a second model on the same item IDs and report paired disagreements. False-positive rate and generated-image recall use **evaluated** items as denominators; `coverage` and `review_or_missing` expose missing/errored items. The Wilson intervals are descriptive and can be wide on a small pilot. `reported_cost_usd` is `null` if any attempted call lacks a provider cost. Model confidence is never interpreted as a calibrated probability. Do not tune thresholds on the locked test split.

## Phase 0 completion evidence

The harness and leakage checks are ready, but the phase's accuracy gate remains open until there is a rights-cleared labeled pilot and provider-reported cost data. The dataset and target false-positive/coverage/latency/spend limits must be recorded before claiming an improved detector. Reuse the same item set, preprocessing and rights constraints for candidate comparisons.

The offline Phase 2b pixel-detector candidate and its unresolved commercial-rights gate are documented in [`docs/PHASE2_IMAGE_CANDIDATE_EVALUATION.md`](../docs/PHASE2_IMAGE_CANDIDATE_EVALUATION.md).
