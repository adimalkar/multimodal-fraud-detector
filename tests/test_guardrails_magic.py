from backend.guardrails import validate_file_magic_bytes


def test_magic_bytes_valid_formats():
    # PDF
    valid, mime = validate_file_magic_bytes(b"%PDF-1.7\n%...", "pdf")
    assert valid
    assert mime == "application/pdf"

    # PNG
    valid, mime = validate_file_magic_bytes(b"\x89PNG\r\n\x1a\n\x00\x00...", "png")
    assert valid
    assert mime == "image/png"

    # JPEG
    valid, mime = validate_file_magic_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF", "jpg")
    assert valid
    assert mime == "image/jpeg"

    # WEBP
    valid, mime = validate_file_magic_bytes(b"RIFF\x24\x00\x00\x00WEBPVP8 ", "webp")
    assert valid
    assert mime == "image/webp"

    # MP4
    valid, mime = validate_file_magic_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00", "mp4")
    assert valid
    assert mime == "video/mp4"


def test_magic_bytes_disguised_executable():
    # Windows PE executable renamed to .pdf
    valid, reason = validate_file_magic_bytes(b"MZ\x90\x00\x03\x00\x00\x00", "pdf")
    assert not valid
    assert "executable" in reason.lower()

    # Linux ELF binary renamed to .png
    valid, reason = validate_file_magic_bytes(b"\x7fELF\x02\x01\x01\x00", "png")
    assert not valid
    assert "executable" in reason.lower()


def test_magic_bytes_mismatch_extension():
    # A JPEG file renamed with .pdf extension
    valid, reason = validate_file_magic_bytes(b"\xff\xd8\xff\xe0\x00\x10", "pdf")
    assert not valid
    assert "Header magic mismatch" in reason
