# Phase 3a: bounded PDF structure evidence

Status: opt-in implementation on the durable backend branch. Set `PDF_EVIDENCE_PIPELINE_ENABLED=1` on the **web service** only after the new worker and `pypdf==6.19.0` are deployed. New PDF jobs store `pdf-evidence-v1` and enter an internal `queued_pdf` state; older workers do not claim them. Clients see `queued`. Already queued jobs keep their stored pipeline version. The public service is not automatically switched by this PR.

## What runs

The worker rechecks the private original's SHA-256, then launches a separate Python process to inspect up to 20 PDF pages in a file of at most 20 MiB. The child receives a minimal environment without provider or storage credentials. It has a 512 MiB address-space limit and 12 CPU-second limit; the parent enforces a 25-second wall timeout. It uses the pinned [pypdf `PdfReader`](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html) and limits each decoded page content stream to 2 MiB before text extraction. The parser reports per-page inspection state, bounded text character counts, direct image XObject counts, and whether a form dictionary exists. It returns no document text or parser exception prose. The child is resource-limited but shares the worker container's user and filesystem; stronger OS isolation remains a deployment task.

The response distinguishes parsed, encrypted, excess-page, excess-file, and parser-error states. Pages skipped due to size or errors reduce coverage and make the structure task inconclusive. Text-layer, image-only, and mixed profiles are **candidates** based on visible structure; a blank text layer does not prove a scan. No OCR or page rendering runs in this phase. [pypdf warns that text extraction can consume much more memory than the decoded content stream](https://pypdf.readthedocs.io/en/stable/user/extract-text.html), which is why parsing runs in a bounded child process.

`document_integrity` and `document_field_consistency` remain inconclusive. No PDF signature, trust chain, revision, field value, or document authenticity is verified. The top-level result remains `manual_review`, classification `Unknown`, and zero external model calls. An unsigned or malformed document is not called fraudulent.

## Local verification and release gate

`tests/test_pdf_evidence.py` exercises real generated PDFs with a text layer, encryption, excess pages, excess content stream and malformed bytes. The durable API tests confirm the queued PDF version, no provider prerequisite, no billing start, and a mixed image/PDF batch when both evidence flags are on. These fixtures establish parser behavior, not fraud-detection accuracy.

Next PDF milestones: verify signatures and post-signature changes with an explicit trust configuration; render/OCR bounded pages with page coordinates; declare an invoice or receipt schema and test deterministic field rules. Build rights-cleared born-digital, scanned, mixed, signed, revised, and controlled-edit cases before any product verdict. Report page coverage, signature-state correctness, extraction/OCR error, field false positives, runtime, and local compute cost. The [implementation plan](MULTIMODAL_DETECTION_IMPLEMENTATION_PLAN.md) remains the release gate.
