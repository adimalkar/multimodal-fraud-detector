"""Verify C2PA against original image bytes, including a signed and altered asset."""

import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image

from backend.image_evidence import analyze_image_evidence, verify_c2pa

SIGNED_FIXTURE = Path(__file__).parent / "fixtures" / "c2pa_valid_untrusted.jpg"


def test_unsigned_image_is_absent_not_synthetic(tmp_path):
    image = Image.new("RGB", (16, 16), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    source = tmp_path / "plain.jpg"
    source.write_bytes(buffer.getvalue())

    result = analyze_image_evidence(
        str(source), "image/jpeg", hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert result["classification"] == "Unknown"
    assert result["model_usage"]["calls"] == 0
    assert result["task_results"][0]["state"] == "absent"
    assert result["task_results"][1]["calibrated_score"] is None


def test_signed_image_is_valid_but_untrusted():
    result = verify_c2pa(str(SIGNED_FIXTURE), "image/jpeg")
    assert result["state"] == "valid_untrusted"
    assert result["asset_sha256"] == hashlib.sha256(SIGNED_FIXTURE.read_bytes()).hexdigest()
    assert "signingCredential.untrusted" in result["validation_failure_codes"]


def test_tampered_signed_image_is_invalid(tmp_path):
    changed = bytearray(SIGNED_FIXTURE.read_bytes())
    changed[-3] ^= 1
    source = tmp_path / "changed.jpg"
    source.write_bytes(changed)

    result = verify_c2pa(str(source), "image/jpeg")
    assert result["state"] == "invalid"
    assert "assertion.dataHash.mismatch" in result["validation_failure_codes"]


def test_expected_original_hash_is_enforced():
    with pytest.raises(ValueError, match="hash changed"):
        analyze_image_evidence(str(SIGNED_FIXTURE), "image/jpeg", "0" * 64)
