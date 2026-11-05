"""Invoice field arithmetic is cited and abstains when extraction is uncertain."""

import hashlib
import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend import pdf_evidence
from backend.pdf_evidence import analyze_pdf_field_evidence
from backend.pdf_invoice_fields import extract_invoice_fields


def _text_pdf(lines):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })
    stream = DecodedStreamObject()
    encoded = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
               for line in lines]
    stream.set_data(("BT /F1 18 Tf 72 720 Td " +
                     " ".join(f"({line}) Tj 0 -32 Td" for line in encoded) +
                     " ET").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _scanned_pdf(lines):
    image = Image.new("RGB", (1600, 900), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 65)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((80, 80 + index * 160), line, font=font, fill="black")
    output = io.BytesIO()
    image.save(output, "PDF", resolution=150.0)
    return output.getvalue()


def _analyze(tmp_path, data):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(data)
    return analyze_pdf_field_evidence(
        str(path), "application/pdf", hashlib.sha256(data).hexdigest()
    )


def test_text_layer_invoice_match_and_mismatch_have_cited_values(tmp_path):
    for total, expected in [("12.50", "match"), ("13.00", "mismatch")]:
        data = _text_pdf(["Invoice 2026", "Subtotal: $10.00", "Tax: $2.50",
                          f"Total: ${total}"])
        result = _analyze(tmp_path, data)
        task = result["task_results"][2]
        assert result["pipeline_version"] == "pdf-evidence-v4"
        assert result["classification"] == "Unknown"
        assert result["decision"] == "manual_review"
        assert result["model_usage"] == {"cost": 0.0, "calls": 0}
        assert task["status"] == "supported"
        assert task["evidence"]["check"] == expected
        assert task["evidence"]["fields"]["total"][0]["citation"] == {
            "page": 1, "source": "text_layer", "line": 4}
        assert task["finding"] == ("evidence_not_found" if expected == "match"
                                   else "evidence_present")
        assert task["coverage"]["pages_read"] == [1]


@pytest.mark.skipif(not shutil.which("tesseract") or not shutil.which("pdftoppm"),
                    reason="OCR system binaries unavailable")
def test_scanned_invoice_uses_ocr_box_and_abstains_on_low_confidence(tmp_path):
    result = _analyze(tmp_path, _scanned_pdf([
        "Invoice 2026", "Subtotal: $10.00", "Tax: $2.50", "Total: $12.50"
    ]))
    task = result["task_results"][2]
    assert task["evidence"]["fields"]["total"][0]["citation"]["source"] == "ocr"
    assert len(task["evidence"]["fields"]["total"][0]["citation"]["bbox_px"]) == 4
    assert task["evidence"]["check"] == "match"
    assert task["state"] == "checked"
    assert result["classification"] == "Unknown"


def test_unsupported_missing_and_repeated_amounts_abstain(tmp_path):
    unsupported = _analyze(tmp_path, _text_pdf(["Receipt", "Subtotal: $10.00",
                                                "Tax: $2.00", "Total: $12.00"]))
    assert unsupported["task_results"][2]["status"] == "unsupported"
    assert unsupported["task_results"][2]["finding"] == "undetermined"

    missing = _analyze(tmp_path, _text_pdf(["Invoice 2026", "Subtotal: $10.00",
                                            "Total: $12.00"]))
    assert missing["task_results"][2]["state"] == "missing_fields"
    assert missing["task_results"][2]["evidence"]["check"] == "not_run"

    repeated = _analyze(tmp_path, _text_pdf(["Invoice 2026", "Subtotal: $10.00",
                                             "Tax: $2.00", "Total: $12.00",
                                             "Total: $13.00"]))
    assert repeated["task_results"][2]["state"] == "ambiguous_fields"
    assert repeated["task_results"][2]["finding"] == "undetermined"


def test_incomplete_page_abstains_even_with_all_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_evidence, "_invoice_text_probe", lambda *_: {
        "state": "partial", "pages": [{"page": 1, "state": "page_error"}],
    })
    result = _analyze(tmp_path, _text_pdf(["Invoice 2026", "Subtotal: $10.00",
                                          "Tax: $2.00", "Total: $12.00"]))
    task = result["task_results"][2]
    assert task["state"] == "incomplete_coverage"
    assert task["finding"] == "undetermined"
    assert task["coverage"]["document_schema_checked"] is False


def test_ocr_uncertainty_blocks_arithmetic():
    lines = [{"text": text, "citation": {"page": 1, "source": "ocr", "line": index},
              "low_ocr_confidence": index == 4}
             for index, text in enumerate([
                 "Invoice 2026", "Subtotal: $10.00", "Tax: $2.00", "Total: $99.00"
             ], 1)]
    result = extract_invoice_fields(lines, complete_coverage=True)
    assert result["state"] == "low_ocr_confidence"
    assert result["check"] == "not_run"


def test_additional_adjustment_abstains_instead_of_false_mismatch(tmp_path):
    result = _analyze(tmp_path, _text_pdf([
        "Invoice 2026", "Subtotal: $10.00", "Tax: $2.00", "Shipping: $3.00",
        "Total: $15.00",
    ]))
    task = result["task_results"][2]
    assert task["state"] == "unsupported_adjustments"
    assert task["finding"] == "undetermined"
    assert task["evidence"]["additional_amount_citations"] == [
        {"page": 1, "source": "text_layer", "line": 4}
    ]


def test_field_child_does_not_receive_provider_or_storage_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    observed = {}

    def fake_run(*args, **kwargs):
        observed.update(kwargs)
        class Process:
            returncode = 0
            stdout = b'{"state":"read","pages":[]}'
        return Process()

    monkeypatch.setattr(pdf_evidence.subprocess, "run", fake_run)
    assert pdf_evidence._invoice_text_probe(tmp_path / "invoice.pdf", [1])["state"] == "read"
    assert "OPENROUTER_API_KEY" not in observed["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in observed["env"]
