# Phase 3c1: bounded PDF OCR evidence

Status: opt-in implementation stacked after [PDF signature evidence](PHASE3_PDF_SIGNATURE_EVIDENCE.md). It adds `pdf-evidence-v3` without changing stored v1 or v2 results.

## What runs

The worker checks the original SHA-256 and runs the v2 structure and signature tasks. A separate, credential-free child selects at most four pages with fewer than 20 extractable text characters. It renders each selected page with Poppler `pdftoppm` at a maximum edge of 1,400 pixels and reads English words with Tesseract TSV output. The child returns page number, temporary render hash and dimensions, bounded words with pixel boxes and OCR confidence, and explicit page, word and error coverage. Pages with a text layer are skipped; additional eligible pages are listed as skipped by budget. Images and TSV files are removed when the child exits. Poppler's [page and scaling flags](https://manpages.debian.org/testing/poppler-utils/pdftoppm.1.en.html) and Tesseract's [TSV word boxes and confidence](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html#tsv-output) are the underlying interfaces.

The child has a 512 MiB address-space limit, a 30 CPU-second limit and an 8 MiB file-size limit. Each renderer/OCR command has a 15-second timeout; the parent has a 75-second wall timeout and kills the child process group if it expires. Rendering is limited to an 8 MiB PNG. TSV output is limited to 256 KiB. At most 100 words per page and 64 characters per word appear in the result. The result records the installed Poppler and Tesseract version strings. Decoder isolation still relies on the worker container's user and filesystem; a separate sandbox remains a deployment task.

OCR text can contain personal or financial details. The durable result is tenant-scoped and subject to the existing evidence-retention and deletion path. The child receives no provider or storage credentials; document text and parser exception prose are not logged. Reviewers should treat OCR confidence as an engine observation, not an authenticity score. A blank page, missing text, OCR error or truncated output is not evidence of fraud.

The `document_field_consistency` task remains inconclusive. No invoice totals, dates or vendor identity are checked in this phase. The top-level result remains `manual_review`, classification `Unknown`, and zero paid model calls.

## Rollout

1. Deploy the updated worker and container image with `poppler-utils` and `tesseract-ocr` before enabling v3 on the web service. The binaries are required only for the OCR path; a missing binary produces a typed `unsupported` OCR result.
2. On the web service, enable `PDF_EVIDENCE_PIPELINE_ENABLED=1`, `PDF_SIGNATURE_PIPELINE_ENABLED=1`, then `PDF_OCR_PIPELINE_ENABLED=1`. New PDF jobs store `pdf-evidence-v3` and use internal `queued_pdf_v3`, which older workers cannot claim. Clients still see `queued`; v1/v2 jobs keep their stored version.
3. Keep public rollout gated on the durable backend's PostgreSQL, private storage, separate worker and authentication prerequisites. If the worker is not ready, leave the flag off. Do not turn OCR output into an AI-generated or fraud label.

## Verification and next milestone

`tests/test_pdf_ocr_evidence.py` uses real image-only PDFs to check recognized words and boxes, five-page budget coverage, text-layer skipping, malformed input, missing tools and credential isolation. `tests/test_durable_backend.py` checks v3 queue versioning, idempotency and zero billed model calls. These fixtures establish OCR plumbing, not extraction accuracy on representative documents.

The [v4 invoice-field follow-up](PHASE3_PDF_INVOICE_FIELDS.md) adds one declared schema, cited amounts and conservative arithmetic. Extraction error and false-positive rates on independently labeled documents remain unmeasured; a document verdict remains outside this phase.
