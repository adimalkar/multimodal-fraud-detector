"""Exercise truthful API outcomes without calling external model providers."""

import base64
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import app as app_module
from backend import db_service, qwen_agent


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "DATABASE_URL", None)
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "evaluations.db"))
    app_module.jobs.clear()
    app_module.batches.clear()
    app_module.rate_limiter.reset()
    with TestClient(app_module.app) as test_client:
        yield test_client
    app_module.jobs.clear()
    app_module.batches.clear()
    app_module.rate_limiter.reset()


def image_bytes():
    image = Image.new("RGB", (32, 32), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_unconfigured_providers_reject_analysis_before_creating_jobs(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "missing_model_credentials",
        lambda: ["OPENROUTER_API_KEY", "FEATHERLESS_API_KEY"],
    )

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["analysis_ready"] is False

    readiness = client.get("/api/ready")
    assert readiness.status_code == 503
    assert readiness.json()["detail"]["code"] == "MODEL_PROVIDERS_UNCONFIGURED"

    image = image_bytes()
    requests = [
        client.post("/api/analyze", files={"file": ("claim.jpg", image, "image/jpeg")}),
        client.post(
            "/api/batch/analyze",
            files=[("files", ("claim.jpg", image, "image/jpeg"))],
        ),
        client.post(
            "/api/analyze-url",
            json={"media_url": "https://example.com/claim.jpg", "filename": "claim.jpg"},
        ),
        client.post("/analyze_media", files={"file": ("claim.jpg", image, "image/jpeg")}),
    ]
    assert all(response.status_code == 503 for response in requests)
    assert app_module.jobs == {}
    assert app_module.batches == {}


def test_configured_provider_readiness(client, monkeypatch):
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    assert client.get("/api/health").json()["analysis_ready"] is True
    assert client.get("/api/ready").json() == {"status": "ready", "analysis_ready": True}


def test_completed_image_job_persists_result(client, monkeypatch):
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    model_result = {
        "classification": "Fake",
        "confidence_score": 0.8,
        "reason": "Controlled model response",
        "vision_findings": "Controlled finding",
        "vote_breakdown": {
            "critic_a": {"classification": "Fake", "confidence": 0.8},
            "critic_b": {"classification": "Fake", "confidence": 0.75},
        },
        "consensus": "unanimous",
    }
    with patch.object(app_module, "analyze_media", return_value=model_result):
        response = client.post(
            "/api/analyze", files={"file": ("claim.jpg", image_bytes(), "image/jpeg")}
        )

    assert response.status_code == 200
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "completed"
    assert job["result"]["classification"] == "Fake"
    assert client.get("/api/analytics/stats").json()["total_records"] == 1


def test_invalid_model_verdict_fails_job_without_persistence(client, monkeypatch):
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    model_result = {
        "classification": "Error",
        "confidence_score": 0.0,
        "reason": "All critic models failed",
        "vote_breakdown": {},
    }
    with patch.object(app_module, "analyze_media", return_value=model_result):
        response = client.post(
            "/api/analyze", files={"file": ("claim.jpg", image_bytes(), "image/jpeg")}
        )

    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "failed"
    assert "valid Real or Fake verdict" in job["error"]
    assert client.get("/api/analytics/stats").json()["total_records"] == 0


def test_batch_reports_failure_when_every_item_fails(client, monkeypatch):
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    with patch.object(app_module, "execute_agent_analysis", side_effect=RuntimeError("provider outage")):
        response = client.post(
            "/api/batch/analyze",
            files=[
                ("files", ("first.jpg", image_bytes(), "image/jpeg")),
                ("files", ("second.jpg", image_bytes(), "image/jpeg")),
            ],
        )

    batch = client.get(f"/api/batch/{response.json()['batch_id']}").json()
    assert batch["status"] == "failed"
    assert batch["summary"]["processed"] == 0
    assert batch["summary"]["error_count"] == 2
    assert batch["error"]
    assert all(item["status"] == "failed" for item in batch["items"])


def test_batch_keeps_partial_results_and_reports_item_error(client, monkeypatch):
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])

    def analyze(file_path, media_type, content_type):
        if "second.jpg" in file_path:
            raise RuntimeError("provider outage")
        return {
            "classification": "Real",
            "confidence": 0.8,
            "reason": "Controlled model response",
            "vision_findings": "Controlled finding",
            "elapsed_seconds": 0.1,
            "multimodal_risk": {"risk_score": 0.2, "severity_tier": "LOW_RISK"},
        }

    with patch.object(app_module, "execute_agent_analysis", side_effect=analyze):
        response = client.post(
            "/api/batch/analyze",
            files=[
                ("files", ("first.jpg", image_bytes(), "image/jpeg")),
                ("files", ("second.jpg", image_bytes(), "image/jpeg")),
            ],
        )

    batch = client.get(f"/api/batch/{response.json()['batch_id']}").json()
    assert batch["status"] == "completed"
    assert batch["summary"]["processed"] == 1
    assert batch["summary"]["error_count"] == 1
    assert batch["items"][0]["status"] == "completed"
    assert batch["items"][1]["error"] == "provider outage"
    assert client.get("/api/analytics/stats").json()["total_records"] == 1


def test_video_failure_preserves_first_frame_error(monkeypatch):
    monkeypatch.setattr(qwen_agent, "missing_model_credentials", lambda: [])
    frame = base64.b64encode(image_bytes()).decode("ascii")
    monkeypatch.setattr(qwen_agent, "extract_video_frames", lambda *args, **kwargs: [frame, frame])
    monkeypatch.setattr(
        qwen_agent,
        "analyze_media",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider outage")),
    )

    with pytest.raises(RuntimeError, match="All 2 video frames failed analysis.*provider outage"):
        qwen_agent.analyze_video("unused.mp4")
