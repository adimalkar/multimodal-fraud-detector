import io
import pytest
from starlette.testclient import TestClient
from backend.app import app
from backend.guardrails import rate_limiter, InMemoryRateLimiter, MAX_BATCH_SIZE

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_limiter(monkeypatch):
    monkeypatch.setattr("backend.app.missing_model_credentials", lambda: [])
    rate_limiter.reset()
    yield
    rate_limiter.reset()


def test_root_includes_guardrails():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "guardrails" in data
    assert "max_file_size_mb" in data["guardrails"]
    assert "max_batch_size" in data["guardrails"]
    assert "allowed_extensions" in data["guardrails"]
    assert "jpg" in data["guardrails"]["allowed_extensions"]
    assert "pdf" in data["guardrails"]["allowed_extensions"]
    assert "mp4" in data["guardrails"]["allowed_extensions"]


def test_reject_unsupported_file_extension():
    fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    response = client.post(
        "/api/analyze",
        files={"file": ("malicious_payload.exe", fake_exe, "application/octet-stream")}
    )
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_reject_unsupported_batch_file_extension():
    valid_file = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
    bad_file = io.BytesIO(b"#!/bin/bash\necho hello")
    response = client.post(
        "/api/batch/analyze",
        files=[
            ("files", ("image.jpg", valid_file, "image/jpeg")),
            ("files", ("script.sh", bad_file, "text/x-shellscript"))
        ]
    )
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_reject_exceeding_max_batch_size():
    files = []
    for i in range(MAX_BATCH_SIZE + 2):
        files.append(("files", (f"file_{i}.jpg", io.BytesIO(b"data"), "image/jpeg")))

    response = client.post("/api/batch/analyze", files=files)
    assert response.status_code == 400
    assert "exceeds maximum limit" in response.json()["detail"]


def test_rate_limiter_unit_logic():
    limiter = InMemoryRateLimiter(default_limit=3, window_seconds=60)
    client_ip = "192.168.1.100"

    # First 3 requests should be permitted
    allowed, rem, _ = limiter.check(client_ip)
    assert allowed is True
    assert rem == 2

    allowed, rem, _ = limiter.check(client_ip)
    assert allowed is True
    assert rem == 1

    allowed, rem, _ = limiter.check(client_ip)
    assert allowed is True
    assert rem == 0

    # 4th request must be denied with retry_after
    allowed, rem, retry_after = limiter.check(client_ip)
    assert allowed is False
    assert rem == 0
    assert retry_after > 0


def test_rate_limit_http_429():
    # Temporarily set limit to 2 for this test
    rate_limiter.default_limit = 2
    try:
        # 1st request
        r1 = client.post(
            "/api/analyze",
            files={"file": ("test1.jpg", io.BytesIO(b"fake data 1"), "image/jpeg")}
        )
        assert r1.status_code == 200

        # 2nd request
        r2 = client.post(
            "/api/analyze",
            files={"file": ("test2.jpg", io.BytesIO(b"fake data 2"), "image/jpeg")}
        )
        assert r2.status_code == 200

        # 3rd request -> HTTP 429
        r3 = client.post(
            "/api/analyze",
            files={"file": ("test3.jpg", io.BytesIO(b"fake data 3"), "image/jpeg")}
        )
        assert r3.status_code == 429
        assert "Rate limit exceeded" in r3.json()["detail"]
        assert "Retry-After" in r3.headers
    finally:
        rate_limiter.default_limit = 60
