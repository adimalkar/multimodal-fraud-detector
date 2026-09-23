from backend.app import detect_media_type

def test_detect_media_type_document():
    media_type, ctype = detect_media_type("invoice_claim.pdf", "application/pdf")
    assert media_type == "Document"
    assert ctype == "application/pdf"

def test_detect_media_type_video():
    media_type, ctype = detect_media_type("dashcam_footage.mp4", "video/mp4")
    assert media_type == "Video"
    assert "video" in ctype

    media_type, ctype = detect_media_type("security.mov", "")
    assert media_type == "Video"

def test_detect_media_type_image():
    media_type, ctype = detect_media_type("car_scratch.png", "image/png")
    assert media_type == "Image"
    assert ctype == "image/png"

    media_type, ctype = detect_media_type("receipt.jpg", "image/jpeg")
    assert media_type == "Image"
    assert ctype == "image/jpeg"
