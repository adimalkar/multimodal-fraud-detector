from backend.storage import (
    is_storage_configured,
    generate_presigned_upload_url
)

def test_storage_not_configured_by_default():
    # In test environments without AWS/R2 env vars, should gracefully report False
    assert is_storage_configured() is False

def test_presigned_url_graceful_fallback():
    result = generate_presigned_upload_url("incident_photo.png", "image/png")
    assert result["storage_configured"] is False
    assert "upload_url" in result
    assert result["upload_url"] is None
    assert "message" in result
