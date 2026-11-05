# Phase 3c2: cited invoice arithmetic evidence

Status: opt-in `pdf-evidence-v4`, stacked after [bounded PDF OCR evidence](PHASE3_PDF_OCR_EVIDENCE.md). Existing v1–v3 jobs keep their stored versions and results.

## Scope and result

This first declared schema is `invoice-subtotal-tax-total-v1`. It looks for an invoice marker and exactly one explicitly labeled `Subtotal`, `Tax`, and `Total` or `Grand Total` amount, each with two decimal places. It checks `subtotal + tax = total` using decimal arithmetic. A mismatch is a **document field inconsistency observation**, not evidence of forgery, AI generation, nonpayment, or a false underlying claim. A match means only that these three extracted amounts reconcile. The top-level result remains `manual_review`, `Unknown`, with no paid model calls or calibrated score.

The task returns normalized amounts with page and line citations. OCR citations include pixel boxes. Text-layer citations identify page and extracted line; pypdf does not provide reliable character boxes in this path. The field result and the upstream OCR words may contain private financial information and follow the existing tenant-scoped result retention/deletion path. Text and parser exception prose are not logged.

The worker first runs v3. For at most four pages, text-layer pages are read by a separate credential-free pypdf child with a 512 MiB address-space/12 CPU-second limit, a 20-second parent wall timeout, a 96 KiB parent output limit, and per-page line/character caps. Image-only pages reuse v3's bounded OCR words. The original SHA-256 is checked before and after field reading. No additional provider call runs.

Arithmetic abstains if any PDF page is outside the four-page budget, unreadable, truncated, or missing; an amount label is missing or repeated; an OCR amount line has a word below 0.8 engine confidence; or an additional amount line signals shipping, discount, payment, credit, fee, balance, or a similar adjustment. `Amount Due` is not treated as `Total`, since payments can change it. Unknown layouts and currencies need a separate declared rule set. A missing invoice marker on a fully read PDF is `unsupported_document_type`; if reading is incomplete, the type remains inconclusive.

## Rollout

Deploy a v4-capable worker before setting `PDF_FIELD_PIPELINE_ENABLED=1` on the web service. This flag takes effect only with `PDF_EVIDENCE_PIPELINE_ENABLED=1`, `PDF_SIGNATURE_PIPELINE_ENABLED=1`, and `PDF_OCR_PIPELINE_ENABLED=1`. New PDF jobs store `pdf-evidence-v4` and use internal `queued_pdf_v4`; the public job status remains `queued`. Keep the flag off until durable PostgreSQL, private storage, authenticated intake and a separate worker are active. Do not show the rule output as a generic fraud score.

## Verification and promotion gate

`tests/test_pdf_invoice_fields.py` checks text-layer and scanned invoices, matching and edited totals, cited fields, missing/repeated labels, unsupported documents, extra charges, unread pages, and low OCR confidence. `tests/test_durable_backend.py` checks v4 queue versioning, idempotency and zero billed model calls. These are controlled fixtures. Before wider release, label an independent collection of real and edited invoices, including scans, mixed pages, multiple currencies, tax regimes, extra charges and duplicates. Measure field precision/recall, arithmetic false positives, abstention, page coverage and p95 latency. Extend schemas only after that evidence.
