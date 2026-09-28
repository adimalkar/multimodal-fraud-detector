"""Score frozen model outputs without making model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

from evaluation.registry import EvidenceItem, load_registry


def _wilson(successes: int, total: int) -> dict | None:
    if total == 0:
        return None
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return {"estimate": p, "ci95": [max(0.0, center - radius), min(1.0, center + radius)]}


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil(fraction * len(ordered)) - 1
    return ordered[max(0, index)]


def load_predictions(path: Path) -> dict[str, dict]:
    predictions: dict[str, dict] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Prediction line {line_number}: invalid JSON") from error
            if not isinstance(row, dict) or not isinstance(row.get("item_id"), str):
                raise ValueError(f"Prediction line {line_number}: missing item_id")
            if row["item_id"] in predictions:
                raise ValueError(f"Prediction line {line_number}: duplicate item_id")
            if row.get("status") not in {"ok", "unpriced", "error", "inconclusive"}:
                raise ValueError(f"Prediction line {line_number}: invalid status")
            if row.get("classification") not in {None, "Real", "Fake"}:
                raise ValueError(f"Prediction line {line_number}: invalid classification")
            if row["status"] in {"ok", "unpriced"} and row["classification"] is None:
                raise ValueError(f"Prediction line {line_number}: missing classification")
            if row["status"] in {"error", "inconclusive"} and row["classification"] is not None:
                raise ValueError(f"Prediction line {line_number}: unexpected classification")
            if not isinstance(row.get("usage"), dict):
                raise ValueError(f"Prediction line {line_number}: usage must be an object")
            predictions[row["item_id"]] = row
    return predictions


def score_run(
    items: list[EvidenceItem], predictions: dict[str, dict], *, split: str,
    expected_registry_sha256: str | None = None,
) -> dict:
    """Score authentic-vs-fully-generated images only; no fraud inference."""
    selected = {
        item.item_id: item for item in items
        if item.split == split and item.media_type == "image"
        and item.label in {"authentic", "fully_generated"}
    }
    if not selected:
        raise ValueError(f"No scoreable images in split {split}")
    if not predictions or not set(predictions).issubset(selected):
        raise ValueError("Predictions must be a nonempty subset of scoreable items in this split")
    model_ids = {row.get("model_id") for row in predictions.values()}
    versions = {row.get("pipeline_version") for row in predictions.values()}
    registry_hashes = {row.get("registry_sha256") for row in predictions.values()}
    code_hashes = {row.get("code_sha256") for row in predictions.values()}
    prompt_hashes = {row.get("prompt_sha256") for row in predictions.values()}
    if len(model_ids) != 1 or None in model_ids or len(versions) != 1 or None in versions:
        raise ValueError("Run must have one model ID and one pipeline version")
    for name, hashes in (
        ("registry", registry_hashes), ("code", code_hashes), ("prompt", prompt_hashes)
    ):
        if len(hashes) != 1 or not isinstance(next(iter(hashes)), str):
            raise ValueError(f"Run has missing or mixed {name} hashes")
    if expected_registry_sha256 and registry_hashes != {expected_registry_sha256}:
        raise ValueError("Prediction registry hash differs from current manifest")

    authentic_count = sum(item.label == "authentic" for item in selected.values())
    generated_count = len(selected) - authentic_count
    fp = tp = evaluated_authentic = evaluated_generated = errors = unpriced = 0
    latencies: list[float] = []
    costs: list[float] = []
    slices: dict[str, dict[str, int]] = {}
    for item_id, row in predictions.items():
        item = selected[item_id]
        if row.get("sha256") != item.sha256:
            raise ValueError(f"Prediction SHA-256 mismatch for {item_id}")
        classification = row.get("classification")
        status = row["status"]
        if status == "error":
            errors += 1
        if status == "unpriced":
            unpriced += 1
        if status not in {"ok", "unpriced"} or classification is None:
            continue
        if item.label == "authentic":
            evaluated_authentic += 1
        else:
            evaluated_generated += 1
        if classification == "Fake" and item.label == "authentic":
            fp += 1
        if classification == "Fake" and item.label == "fully_generated":
            tp += 1
        latency = row.get("latency_ms")
        if (
            isinstance(latency, (int, float)) and not isinstance(latency, bool)
            and math.isfinite(latency) and latency >= 0
        ):
            latencies.append(float(latency))
        cost = (row.get("usage") or {}).get("cost")
        if (
            isinstance(cost, (int, float)) and not isinstance(cost, bool)
            and math.isfinite(cost) and cost >= 0
        ):
            costs.append(float(cost))
        slice_name = item.generator_family if item.label == "fully_generated" else "authentic"
        bucket = slices.setdefault(slice_name, {"total": 0, "fake_predictions": 0})
        bucket["total"] += 1
        bucket["fake_predictions"] += int(classification == "Fake")
    return {
        "split": split,
        "task": "synthetic_image_screening",
        "model_id": next(iter(model_ids)),
        "pipeline_version": next(iter(versions)),
        "registry_sha256": next(iter(registry_hashes)),
        "code_sha256": next(iter(code_hashes)),
        "prompt_sha256": next(iter(prompt_hashes)),
        "items": len(selected),
        "attempted_items": len(predictions),
        "authentic_items": authentic_count,
        "generated_items": generated_count,
        "evaluated_authentic": evaluated_authentic,
        "evaluated_generated": evaluated_generated,
        "false_positives": fp,
        "true_positives": tp,
        "false_positive_rate_on_evaluated": _wilson(fp, evaluated_authentic),
        "generated_recall_on_evaluated": _wilson(tp, evaluated_generated),
        "review_or_missing": len(selected) - evaluated_authentic - evaluated_generated,
        "error_count": errors,
        "unpriced_count": unpriced,
        "coverage": (evaluated_authentic + evaluated_generated) / len(selected),
        "reported_cost_usd": sum(costs) if len(costs) == len(predictions) else None,
        "p50_latency_ms": statistics.median(latencies) if latencies else None,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "slices": slices,
        "limitations": [
            "The VLM confidence is uncalibrated.",
            "This compares fully generated vs authentic images only, not fraud or local edits.",
        ],
    }


def paired_comparison(left: dict[str, dict], right: dict[str, dict]) -> dict:
    if set(left) != set(right):
        raise ValueError("Paired runs must contain identical item IDs")
    comparable = disagreement = 0
    for item_id in left:
        a, b = left[item_id], right[item_id]
        if a.get("sha256") != b.get("sha256"):
            raise ValueError(f"Paired runs have different evidence for {item_id}")
        if a.get("status") in {"ok", "unpriced"} and b.get("status") in {"ok", "unpriced"}:
            comparable += 1
            disagreement += int(a.get("classification") != b.get("classification"))
    return {"comparable_items": comparable, "disagreements": disagreement}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--split", choices=["pilot", "validation", "test"], required=True)
    args = parser.parse_args()
    items = load_registry(args.manifest, args.data_root)
    registry_sha256 = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    predictions = load_predictions(args.predictions)
    report = score_run(
        items, predictions, split=args.split,
        expected_registry_sha256=registry_sha256,
    )
    if args.compare:
        other = load_predictions(args.compare)
        report["comparison"] = {
            "other": score_run(
                items, other, split=args.split,
                expected_registry_sha256=registry_sha256,
            ),
            "paired": paired_comparison(predictions, other),
        }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
