"""Offline candidate provenance and scoring gates (no model or dataset bundled)."""

import hashlib
import json

import pytest

from evaluation.run_image_candidate import run_candidate
from evaluation.registry import load_registry
from evaluation.score import load_predictions, score_run


def _registry(tmp_path):
    rows = []
    for item_id, label in (("real", "authentic"), ("generated", "fully_generated")):
        data = item_id.encode()
        (tmp_path / f"{item_id}.jpg").write_bytes(data)
        rows.append({
            "item_id": item_id,
            "relative_path": f"{item_id}.jpg",
            "sha256": hashlib.sha256(data).hexdigest(),
            "media_type": "image",
            "label": label,
            "split": "pilot",
            "source_group": item_id,
            "rights": "consented",
            "rights_reference": "test-fixture",
            "generator_family": "test-generator" if label == "fully_generated" else None,
            "transformations": [],
        })
    manifest = tmp_path / "registry.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return manifest


def test_candidate_requires_pinned_checkpoint_before_output(tmp_path):
    manifest = _registry(tmp_path)
    checkpoint = tmp_path / "checkpoint.safetensors"
    checkpoint.write_bytes(b"wrong weights")
    output = tmp_path / "run.jsonl"
    with pytest.raises(ValueError, match="Checkpoint SHA-256"):
        run_candidate(
            manifest, tmp_path, output, checkpoint=checkpoint, split="pilot",
            threshold=0.5,
        )
    assert not output.exists()


def test_candidate_records_raw_scores_and_scores_same_registered_items(tmp_path):
    manifest = _registry(tmp_path)
    checkpoint = tmp_path / "checkpoint.safetensors"
    checkpoint.write_bytes(b"fixture weights")
    checkpoint_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    output = tmp_path / "run.jsonl"
    values = {"real.jpg": 0.2, "generated.jpg": 0.8}
    count = run_candidate(
        manifest, tmp_path, output, checkpoint=checkpoint, split="pilot",
        threshold=0.5, expected_checkpoint_sha256=checkpoint_hash,
        predictor_factory=lambda _: lambda path: values[path.name],
    )
    assert count == 2
    predictions = load_predictions(output)
    assert predictions["real"]["synthetic_score_raw"] == 0.2
    assert predictions["generated"]["classification"] == "Fake"
    assert {row["checkpoint_sha256"] for row in predictions.values()} == {checkpoint_hash}
    report = score_run(
        load_registry(manifest, tmp_path), predictions, split="pilot",
        expected_registry_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    assert report["coverage"] == 1
    assert report["false_positives"] == 0
    assert report["true_positives"] == 1
    assert report["reported_cost_usd"] == 0
    with pytest.raises(ValueError, match="already exists"):
        run_candidate(
            manifest, tmp_path, output, checkpoint=checkpoint, split="pilot",
            threshold=0.5, expected_checkpoint_sha256=checkpoint_hash,
        )


def test_invalid_candidate_output_abstains_and_keeps_error_type(tmp_path):
    manifest = _registry(tmp_path)
    checkpoint = tmp_path / "checkpoint.safetensors"
    checkpoint.write_bytes(b"fixture weights")
    output = tmp_path / "run.jsonl"
    run_candidate(
        manifest, tmp_path, output, checkpoint=checkpoint, split="pilot",
        threshold=0.5, expected_checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        predictor_factory=lambda _: lambda path: float("nan") if path.name == "real.jpg" else 0.8,
    )
    predictions = load_predictions(output)
    assert predictions["real"]["status"] == "error"
    assert predictions["real"]["classification"] is None
    assert predictions["real"]["error_type"] == "ValueError"
    report = score_run(load_registry(manifest, tmp_path), predictions, split="pilot")
    assert report["coverage"] == 0.5
