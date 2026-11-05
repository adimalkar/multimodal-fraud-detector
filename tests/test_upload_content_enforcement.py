"""Every intake path must reject content that doesn't match its extension."""
import asyncio
import io
import time

import pytest
from PIL import Image
from starlette.testclient import TestClient

from backend import app as app_module
from backend.app import app, jobs
from backend.guardrails import rate_limiter

ELF = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(monkeypatch):
    rate_limiter._requests.clear()
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    monkeypatch.setattr(app_module, "verify_provider_authentication",
                        lambda: {"openrouter": {"status": "authenticated", "http_status": 200}})
    monkeypatch.setattr(app_module, "run_analysis_pipeline", lambda *args: None)
    monkeypatch.setattr(app_module, "run_batch_pipeline", lambda *args: None)
    return TestClient(app)


@pytest.mark.parametrize("name,payload,kind", [
    ("claim.jpg", ELF, "image/jpeg"),
    ("claim.pdf", jpeg(), "application/pdf"),
    ("clip.mov", b"plain text pretending to be video", "video/quicktime"),
    ("clip.avi", b"plain text pretending to be video", "video/x-msvideo"),
    ("claim.jpg", b"\xff\xd8", "image/jpeg"),
])
def test_single_upload_rejects_mismatched_content(client, name, payload, kind):
    response = client.post("/api/analyze", files={"file": (name, payload, kind)})
    assert response.status_code == 415, response.text
    assert name in response.json()["detail"]


def test_sync_upload_rejects_mismatched_content(client):
    response = client.post("/analyze_media", files={"file": ("claim.jpg", ELF, "image/jpeg")})
    assert response.status_code == 415


def test_batch_rejects_whole_batch_on_one_bad_file(client):
    response = client.post("/api/batch/analyze", files=[
        ("files", ("good.jpg", jpeg(), "image/jpeg")),
        ("files", ("bad.jpg", ELF, "image/jpeg")),
    ])
    assert response.status_code == 415
    assert "bad.jpg" in response.json()["detail"]


def test_valid_upload_is_untouched_by_the_check(client, monkeypatch):
    """The check must rewind the stream, or an empty file gets stored."""
    seen = {}

    def capture(job_id, file_path, media_type, content_type):
        with open(file_path, "rb") as stored:
            seen["bytes"] = stored.read()

    monkeypatch.setattr(app_module, "run_analysis_pipeline", capture)
    payload = jpeg()
    response = client.post("/api/analyze", files={"file": ("claim.jpg", payload, "image/jpeg")})
    assert response.status_code == 200
    assert seen["bytes"] == payload


def test_url_download_with_bad_content_fails_and_is_deleted(client, monkeypatch, tmp_path):
    async def fake_download(url, path):
        with open(path, "wb") as target:
            target.write(ELF)

    monkeypatch.setattr(app_module, "download_file_stream", fake_download)
    monkeypatch.setattr(app_module, "TEMP_DIR", str(tmp_path))
    reached = []
    monkeypatch.setattr(app_module, "run_analysis_pipeline", lambda *args: reached.append(args))
    job_id = "url-job"
    jobs[job_id] = {"status": "queued", "created_at": time.time(), "updated_at": time.time()}
    asyncio.run(app_module.run_analysis_pipeline_from_url(
        job_id, "https://example.test/x.jpg", "Image", "image/jpeg", "x.jpg"))
    assert jobs[job_id]["status"] == "failed"
    assert not reached
    assert list(tmp_path.iterdir()) == []
