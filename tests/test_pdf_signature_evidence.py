"""Real signed PDF cases for the opt-in offline integrity task."""

import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pypdf import PdfWriter

from backend import pdf_evidence
from backend.pdf_evidence import analyze_pdf_signature_evidence


def _analyze(tmp_path, data, monkeypatch, trust_bundle=None):
    path = tmp_path / "document.pdf"
    path.write_bytes(data)
    if trust_bundle is None:
        monkeypatch.delenv("PDF_SIGNATURE_TRUST_ROOTS_PATH", raising=False)
    else:
        monkeypatch.setenv("PDF_SIGNATURE_TRUST_ROOTS_PATH", str(trust_bundle))
    return analyze_pdf_signature_evidence(
        str(path), "application/pdf", hashlib.sha256(data).hexdigest()
    )


@pytest.fixture(scope="module")
def signed_pdf(tmp_path_factory):
    directory = tmp_path_factory.mktemp("signed-pdf")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Signing Root")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(key, hashes.SHA256())
    )
    bundle = directory / "roots.pem"
    bundle.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    pkcs12_path = directory / "signer.p12"
    pkcs12_path.write_bytes(pkcs12.serialize_key_and_certificates(
        b"test", key, certificate, None, serialization.NoEncryption()
    ))
    signer = signers.SimpleSigner.load_pkcs12(pkcs12_path)
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    unsigned = io.BytesIO()
    writer.write(unsigned)
    signed = signers.sign_pdf(
        IncrementalPdfFileWriter(io.BytesIO(unsigned.getvalue())),
        signers.PdfSignatureMetadata(field_name="Signature1"), signer=signer,
    ).getvalue()
    return signed, bundle


def test_unsigned_pdf_is_observation_not_fraud(tmp_path, monkeypatch):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    result = _analyze(tmp_path, stream.getvalue(), monkeypatch)
    integrity = result["task_results"][1]
    assert result["pipeline_version"] == "pdf-evidence-v2"
    assert result["decision"] == "manual_review"
    assert result["classification"] == "Unknown"
    assert integrity["state"] == "unsigned"
    assert integrity["status"] == "supported"
    assert integrity["finding"] == "undetermined"
    assert integrity["coverage"]["signature_count"] == 0


def test_signed_pdf_checks_integrity_and_only_explicit_trust(tmp_path, monkeypatch, signed_pdf):
    data, bundle = signed_pdf
    without_roots = _analyze(tmp_path, data, monkeypatch)
    untrusted = without_roots["task_results"][1]
    assert untrusted["state"] == "checked"
    assert untrusted["evidence"]["signatures"][0]["cryptographic_integrity"] == "valid"
    assert untrusted["evidence"]["signatures"][0]["trust"] == "not_configured"
    assert untrusted["evidence"]["signatures"][0]["post_signature_updates"] is False
    assert untrusted["coverage"]["online_revocation_checked"] is False
    assert without_roots["model_usage"] == {"cost": 0.0, "calls": 0}

    with_roots = _analyze(tmp_path, data, monkeypatch, bundle)
    trusted = with_roots["task_results"][1]
    assert trusted["evidence"]["signatures"][0]["trust"] == "anchored_offline"
    assert trusted["coverage"]["trust_bundle_sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert trusted["finding"] == "undetermined"
    assert "Test Signing Root" not in str(with_roots)


def test_tampered_signed_pdf_is_evidence_but_still_manual_review(tmp_path, monkeypatch, signed_pdf):
    data, bundle = signed_pdf
    assert b"/MediaBox [ 0 0 612 792 ]" in data
    tampered = data.replace(b"/MediaBox [ 0 0 612 792 ]", b"/MediaBox [ 0 0 613 792 ]", 1)
    result = _analyze(tmp_path, tampered, monkeypatch, bundle)
    integrity = result["task_results"][1]
    assert integrity["state"] == "checked"
    assert integrity["evidence"]["signatures"][0]["cryptographic_integrity"] == "invalid"
    assert integrity["finding"] == "evidence_present"
    assert result["decision"] == "manual_review"


def test_incremental_revision_is_reported_without_auto_fraud_label(tmp_path, monkeypatch, signed_pdf):
    data, bundle = signed_pdf
    editor = PdfWriter(io.BytesIO(data), incremental=True)
    editor.add_metadata({"/Producer": "Benign test revision"})
    revised_stream = io.BytesIO()
    editor.write(revised_stream)
    result = _analyze(tmp_path, revised_stream.getvalue(), monkeypatch, bundle)
    integrity = result["task_results"][1]
    signature = integrity["evidence"]["signatures"][0]
    assert integrity["state"] == "checked"
    assert signature["cryptographic_integrity"] == "valid"
    assert signature["post_signature_updates"] is True
    assert signature["modification_level"] is not None
    assert result["decision"] == "manual_review"


def test_invalid_trust_bundle_is_typed_error_without_path(tmp_path, monkeypatch, signed_pdf):
    data, _ = signed_pdf
    missing = tmp_path / "missing-roots.pem"
    result = _analyze(tmp_path, data, monkeypatch, missing)
    integrity = result["task_results"][1]
    assert integrity["status"] == "error"
    assert integrity["state"] == "verification_error"
    assert integrity["evidence"]["error_type"] == "ValueError"
    assert str(missing) not in str(result)


def test_signature_child_receives_no_provider_or_storage_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    observed = {}

    def fake_run(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "state": "unsigned", "signature_count": 0, "signatures": [],
        }).encode())

    monkeypatch.setattr(pdf_evidence.subprocess, "run", fake_run)
    result = pdf_evidence._signature_probe(tmp_path / "placeholder.pdf")
    assert result["state"] == "unsigned"
    assert "OPENROUTER_API_KEY" not in observed["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in observed["env"]
    assert observed["timeout"] == pdf_evidence.PROBE_TIMEOUT_SECONDS


def test_malformed_pdf_skips_signature_validation(tmp_path, monkeypatch):
    def forbid_signature_probe(*args):
        raise AssertionError("Malformed PDF must not reach signature validation")

    monkeypatch.setattr(pdf_evidence, "_signature_probe", forbid_signature_probe)
    result = _analyze(tmp_path, b"%PDF-1.4\nnot a document", monkeypatch)
    assert result["task_results"][0]["status"] == "error"
    assert result["task_results"][1]["state"] == "not_checked"
    assert result["classification"] == "Unknown"
