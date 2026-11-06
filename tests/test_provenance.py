"""Provenance checks: what a file declares about its own origin.

The two c2pa_ai_generated_untrusted.* fixtures were signed with the C2PA SDK's
published test certificate (contentauth/c2pa-rs, sdk/tests/fixtures/certs/es256),
so they carry a valid but untrusted signature, exactly like a real generator's
credentials before a trust list is configured.
"""

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from backend import provenance
from backend.provenance import inspect_provenance, model_reported_watermark

FIXTURES = Path(__file__).parent / "fixtures"
AI_JPEG = FIXTURES / "c2pa_ai_generated_untrusted.jpg"
AI_MP4 = FIXTURES / "c2pa_ai_generated_untrusted.mp4"
CAMERA_JPEG = FIXTURES / "c2pa_valid_untrusted.jpg"
needs_ocr = pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract is not installed")


def xmp(source_type):
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
        f'Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/digitalsourcetype/{source_type}"/>'
        "</rdf:RDF></x:xmpmeta>"
    ).encode()


def jpeg(tmp_path, name="photo.jpg", **save):
    path = tmp_path / name
    Image.new("RGB", (64, 48), (120, 140, 160)).save(path, "JPEG", **save)
    return str(path)


def kinds(result):
    return [finding["kind"] for finding in result["findings"]]


def test_signed_ai_declaration_is_decisive():
    result = inspect_provenance(str(AI_JPEG), "Image", "image/jpeg")
    credentials = result["checks"][0]
    assert credentials["state"] == "valid_untrusted"
    assert credentials["ai_declared"] is True
    assert result["decisive"] is True
    assert kinds(result) == ["declared_ai_signed"]
    assert "Created by a test generator." in result["findings"][0]["summary"]


def test_signed_ai_video_is_decisive():
    result = inspect_provenance(str(AI_MP4), "Video", "video/mp4")
    assert result["decisive"] is True
    assert kinds(result)[0] == "declared_ai_signed"


def test_valid_credentials_without_an_ai_declaration_raise_nothing():
    result = inspect_provenance(str(CAMERA_JPEG), "Image", "image/jpeg")
    assert result["checks"][0]["state"] == "valid_untrusted"
    assert result["findings"] == []
    assert result["decisive"] is False


def test_broken_signature_still_reports_the_declaration(tmp_path):
    data = bytearray(AI_JPEG.read_bytes())
    data[-40] ^= 0xFF  # Inside the image data, after the manifest.
    altered = tmp_path / "altered.jpg"
    altered.write_bytes(bytes(data))
    result = inspect_provenance(str(altered), "Image", "image/jpeg")
    assert result["checks"][0]["state"] == "invalid"
    assert kinds(result) == ["declared_ai_broken_signature"]
    assert result["decisive"] is False


def test_unsigned_iptc_tag_is_reported(tmp_path):
    result = inspect_provenance(jpeg(tmp_path, xmp=xmp("trainedAlgorithmicMedia")), "Image", "image/jpeg")
    assert kinds(result) == ["declared_ai_tag"]
    assert result["decisive"] is True


def test_camera_iptc_tag_raises_nothing(tmp_path):
    result = inspect_provenance(jpeg(tmp_path, xmp=xmp("digitalCapture")), "Image", "image/jpeg")
    assert result["checks"][1]["source_types"] == ["digitalCapture"]
    assert result["findings"] == []


def test_generator_settings_in_png_are_reported_without_the_prompt(tmp_path):
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a private prompt about the claimant, Steps: 30, Sampler: Euler a")
    path = tmp_path / "render.png"
    Image.new("RGB", (32, 32)).save(path, pnginfo=info)
    result = inspect_provenance(str(path), "Image", "image/png")
    assert kinds(result) == ["generator_metadata"]
    assert "private prompt" not in result["findings"][0]["summary"]


@pytest.mark.parametrize("tag,value,expected", [
    (305, "DALL-E 3", True),
    (305, "Adobe Photoshop 25.0", False),
    (270, "Parked near the runway at noon", False),
    (270, "AI generated concept image", True),
])
def test_exif_tags(tmp_path, tag, value, expected):
    exif = Image.Exif()
    exif[tag] = value
    result = inspect_provenance(jpeg(tmp_path, exif=exif), "Image", "image/jpeg")
    assert ("generator_metadata" in kinds(result)) is expected


def captioned(tmp_path, text, name):
    image = Image.new("RGB", (900, 600), (40, 60, 90))
    ImageDraw.Draw(image).text((700, 545), text, fill="white", font=ImageFont.load_default(size=40))
    path = tmp_path / name
    image.save(path, "JPEG", quality=92)
    return str(path)


@needs_ocr
def test_visible_generator_mark_is_read(tmp_path):
    result = inspect_provenance(captioned(tmp_path, "Veo", "veo.jpg"), "Image", "image/jpeg")
    assert kinds(result) == ["visible_watermark"]
    assert result["decisive"] is False


@needs_ocr
def test_ordinary_sign_text_is_not_a_watermark(tmp_path):
    result = inspect_provenance(captioned(tmp_path, "Gemini Cafe", "sign.jpg"), "Image", "image/jpeg")
    assert result["findings"] == []


def test_missing_ocr_reads_as_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance.shutil, "which", lambda name: None)
    result = inspect_provenance(jpeg(tmp_path), "Image", "image/jpeg")
    watermark = next(check for check in result["checks"] if check["check"] == "visible_watermark")
    assert watermark["state"] == "not_run"


def test_unreadable_trust_list_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setenv("C2PA_TRUST_ANCHORS_PATH", "/nonexistent/anchors.pem")
    assert provenance.check_content_credentials(str(AI_JPEG), "image/jpeg")["state"] == "error"


def test_plain_file_has_no_findings_and_every_check_reports_a_state(tmp_path):
    result = inspect_provenance(jpeg(tmp_path), "Image", "image/jpeg")
    assert result["findings"] == []
    assert all(check["state"] for check in result["checks"])
    assert {check["check"] for check in result["checks"]} == {
        "content_credentials", "embedded_tags", "generator_metadata", "visible_watermark"}


@pytest.mark.parametrize("text,kept", [("Veo", True), ("Made with AI", True), ("", False), ("a red car", False)])
def test_model_reported_watermark(text, kept):
    assert (model_reported_watermark(text) is not None) is kept
