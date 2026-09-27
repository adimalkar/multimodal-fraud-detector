"""Real parser and boundary checks for the opt-in PDF evidence path."""

import hashlib
import io
import json
import subprocess
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from backend.pdf_evidence import analyze_pdf_evidence
from backend import pdf_evidence
from backend.pdf_probe import MAX_CONTENT_BYTES_PER_PAGE


def pdf_bytes(*, pages=1, with_text=False, encrypted=False, oversized_content=False):
    writer = PdfWriter()
    for index in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        if with_text and index == 0:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            font_ref = writer._add_object(font)
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 72 720 Td (Private invoice text) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        if oversized_content and index == 0:
            stream = DecodedStreamObject()
            stream.set_data(b" " * (MAX_CONTENT_BYTES_PER_PAGE + 1))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def analyze(tmp_path, data):
    path = tmp_path / "evidence.pdf"
    path.write_bytes(data)
    return analyze_pdf_evidence(str(path), "application/pdf", hashlib.sha256(data).hexdigest())


def test_pdf_records_page_coverage_without_disclosing_text(tmp_path):
    result = analyze(tmp_path, pdf_bytes(pages=2, with_text=True))
    structure, integrity, fields = result["task_results"]
    assert result["decision"] == "manual_review"
    assert result["model_usage"] == {"cost": 0.0, "calls": 0}
    assert structure["status"] == "supported"
    assert structure["coverage"] == {"pages_total": 2, "pages_inspected": 2,
                                     "text_extracted_to_result": False}
    assert structure["evidence"]["text_layer_pages"] == 1
    assert structure["evidence"]["document_profile"] == "undetermined"
    assert integrity["status"] == "inconclusive"
    assert fields["status"] == "inconclusive"
    assert "Private invoice text" not in json.dumps(result)


def test_encrypted_and_excess_pages_abstain(tmp_path):
    encrypted = analyze(tmp_path, pdf_bytes(encrypted=True))["task_results"][0]
    assert encrypted["status"] == "unsupported"
    assert encrypted["state"] == "encrypted"
    too_many = analyze(tmp_path, pdf_bytes(pages=21))["task_results"][0]
    assert too_many["status"] == "unsupported"
    assert too_many["state"] == "page_limit_exceeded"
    assert too_many["coverage"]["pages_inspected"] == 0


def test_large_content_stream_skips_page_and_reports_partial_coverage(tmp_path):
    structure = analyze(tmp_path, pdf_bytes(oversized_content=True))["task_results"][0]
    assert structure["status"] == "inconclusive"
    assert structure["coverage"] == {"pages_total": 1, "pages_inspected": 0,
                                     "text_extracted_to_result": False}
    assert structure["evidence"]["pages"][0]["state"] == "content_limit_exceeded"


def test_malformed_pdf_returns_typed_error_and_hash_change_fails(tmp_path):
    malformed = analyze(tmp_path, b"%PDF-1.4\nbroken")["task_results"][0]
    assert malformed["status"] == "error"
    assert malformed["state"] == "parse_error"
    path = tmp_path / "evidence.pdf"
    with pytest.raises(ValueError, match="hash changed"):
        analyze_pdf_evidence(str(path), "application/pdf", "0" * 64)


def test_pdf_child_receives_no_provider_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    observed = {}

    def fake_run(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b'{"state":"encrypted","page_count":null,"pages":[]}')

    monkeypatch.setattr(pdf_evidence.subprocess, "run", fake_run)
    analyze(tmp_path, pdf_bytes())
    assert "OPENROUTER_API_KEY" not in observed["env"]
    assert observed["timeout"] == pdf_evidence.PROBE_TIMEOUT_SECONDS


def test_pdf_probe_timeout_abstains_without_parser_prose(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(pdf_evidence.subprocess, "run", timeout)
    result = analyze(tmp_path, pdf_bytes())
    structure = result["task_results"][0]
    assert structure["status"] == "error"
    assert structure["evidence"]["error_type"] == "TimeoutExpired"
    assert result["classification"] == "Unknown"
