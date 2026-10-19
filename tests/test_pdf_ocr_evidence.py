"""Real scanned-PDF OCR and conservative coverage checks."""

import hashlib
import io
import json
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend import pdf_evidence
from backend.pdf_evidence import analyze_pdf_ocr_evidence
from backend.pdf_ocr_probe import MAX_WORDS_PER_PAGE, _words


def _analyze(tmp_path, data):
    path = tmp_path / "document.pdf"
    path.write_bytes(data)
    return analyze_pdf_ocr_evidence(
        str(path), "application/pdf", hashlib.sha256(data).hexdigest()
    )


def _scanned_pdf(page_count=1):
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 90)
    pages = []
    for _ in range(page_count):
        image = Image.new("RGB", (1600, 550), "white")
        ImageDraw.Draw(image).text(
            (80, 120), "INVOICE 2026 TOTAL 42.00", font=font, fill="black"
        )
        pages.append(image)
    output = io.BytesIO()
    pages[0].save(output, "PDF", resolution=150.0, save_all=True,
                  append_images=pages[1:])
    return output.getvalue()


def _text_layer_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
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
    stream.set_data(b"BT /F1 20 Tf 72 720 Td (Private invoice total 42.00) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.skipif(not shutil.which("tesseract") or not shutil.which("pdftoppm"),
                    reason="OCR system binaries unavailable")
def test_scanned_pdf_ocr_has_page_boxes_without_fraud_verdict(tmp_path):
    result = _analyze(tmp_path, _scanned_pdf())
    ocr = result["task_results"][-1]
    assert result["pipeline_version"] == "pdf-evidence-v3"
    assert result["decision"] == "manual_review"
    assert result["classification"] == "Unknown"
    assert result["model_usage"] == {"cost": 0.0, "calls": 0}
    assert ocr["status"] == "supported"
    assert ocr["coverage"]["pages_ocr_selected"] == [1]
    assert ocr["coverage"]["pages_ocr_read"] == 1
    page = ocr["evidence"]["pages"][0]
    assert page["render_sha256"] and len(page["render_sha256"]) == 64
    assert page["image_size_px"][0] <= 1400
    assert page["image_size_px"][1] <= 1400
    assert "INVOICE" in [word["text"] for word in page["words"]]
    assert all(0 <= word["confidence"] <= 1 for word in page["words"])
    assert all(0 <= word["bbox_px"][0] < word["bbox_px"][2] <= page["image_size_px"][0]
               for word in page["words"])
    assert result["task_results"][2]["status"] == "inconclusive"
    assert "INVOICE" not in str(result["task_results"][:3])


def test_text_layer_page_skips_ocr_without_claiming_field_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_evidence, "_ocr_probe", lambda *_: pytest.fail("OCR was not needed"))
    result = _analyze(tmp_path, _text_layer_pdf())
    ocr = result["task_results"][-1]
    assert ocr["state"] == "not_needed_text_layer"
    assert ocr["coverage"]["pages_ocr_selected"] == []
    assert ocr["status"] == "inconclusive"
    assert result["task_results"][2]["coverage"]["document_schema_checked"] is False


@pytest.mark.skipif(not shutil.which("tesseract") or not shutil.which("pdftoppm"),
                    reason="OCR system binaries unavailable")
def test_page_budget_exposes_unread_pages(tmp_path):
    result = _analyze(tmp_path, _scanned_pdf(page_count=5))
    ocr = result["task_results"][-1]
    assert ocr["status"] == "inconclusive"
    assert ocr["coverage"]["pages_ocr_eligible"] == 5
    assert ocr["coverage"]["pages_ocr_selected"] == [1, 2, 3, 4]
    assert ocr["coverage"]["pages_skipped_budget"] == [5]
    assert ocr["coverage"]["pages_ocr_read"] == 4


def test_bad_pdf_skips_ocr_and_missing_binary_is_typed(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_evidence, "_ocr_probe", lambda *_: pytest.fail("Bad PDF reached OCR"))
    result = _analyze(tmp_path, b"%PDF-1.4\nnot a PDF")
    assert result["task_results"][-1]["state"] == "not_checked_structure"
    assert result["task_results"][-1]["coverage"]["ocr_run"] is False

    monkeypatch.setattr(pdf_evidence, "_ocr_probe", lambda *_: {
        "state": "dependency_unavailable", "pages": [],
    })
    result = _analyze(tmp_path, _scanned_pdf())
    assert result["task_results"][-1]["status"] == "unsupported"
    assert result["classification"] == "Unknown"


def test_ocr_child_environment_excludes_provider_and_storage_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    observed = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return json.dumps({"state": "read", "pages": []}).encode(), b""

    def fake_popen(*args, **kwargs):
        observed.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(pdf_evidence.subprocess, "Popen", fake_popen)
    assert pdf_evidence._ocr_probe(tmp_path / "sample.pdf", [1])["state"] == "read"
    assert "OPENROUTER_API_KEY" not in observed["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in observed["env"]
    assert observed["start_new_session"]


def test_ocr_word_output_is_bounded_and_rejects_invalid_boxes():
    header = "level\tleft\ttop\twidth\theight\tconf\ttext\n"
    word = "A" * 80
    rows = "".join(f"5\t0\t0\t20\t10\t95\t{word}\n"
                   for _ in range(MAX_WORDS_PER_PAGE + 3))
    count, reported, mean = _words((header + rows).encode(), 100, 100)
    assert count == MAX_WORDS_PER_PAGE + 3
    assert len(reported) == MAX_WORDS_PER_PAGE
    assert all(len(item["text"]) == 64 and item["text_capped"] for item in reported)
    assert mean == 0.95

    with pytest.raises(ValueError, match="geometry"):
        _words((header + "5\t99\t0\t20\t10\t95\tbad\n").encode(), 100, 100)
