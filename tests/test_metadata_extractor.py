import sys
import tempfile
import types

from PIL import Image

from backend.metadata_extractor import extract_metadata


def test_pdf_decodes_octal_escapes_and_nested_parentheses():
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(
            b"%PDF-1.5\n1 0 obj\n"
            b"<< /Creator (Writer \\(1\\0560\\)) /Producer (Ghost\\055PDF) >>\n"
            b"endobj\n%%EOF"
        )
        f.flush()

        res = extract_metadata(f.name, "Document")
        assert res["metadata"]["creator"] == "Writer (1.0)"
        assert res["metadata"]["producer"] == "Ghost-PDF"


def test_pdf_decodes_utf16be_and_ascii_hex_metadata():
    # <FEFF00430061006E00760061> == "Canva", <536D616C6C504446> == "SmallPDF"
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(
            b"%PDF-1.6\n1 0 obj\n"
            b"<< /Creator <FEFF00430061006E00760061> /Producer <536D616C6C504446> >>\n"
            b"endobj\n%%EOF"
        )
        f.flush()

        res = extract_metadata(f.name, "Document")
        assert res["metadata"]["creator"] == "Canva"
        assert res["metadata"]["producer"] == "SmallPDF"
        assert any("Canva" in flag for flag in res["flags"])


def test_pdf_dictionary_value_does_not_misparse_as_hex_string():
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b"%PDF-1.4\n<< /Creator << /Nested 1 >> /Producer (PlainTool) >>\n%%EOF")
        f.flush()

        res = extract_metadata(f.name, "Document")
        assert res["metadata"]["creator"] is None
        assert res["metadata"]["producer"] == "PlainTool"


def test_image_exif_strips_nul_padding_and_avoids_false_date_mismatch(monkeypatch):
    class FakeImage:
        format = "JPEG"
        width = 800
        height = 600
        mode = "RGB"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def _getexif(self):
            # 271=Make, 272=Model, 305=Software, 306=DateTime, 36867=DateTimeOriginal
            return {
                271: "Canon\x00\x00",
                272: b"EOS R6\x00",
                305: "Adobe Photoshop 25.0\x00",
                306: "2026:11:24 10:00:00",
                36867: "2026:11:24 10:00:00\x00 ",
            }

    monkeypatch.setattr(Image, "open", lambda _path: FakeImage())

    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        res = extract_metadata(f.name, "Image")

    assert res["metadata"]["camera_make"] == "Canon"
    assert res["metadata"]["camera_model"] == "EOS R6"
    assert res["metadata"]["software"] == "Adobe Photoshop 25.0"
    assert any("Photoshop" in flag for flag in res["flags"])
    assert not any("date tags differ" in flag for flag in res["flags"])


def test_video_capture_releases_handle_even_if_probe_errors(monkeypatch):
    state = {"released": False}

    class FailingCapture:
        def isOpened(self):
            return True

        def get(self, _prop):
            raise RuntimeError("corrupt frame header")

        def release(self):
            state["released"] = True

    fake_cv2 = types.SimpleNamespace(
        VideoCapture=lambda _path: FailingCapture(),
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        CAP_PROP_FPS=5,
        CAP_PROP_FRAME_COUNT=7,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        res = extract_metadata(f.name, "Video")

    assert state["released"] is True
    assert any("Video metadata error" in flag for flag in res["flags"])
