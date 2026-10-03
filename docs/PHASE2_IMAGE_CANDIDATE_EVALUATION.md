# Phase 2b: offline pixel-detector candidate

The image provenance branch still abstains on `synthetic_image`. This change adds an **offline research runner** for Nonescape Mini and makes the existing image scoring tool accept either a VLM prompt hash or a pixel-detector run-config hash. It does not enable a public detector or alter the product API.

## Candidate and rights gate

- Candidate: [Nonescape Mini](https://huggingface.co/e3ntity/nonescape-v0), an Apache-2.0-labelled 86,666,672-byte safetensors checkpoint at model revision `be8f32d0f8bd54f494e607e40c2e2fc1273fac56` with SHA-256 `7a0d0740c813ce199bc32ed16a5f4f4915895c4c9fdee0a98bdbeedd4f3631fd`.
- The adapter follows the publisher's [Python Mini architecture and preprocessing](https://github.com/e3ntity/nonescape/blob/52619d5c96ab83f018d9e879d4be14d847ccb15d/python/nonescape/__init__.py): EfficientNet V2-S, 1024-dimensional head, RGB, resize 256, center crop 224, JPEG quality 100, float scaling, ImageNet normalization, softmax class index 1. The publisher's browser ONNX preprocessing differs, so do not mix its outputs with this run.
- The [model card](https://huggingface.co/e3ntity/nonescape-v0) says the training set was over one million internet-scraped images. The Apache label on weights and code does not establish rights for that training data. **Commercial-use review remains open.** No model weights are committed, auto-downloaded, or deployed.
- The publisher's reported accuracy is not a project measurement. The raw synthetic score is uncalibrated; the default 0.5 threshold only reproduces the publisher's starting point.

## Reproduce an offline run

Use Python 3.11 or 3.12 in a separate environment. Install `evaluation/requirements-image-candidate.txt`, preferably using CPU-only PyTorch wheels for a CPU evaluation. Obtain the checkpoint from the pinned Hugging Face revision above into a private local path, then verify its SHA-256. The runner independently checks the pinned hash before loading it. It makes no provider requests.

```bash
python -m evaluation.run_image_candidate \
  --manifest /private/evidence/registry.jsonl \
  --data-root /private/evidence \
  --checkpoint /private/models/nonescape-mini-v0.safetensors \
  --output /private/evidence/runs/nonescape-mini-pilot.jsonl \
  --split pilot \
  --threshold 0.5

python -m evaluation.score \
  --manifest /private/evidence/registry.jsonl \
  --data-root /private/evidence \
  --predictions /private/evidence/runs/nonescape-mini-pilot.jsonl \
  --split pilot
```

The runner processes only registered `authentic` and `fully_generated` images. Each row binds the original file, registry, code, checkpoint, model/source revision, preprocessing and threshold. A decoding or inference failure becomes `error` with no classification. `model_load_ms` records one-time startup separately from per-image latency. `usage.cost = 0` means **no external API charge**; local compute, storage and hardware costs still need measurement. The output contains no image bytes or model prose. Keep paths and run files private because item IDs can reveal sources.

To compare it with the VLM baseline, run both on the same registered item IDs and use `evaluation.score --compare`. Register a rights-cleared independent pilot first, choose a threshold on `validation`, then freeze it before the locked `test` split. Do not use publisher examples or mock fixtures as evidence of accuracy. Report false positives, generated-image recall by source and transformation, coverage, p95 latency, and local operating cost before considering any product rollout. The model-rights review, dataset, accuracy gate, and production integration remain pending.
