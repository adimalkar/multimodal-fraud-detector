# Visual screening evaluation plan

The current Gemma 4 26B A4B path is a low-call-cost **operational baseline**, not a validated AI-image detector. Its `Real`/`Fake` output and confidence are uncalibrated. Do not use either for automated claim decisions.

## Evidence and labels

1. Assemble a consented, provenance-tracked set of real camera images and AI-generated or edited images. Record original source, generator/edit tool and version, date, file hash, licensing, and any transformations. Keep unknown-provenance examples in a separate exploratory set, never as ground truth.
2. Include relevant insurance-like scenes and ordinary photos, scanned documents, and video clips. Label fully generated, locally edited, and authentic content separately. The current binary response cannot express these distinctions; report that limitation when scoring it.
3. Split by source and generator family, not just random image, to prevent near-duplicate leakage. Hold out new generators and sources. Add JPEG compression, screenshot/re-digitization, scaling, cropping, and social-media-like recompression slices.
4. Have independent reviewers adjudicate disputed labels without seeing model output. Preserve the adjudication record.

## Paired model and cost comparison

1. Freeze model ID, prompt, preprocessing, and test-set hashes. Run the current single-call baseline on a small, capped pilot first. Log OpenRouter-reported `usage.cost`, input/output tokens, latency, invalid responses, and failure rate per item; do not infer cost from text-token price alone because image token accounting and provider routing vary.
2. Compare a second low-cost vision model on the **same** items. Candidate IDs already allowlisted: `qwen/qwen3.5-flash-02-23` and `inclusionai/ling-3.0-flash-vl`. Recheck live price, availability, image support, and retention before spending. Use a dedicated OpenRouter key with a hard budget limit and model allowlist.
3. Measure class-wise precision/recall, false-positive rate on real claims, AUROC where suitable, abstention/invalid-response rate, and performance by generator, source, modality, and transformation. Report bootstrap confidence intervals. An uncalibrated model confidence is not a probability of fraud.
4. Only add a second paid vision call for an uncertainty band if it improves the held-out cost-quality frontier. A text critic reading the first model's description is not independent visual evidence. Compare an independent pixel-based detector or provenance signal under the same held-out protocol before calling any ensemble superior.

## Release gates

- Keep all results marked for human review until the false-positive rate and robustness meet an agreed product target on held-out data.
- Do not claim document forgery or full-video detection from a three-page/three-frame visual sample. Add modality-specific extraction and evaluation before those claims.
- Before public traffic: OpenRouter hard spend cap and model allowlist, application authentication, durable per-user quotas, and retention/privacy rules for uploaded evidence.

Research motivation: [AIGIBench](https://papers.neurips.cc/paper_files/paper/2025/hash/fb693c67f61e5321746ffce8b6fdd2d0-Abstract-Datasets_and_Benchmarks_Track.html) evaluates cross-source generalization and degradation; [RRDataset](https://openaccess.thecvf.com/content/ICCV2025/papers/Li_Bridging_the_Gap_Between_Ideal_and_Real-world_Evaluation_Benchmarking_AI-Generated_ICCV_2025_paper.pdf) reports performance declines after transmission and re-digitization. Those failure modes are directly relevant to claims media.
