"""Opt-in, no-model PDF evidence; authenticity remains undetermined."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from backend.pdf_probe import MAX_PAGES, PYPDF_VERSION
from backend.pdf_ocr_probe import MAX_OCR_PAGES
from backend.pdf_signature_probe import PYHANKO_VERSION

PDF_PIPELINE_VERSION = "pdf-evidence-v1"
PDF_SIGNATURE_PIPELINE_VERSION = "pdf-evidence-v2"
PDF_OCR_PIPELINE_VERSION = "pdf-evidence-v3"
PDF_POLICY_VERSION = "manual-review-v1"
PDF_SIGNATURE_POLICY_VERSION = "manual-review-v2"
PDF_OCR_POLICY_VERSION = "manual-review-v3"
MAX_PDF_BYTES = 20 * 1024 * 1024
PROBE_TIMEOUT_SECONDS = 25
OCR_PROBE_TIMEOUT_SECONDS = 75


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


def _signature_probe(path: Path) -> dict:
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1"}
    trust_path = os.getenv("PDF_SIGNATURE_TRUST_ROOTS_PATH")
    if trust_path:
        env["PDF_SIGNATURE_TRUST_ROOTS_PATH"] = trust_path
    try:
        process = subprocess.run(
            [sys.executable, "-m", "backend.pdf_signature_probe", str(path)],
            cwd=Path(__file__).resolve().parent.parent,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, timeout=PROBE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"state": "verification_error", "error_type": "TimeoutExpired"}
    if process.returncode != 0 or len(process.stdout) > 64 * 1024:
        return {"state": "verification_error", "error_type": "ProbeFailed"}
    try:
        result = json.loads(process.stdout)
    except (ValueError, UnicodeDecodeError):
        return {"state": "verification_error", "error_type": "ProbeOutputInvalid"}
    if not isinstance(result, dict) or result.get("state") not in {
        "unsigned", "checked", "partial", "signature_limit_exceeded", "verification_error"
    }:
        return {"state": "verification_error", "error_type": "ProbeOutputInvalid"}
    return result


def _ocr_probe(path: Path, pages: list[int]) -> dict:
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.pdf_ocr_probe", str(path),
         ",".join(str(page) for page in pages)],
        cwd=Path(__file__).resolve().parent.parent,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1",
             "OMP_THREAD_LIMIT": "1"},
        start_new_session=os.name == "posix",
    )
    try:
        output, _ = process.communicate(timeout=OCR_PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.communicate()
        return {"state": "probe_error", "error_type": "TimeoutExpired", "pages": []}
    if process.returncode != 0 or len(output) > 256 * 1024:
        return {"state": "probe_error", "error_type": "ProbeFailed", "pages": []}
    try:
        result = json.loads(output)
    except (ValueError, UnicodeDecodeError):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "pages": []}
    if not isinstance(result, dict) or result.get("state") not in {
        "read", "partial", "dependency_unavailable", "probe_error"
    } or not isinstance(result.get("pages"), list):
        return {"state": "probe_error", "error_type": "ProbeOutputInvalid", "pages": []}
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


def analyze_pdf_signature_evidence(path: str, content_type: str, expected_sha256: str) -> dict:
    """Add offline signature observations to the v1 structure result, then abstain."""
    result = analyze_pdf_evidence(path, content_type, expected_sha256)
    result["pipeline_version"] = PDF_SIGNATURE_PIPELINE_VERSION
    for task in result["task_results"]:
        task["policy_version"] = PDF_SIGNATURE_POLICY_VERSION
    structure, integrity, _ = result["task_results"]
    if structure["status"] != "supported":
        integrity["state"] = "not_checked"
        integrity["limitations"] = "Signature verification was skipped because PDF structure inspection was incomplete."
        return result

    signature_result = _signature_probe(Path(path))
    # A local materialized artifact should not change between the two child reads.
    if _sha256_file(Path(path))[0] != expected_sha256:
        raise ValueError("Original evidence hash changed during PDF signature analysis")
    state = signature_result["state"]
    signatures = signature_result.get("signatures", [])
    integrity.update({
        "status": (
            "supported" if state in {"unsigned", "checked"} else
            "inconclusive" if state in {"partial", "signature_limit_exceeded"} else "error"
        ),
        "state": state,
        "finding": (
            "evidence_present" if state == "checked" and any(
                item.get("cryptographic_integrity") == "invalid"
                or item.get("document_policy_ok") is False for item in signatures
            ) else "undetermined"
        ),
        "evidence": signature_result,
        "coverage": {
            "signature_count": signature_result.get("signature_count"),
            "signatures_checked": sum(item.get("state") == "checked" for item in signatures),
            "signature_validation_run": state in {"checked", "partial"},
            "revision_validation_run": state == "checked",
            "trust_roots_configured": signature_result.get("trust_roots_configured", False),
            "trust_bundle_sha256": signature_result.get("trust_bundle_sha256"),
            "online_revocation_checked": False,
        },
        "validator_version": PYHANKO_VERSION,
        "limitations": (
            "An unsigned PDF is ordinary. Signature integrity and revision checks do not "
            "validate the document's factual claims. Trust is assessed only against an "
            "explicit local root bundle; online revocation was not checked."
        ),
    })
    return result


def analyze_pdf_ocr_evidence(path: str, content_type: str, expected_sha256: str) -> dict:
    """Add bounded page OCR to v2 evidence without making a document verdict."""
    result = analyze_pdf_signature_evidence(path, content_type, expected_sha256)
    result["pipeline_version"] = PDF_OCR_PIPELINE_VERSION
    for task in result["task_results"]:
        task["policy_version"] = PDF_OCR_POLICY_VERSION
    structure = result["task_results"][0]
    field_task = result["task_results"][2]
    pages = structure["evidence"].get("pages", [])
    candidates = [page["page"] for page in pages
                  if page.get("state") == "inspected" and page.get("text_chars", 0) < 20]
    selected = candidates[:MAX_OCR_PAGES] if structure["status"] == "supported" else []
    reading = {
        "task": "document_ocr", "status": "inconclusive", "finding": "undetermined",
        "state": "not_checked", "evidence": [],
        "coverage": {
            "pages_total": structure["coverage"]["pages_total"],
            "pages_with_text_layer": sum(page.get("text_chars", 0) >= 20 for page in pages),
            "pages_ocr_eligible": len(candidates), "pages_ocr_selected": selected,
            "pages_skipped_budget": candidates[MAX_OCR_PAGES:], "pages_ocr_read": 0,
            "words_reported": 0, "ocr_run": False,
        },
        "calibrated_score": None, "policy_version": PDF_OCR_POLICY_VERSION,
        "limitations": (
            "English OCR is limited to pages with little extractable text and four pages per job. "
            "Word text may contain private document data; results are tenant-scoped. "
            "OCR confidence is engine output, not evidence of document authenticity."
        ),
    }
    result["task_results"].append(reading)
    if structure["status"] != "supported":
        reading["state"] = "not_checked_structure"
        return result
    if not selected:
        reading["state"] = "not_needed_text_layer"
        return result

    ocr_result = _ocr_probe(Path(path), selected)
    if _sha256_file(Path(path))[0] != expected_sha256:
        raise ValueError("Original evidence hash changed during PDF OCR analysis")
    observations = ocr_result.get("pages", [])
    read_pages = [page for page in observations if page.get("state") == "read"]
    reading.update({
        "status": (
            "supported" if ocr_result["state"] == "read"
            and len(candidates) == len(selected)
            and all(not page["words_capped"] for page in read_pages)
            else "unsupported" if ocr_result["state"] == "dependency_unavailable"
            else "error" if ocr_result["state"] == "probe_error" else "inconclusive"
        ),
        "state": ocr_result["state"], "evidence": ocr_result,
    })
    reading["coverage"].update({
        "pages_ocr_read": len(read_pages),
        "words_reported": sum(page["words_reported"] for page in read_pages),
        "ocr_run": bool(observations),
    })
    field_task["coverage"]["ocr_run"] = bool(observations)
    field_task["limitations"] = "OCR observations are available, but no field extraction or document rules have run."
    return result
