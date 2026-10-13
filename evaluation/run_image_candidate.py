"""Offline, pinned Nonescape Mini image candidate; never used by the product API."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import time
from pathlib import Path
from typing import Callable

from evaluation.registry import load_registry

MODEL_ID = "e3ntity/nonescape-mini-v0"
MODEL_REVISION = "be8f32d0f8bd54f494e607e40c2e2fc1273fac56"
SOURCE_REVISION = "52619d5c96ab83f018d9e879d4be14d847ccb15d"
CHECKPOINT_SHA256 = "7a0d0740c813ce199bc32ed16a5f4f4915895c4c9fdee0a98bdbeedd4f3631fd"
PIPELINE_VERSION = "nonescape_mini_python_eval_v1"
PREPROCESSING = {
    "color": "PIL RGB",
    "resize": "torchvision.transforms.v2.Resize(256)",
    "crop": "torchvision.transforms.v2.CenterCrop(224)",
    "jpeg": "torchvision.transforms.v2.JPEG(quality=100)",
    "dtype": "torch.float32 scale=True",
    "normalize_mean": [0.485, 0.456, 0.406],
    "normalize_std": [0.229, 0.224, 0.225],
}
RUNTIME_VERSIONS = {
    "torch": "2.7.1",
    "torchvision": "0.22.1",
    "safetensors": "0.5.3",
    "Pillow": "11.3.0",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_classifier(checkpoint: Path) -> Callable[[Path], float]:
    """Reproduce the publisher's Mini architecture and Python preprocessing.

    Dependencies are optional and isolated from the production API. The
    checkpoint is verified by the caller before safetensors loads it.
    """
    for package, expected in RUNTIME_VERSIONS.items():
        installed = importlib.metadata.version(package).split("+", 1)[0]
        if installed != expected:
            raise RuntimeError(f"{package} version differs from the pinned evaluation environment")

    import torch
    from PIL import Image
    from safetensors.torch import load_file
    from torch import nn
    from torchvision import models
    from torchvision.transforms import v2 as transforms

    transform = transforms.Compose([
        transforms.ToImage(),
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.JPEG(quality=100),
        transforms.ToDtype(torch.float32, scale=True),
        transforms.Normalize(mean=PREPROCESSING["normalize_mean"], std=PREPROCESSING["normalize_std"]),
    ])

    class Mini(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = models.efficientnet_v2_s(
                weights=None, num_classes=1024, dropout=0.2
            )
            self.head = nn.Linear(1024, 2)

        def forward(self, pixels):
            return self.head(self.backbone(pixels))

    model = Mini()
    model.load_state_dict(load_file(str(checkpoint)), strict=True)
    model.eval()

    def predict(path: Path) -> float:
        with Image.open(path) as source:
            pixels = transform(source.convert("RGB")).unsqueeze(0)
        with torch.inference_mode():
            logits = model(pixels)
            return float(torch.softmax(logits, dim=-1)[0, 1].item())

    return predict


def run_candidate(
    manifest: Path,
    data_root: Path,
    output: Path,
    *,
    checkpoint: Path,
    split: str,
    threshold: float,
    expected_checkpoint_sha256: str = CHECKPOINT_SHA256,
    predictor_factory: Callable[[Path], Callable[[Path], float]] = load_classifier,
) -> int:
    """Run on registered images only, with no network or paid provider calls."""
    if split not in {"pilot", "validation", "test"}:
        raise ValueError("Invalid evaluation split")
    if not math.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("Threshold must be between zero and one")
    if output.exists():
        raise ValueError("Output already exists; use a new run file")
    if _sha256_file(checkpoint) != expected_checkpoint_sha256:
        raise ValueError("Checkpoint SHA-256 does not match the pinned model")
    items = load_registry(manifest, data_root)
    selected = [item for item in items if item.split == split and item.media_type == "image"
                and item.label in {"authentic", "fully_generated"}]
    if not selected:
        raise ValueError(f"No scoreable images in split {split}")

    config = {
        "checkpoint_sha256": expected_checkpoint_sha256,
        "model_revision": MODEL_REVISION,
        "source_revision": SOURCE_REVISION,
        "preprocessing": PREPROCESSING,
        "runtime_versions": RUNTIME_VERSIONS,
        "threshold": threshold,
        "threshold_origin": "publisher_default" if threshold == 0.5 else "operator_selected",
    }
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    registry_hash = _sha256_file(manifest)
    code_hash = _sha256_file(Path(__file__))
    load_started = time.perf_counter()
    predict = predictor_factory(checkpoint)
    model_load_ms = round((time.perf_counter() - load_started) * 1000, 1)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        for item in selected:
            row = {
                "item_id": item.item_id,
                "sha256": item.sha256,
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "source_revision": SOURCE_REVISION,
                "checkpoint_sha256": expected_checkpoint_sha256,
                "pipeline_version": PIPELINE_VERSION,
                "registry_sha256": registry_hash,
                "code_sha256": code_hash,
                "run_config_sha256": config_hash,
                "threshold": threshold,
                "model_load_ms": model_load_ms,
                "status": "error",
                "classification": None,
                "synthetic_score_raw": None,
                "usage": {"cost": 0.0, "cost_basis": "external_api_only"},
                "latency_ms": None,
            }
            started = time.perf_counter()
            try:
                score = predict((data_root / item.relative_path).resolve())
                if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Candidate returned an invalid synthetic score")
                row["synthetic_score_raw"] = float(score)
                row["classification"] = "Fake" if score > threshold else "Real"
                row["status"] = "ok"
            except Exception as error:
                row["error_type"] = type(error).__name__
            row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
    return len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--split", choices=["pilot", "validation", "test"], required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    count = run_candidate(
        args.manifest, args.data_root, args.output, checkpoint=args.checkpoint,
        split=args.split, threshold=args.threshold,
    )
    print(json.dumps({"attempted_images": count, "output": os.fspath(args.output)}))


if __name__ == "__main__":
    main()
