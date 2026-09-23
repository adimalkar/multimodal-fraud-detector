import io
import uuid
import pytest
from starlette.testclient import TestClient
from backend.app import app, jobs

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "active_jobs" in data

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "endpoints" in data

def test_analyze_empty_file_validation(client):
    response = client.post("/api/analyze", files={"file": ("", b"", "image/jpeg")})
    assert response.status_code in [400, 422]

def test_create_and_poll_job(client):
    test_image = io.BytesIO(b"fake image data")
    response = client.post(
        "/api/analyze",
        files={"file": ("claim_photo.jpg", test_image, "image/jpeg")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["media_type"] == "Image"

    job_id = data["job_id"]

    # Poll status
    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["job_id"] == job_id
    assert status_data["status"] in ["queued", "processing", "completed", "failed"]

def test_poll_nonexistent_job_returns_404(client):
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/jobs/{fake_id}")
    assert response.status_code == 404
    assert "detail" in response.json()

def test_storage_presigned_url_endpoint(client):
    response = client.post(
        "/api/storage/presigned-url",
        json={"filename": "damage.mp4", "content_type": "video/mp4"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "storage_configured" in data
    assert "key" in data

def test_analyze_url_endpoint(client):
    response = client.post(
        "/api/analyze-url",
        json={"media_url": "https://example.com/test.jpg", "filename": "test.jpg"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"

def test_analytics_stats_endpoint(client):
    response = client.get("/api/analytics/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_records" in data
    assert "flagged_rate_percentage" in data
    assert "media_counts" in data

def test_analytics_csv_export(client):
    response = client.get("/api/analytics/export-csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "File Name" in response.text

def test_batch_analyze_and_poll_status(client):
    file1 = ("image1.jpg", io.BytesIO(b"file 1 dummy data"), "image/jpeg")
    file2 = ("document2.pdf", io.BytesIO(b"file 2 dummy pdf"), "application/pdf")

    response = client.post(
        "/api/batch/analyze",
        files=[("files", file1), ("files", file2)]
    )
    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    assert data["status"] == "queued"
    assert data["total_files"] == 2

    batch_id = data["batch_id"]

    # Poll batch status
    poll_res = client.get(f"/api/batch/{batch_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["batch_id"] == batch_id
    assert poll_data["total_items"] == 2
    assert "summary" in poll_data
    assert "items" in poll_data
    assert len(poll_data["items"]) == 2

def test_batch_analyze_validation(client):
    response = client.post(
        "/api/batch/analyze",
        files=[("files", ("", io.BytesIO(b""), "image/jpeg"))]
    )
    assert response.status_code in [400, 422]

def test_batch_status_404(client):
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/batch/{fake_id}")
    assert response.status_code == 404

