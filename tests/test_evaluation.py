"""Evaluation gates that prevent leakage and optimistic detector claims."""

import hashlib
import json
from pathlib import Path

import pytest

from evaluation.registry import load_registry
from evaluation.run_baseline import run_pilot
from evaluation.score import paired_comparison, score_run


def _evidence(tmp_path: Path, item_id: str, label: str, **overrides) -> dict:
    evidence_path = tmp_path / f"{item_id}.jpg"
    evidence_path.write_bytes(item_id.encode())
    row = {
        "item_id": item_id,
        "relative_path": evidence_path.name,
        "sha256": hashlib.sha256(item_id.encode()).hexdigest(),
        "media_type": "image",
        "label": label,
        "split": "pilot",
        "source_group": item_id,
        "rights": "consented",
        "rights_reference": "test-consent-record",
        "generator_family": "generator-a" if label == "fully_generated" else None,
        "transformations": [],
    }
    row.update(overrides)
    return row


def _registry(tmp_path: Path, rows: list[dict]):
    manifest = tmp_path / "registry.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return load_registry(manifest, tmp_path)


def _prediction(item, classification: str | None, status="ok") -> dict:
    return {
        "item_id": item.item_id,
        "sha256": item.sha256,
        "model_id": "test-model",
        "pipeline_version": "test-v1",
        "registry_sha256": "a" * 64,
        "code_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
        "status": status,
        "classification": classification,
        "usage": {"cost": 0.01} if status == "ok" else {},
        "latency_ms": 50,
    }


def test_registry_rejects_changed_file_and_missing_rights(tmp_path):
    row = _evidence(tmp_path, "real", "authentic")
    _registry(tmp_path, [row])
    (tmp_path / "real.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _registry(tmp_path, [row])
    row["rights_reference"] = ""
    with pytest.raises(ValueError, match="rights_reference"):
        _registry(tmp_path, [row])


def test_registry_rejects_source_and_generator_split_leakage(tmp_path):
    real = _evidence(tmp_path, "real", "authentic")
    reused_source = _evidence(
        tmp_path, "real2", "authentic", split="test", source_group="real"
    )
    with pytest.raises(ValueError, match="source_group crosses splits"):
        _registry(tmp_path, [real, reused_source])
    fake = _evidence(tmp_path, "fake", "fully_generated")
    reused_generator = _evidence(
        tmp_path, "fake2", "fully_generated", split="test"
    )
    with pytest.raises(ValueError, match="generator_family crosses splits"):
        _registry(tmp_path, [fake, reused_generator])


def test_scoring_uses_evaluated_denominator_and_reports_coverage(tmp_path):
    items = _registry(
        tmp_path,
        [
            _evidence(tmp_path, "real1", "authentic"),
            _evidence(tmp_path, "real2", "authentic"),
            _evidence(tmp_path, "fake", "fully_generated"),
        ],
    )
    predictions = {
        items[0].item_id: _prediction(items[0], "Fake"),
        items[1].item_id: _prediction(items[1], None, "error"),
        items[2].item_id: _prediction(items[2], "Real"),
    }
    report = score_run(items, predictions, split="pilot")
    assert report["false_positive_rate_on_evaluated"]["estimate"] == 1.0
    assert report["generated_recall_on_evaluated"]["estimate"] == 0.0
    assert report["coverage"] == pytest.approx(2 / 3)
    assert report["review_or_missing"] == 1
    assert report["reported_cost_usd"] is None


def test_paired_comparison_rejects_different_item_sets(tmp_path):
    items = _registry(tmp_path, [_evidence(tmp_path, "real", "authentic")])
    with pytest.raises(ValueError, match="identical item IDs"):
        paired_comparison({items[0].item_id: _prediction(items[0], "Real")}, {})


def test_live_runner_requires_confirmed_provider_cap_before_any_call(tmp_path):
    with pytest.raises(ValueError, match="hard cap"):
        run_pilot(
            tmp_path / "missing.jsonl", tmp_path, tmp_path / "output.jsonl",
            model_id="google/gemma-4-26b-a4b-it", max_calls=1,
            max_observed_cost_usd=1,
        )
    assert not (tmp_path / "output.jsonl").exists()
