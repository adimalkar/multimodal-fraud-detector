"""Opt-in, no-model PDF structure evidence; authenticity remains undetermined."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from backend.pdf_probe import MAX_PAGES, PYPDF_VERSION

PDF_PIPELINE_VERSION = "pdf-evidence-v1"
PDF_POLICY_VERSION = "manual-review-v1"
MAX_PDF_BYTES = 20 * 1024 * 1024
PROBE_TIMEOUT_SECONDS = 25


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _probe(path: Path) -> dict:
    try:
        process = subprocess.run(
            [sys.executable, "-m", "backend.pdf_probe", str(path)],
            cwd=Path(__file__).resolve().parent.parent,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1"},
            timeout=PROBE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"state": "parse_error", "error_type": "TimeoutExpired"}
    if process.returncode != 0 or len(process.stdout) > 64 * 1024:
        return {"state": "parse_error", "error_type": "ProbeFailed"}
    try:
        result = json.loads(process.stdout)
    except (ValueError, UnicodeDecodeError):
        return {"state": "parse_error", "error_type": "ProbeOutputInvalid"}
    if not isinstance(result, dict) or result.get("state") not in {
        "parsed", "encrypted", "page_limit_exceeded", "parse_error"
    }:
        return {"state": "parse_error", "error_type": "ProbeOutputInvalid"}
    return result


def analyze_pdf_evidence(path: str, content_type: str, expected_sha256: str) -> dict:
    original = Path(path)
    digest, size = _sha256_file(original)
    if digest != expected_sha256:
        raise ValueError("Original evidence hash changed before PDF analysis")
    if content_type != "application/pdf":
        probe = {"state": "unsupported_media_type"}
    elif size > MAX_PDF_BYTES:
        probe = {"state": "file_limit_exceeded"}
    else:
        probe = _probe(original)
    state = probe["state"]
    structure_status = (
        "supported" if state == "parsed" and probe.get("inspected_pages") == probe.get("page_count") else
        "inconclusive" if state == "parsed" else
        "unsupported" if state in {"encrypted", "page_limit_exceeded", "file_limit_exceeded", "unsupported_media_type"}
        else "error"
    )
    return {
        "pipeline_version": PDF_PIPELINE_VERSION,
        "decision": "manual_review",
        "classification": "Unknown",
        "confidence": 0.0,
        "needs_review": True,
        "model_usage": {"cost": 0.0, "calls": 0},
        "task_results": [
            {
                "task": "document_structure", "status": structure_status,
                "finding": "undetermined", "state": state,
                "evidence": {"asset_sha256": digest, "file_bytes": size,
                             "parser_version": PYPDF_VERSION, **probe},
                "coverage": {"pages_total": probe.get("page_count"),
                             "pages_inspected": probe.get("inspected_pages", 0),
                             "text_extracted_to_result": False},
                "policy_version": PDF_POLICY_VERSION,
                "limitations": (
                    "Text-layer and direct-image observations are structural hints only. "
                    "Skipped pages and nested images are not fully inspected. No OCR or rendering ran."
                ),
            },
            {
                "task": "document_integrity", "status": "inconclusive",
                "finding": "undetermined", "evidence": [],
                "coverage": {"signature_validation_run": False,
                             "revision_validation_run": False},
                "calibrated_score": None, "policy_version": PDF_POLICY_VERSION,
                "limitations": "PDF signatures, revisions, and trust chains have not been verified.",
            },
            {
                "task": "document_field_consistency", "status": "inconclusive",
                "finding": "undetermined", "evidence": [],
                "coverage": {"ocr_run": False, "document_schema_checked": False},
                "calibrated_score": None, "policy_version": PDF_POLICY_VERSION,
                "limitations": "No OCR, field extraction, or document-specific rules have run.",
            },
        ],
    }
