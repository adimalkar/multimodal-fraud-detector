"""Original-byte image provenance and a conservative, no-cost review result."""

import hashlib
import importlib.metadata
from pathlib import Path

IMAGE_PIPELINE_VERSION = "image-evidence-v1"
POLICY_VERSION = "manual-review-v1"
SUPPORTED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def verify_c2pa(path: str, content_type: str) -> dict:
    """Verify an embedded manifest without fetching remote URLs or OCSP data."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(64 * 1024):
            digest.update(chunk)
    asset_sha256 = digest.hexdigest()
    evidence = {
        "state": "unsupported",
        "asset_sha256": asset_sha256,
        "sdk_version": importlib.metadata.version("c2pa-python"),
        "validation_failure_codes": [],
    }
    if content_type not in SUPPORTED_TYPES:
        return evidence

    import c2pa

    try:
        with c2pa.Context.from_dict({
            "verify": {
                "verify_after_reading": True,
                "verify_trust": True,
                "verify_timestamp_trust": True,
                "remote_manifest_fetch": False,
                "ocsp_fetch": False,
            },
        }) as context:
            reader = c2pa.Reader.try_create(path, context=context)
            if reader is None:
                evidence["state"] = "absent"
                return evidence
            with reader:
                state = reader.get_validation_state()
                results = reader.get_validation_results() or {}
                active = results.get("activeManifest") or {}
                failures = active.get("failure") or []
                evidence["validation_failure_codes"] = [
                    item["code"] for item in failures[:20]
                    if isinstance(item, dict) and isinstance(item.get("code"), str)
                ]
                evidence["state"] = {
                    "Trusted": "valid_trusted",
                    "Valid": "valid_untrusted",
                    "Invalid": "invalid",
                }.get(state, "verification_error")
    except c2pa.C2paError:
        evidence["state"] = "verification_error"
    return evidence


def analyze_image_evidence(path: str, content_type: str, expected_sha256: str) -> dict:
    """Return verifiable provenance and abstain on unmeasured synthetic detection."""
    provenance = verify_c2pa(path, content_type)
    if provenance["asset_sha256"] != expected_sha256:
        raise ValueError("Original evidence hash changed before image analysis")
    state = provenance["state"]
    provenance_status = (
        "unsupported" if state == "unsupported" else
        "error" if state == "verification_error" else
        "supported"
    )
    return {
        "pipeline_version": IMAGE_PIPELINE_VERSION,
        "decision": "manual_review",
        "classification": "Unknown",
        "confidence": 0.0,
        "needs_review": True,
        "model_usage": {"cost": 0.0, "calls": 0},
        "task_results": [
            {
                "task": "provenance",
                "status": provenance_status,
                "finding": "evidence_present" if state.startswith("valid_") else "undetermined",
                "state": state,
                "evidence": provenance,
                "coverage": {"original_bytes_checked": True, "embedded_manifest_only": True},
                "policy_version": POLICY_VERSION,
                "limitations": (
                    "A valid credential attests to signed provenance, not factual truth or human origin. "
                    "Absent or invalid credentials do not establish AI generation. "
                    "Remote manifests and online revocation were not checked."
                ),
            },
            {
                "task": "synthetic_image",
                "status": "inconclusive",
                "finding": "undetermined",
                "evidence": [],
                "coverage": {"pixel_detector_checked": False},
                "calibrated_score": None,
                "policy_version": POLICY_VERSION,
                "limitations": "No rights-cleared pixel detector has passed a held-out image evaluation.",
            },
        ],
    }
