# Phase 2a: original-byte image provenance

Status: opt-in implementation on top of the durable job branch. Set `IMAGE_EVIDENCE_PIPELINE_ENABLED=1` on the **web service** after enabling durable jobs and deploying the new worker code. The web service writes `image-evidence-v1` into each newly queued image job; a worker chooses the pipeline from that stored version, so changing a flag does not change work already queued. Image jobs use an internal `queued_image` state that older workers do not claim; clients still see `queued`. If only old workers remain, image jobs wait safely until a new worker is available. Other modalities still use the existing screening path. The current public service remains on the legacy path.

## What runs

For JPEG, PNG and WebP uploads, the worker reads the private original, checks its SHA-256 against the intake record, and uses pinned `c2pa-python==0.37.12` to verify an embedded Content Credential. Trust checking remains enabled. Remote manifest and OCSP network fetching are disabled. The response distinguishes `valid_trusted`, `valid_untrusted`, `invalid`, `absent`, `unsupported`, and `verification_error`, includes only bounded validation failure codes and the original hash, and records that only embedded manifests were checked. The image receives a separate `synthetic_image` task with an inconclusive finding and no score. The top-level decision is `manual_review`; no hosted model is called or billed for this image path.

The SDK's `Trusted` state means that its configured trust roots accepted the signature, while `Valid` means the manifest validated without a trusted signer. A verified signature concerns provenance and integrity of the signed asset; it does not prove that the scene is real, that an expense is genuine, or that no AI tools were used. An absent or invalid credential does not prove synthesis. Offline verification cannot check remote manifests or fresh revocation state. See the [SDK Reader API](https://contentauth.github.io/c2pa-python/api/c2pa/c2pa/index.html), [context settings](https://github.com/contentauth/c2pa-python/blob/main/docs/context-settings.md), and [Reader state reference](https://contentauth.github.io/json-manifest-reference/reader-ref).

`tests/fixtures/c2pa_valid_untrusted.jpg` is a generated 16 × 16 JPEG signed with the public development certificate from the [MIT or Apache licensed upstream SDK test fixtures](https://github.com/contentauth/c2pa-python/tree/main/tests/fixtures). It tests verification behavior only; it is not a labeled authentic or AI-generated sample. Tests also alter its signed JPEG bytes to confirm that the SDK reports a hash mismatch.

## Still required for the image release gate

- Build a rights-cleared, independently labeled image set with camera, generated, edit, screenshot and recompression strata. The existing evaluation registry can enforce hashes, rights and split boundaries; none of its smoke fixtures measures detector accuracy.
- Select a commercially usable pixel detector **including checkpoint, backbone and training-data rights**, then add a pinned preprocessing/adapter and run it against the existing VLM baseline on paired held-out examples. Measure false positives, recall by source and transformation, abstention, runtime and cost before exposing a score.
- Evaluate local edit and face manipulation with separate labels and localization metrics. They are currently `not_checked`; whole-image provenance cannot answer either question.
- Test current C2PA trust roots, real trusted and revoked fixtures, remote-manifest policy, and malformed inputs in a staging worker with CPU/memory/time limits. The checked-in fixture verifies the valid-untrusted and tamper states only.

This implementation is a no-cost provenance check and an explicit abstention, **not an AI-image detector**. Keep it behind the opt-in flag and manual review while the image evaluation gate is open.
