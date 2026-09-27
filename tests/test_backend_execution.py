"""Exercise truthful API outcomes without calling external model providers."""

import base64
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import app as app_module
from backend import db_service, provider_readiness, qwen_agent


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "DATABASE_URL", None)
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "evaluations.db"))
    app_module.jobs.clear()
    app_module.batches.clear()
    app_module.rate_limiter.reset()
    monkeypatch.setattr(
        app_module,
        "verify_provider_authentication",
        lambda: {
            "openrouter": {"status": "authenticated", "http_status": 200},
        },
    )
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
        lambda: ["OPENROUTER_API_KEY"],
    )

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["providers_configured"] is False

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
    assert client.get("/api/health").json()["providers_configured"] is True
    assert client.get("/api/ready").json() == {"status": "ready", "analysis_ready": True}


def test_rejected_provider_blocks_jobs_without_exposing_keys(client, monkeypatch):
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    monkeypatch.setattr(
        app_module,
        "verify_provider_authentication",
        lambda: {
            "openrouter": {"status": "rejected", "http_status": 401},
        },
    )

    readiness = client.get("/api/ready")
    assert readiness.status_code == 503
    assert readiness.json()["detail"]["code"] == "MODEL_PROVIDERS_UNAVAILABLE"
    assert readiness.json()["detail"]["providers"]["openrouter"]["http_status"] == 401

    submission = client.post(
        "/api/analyze", files={"file": ("claim.jpg", image_bytes(), "image/jpeg")}
    )
    assert submission.status_code == 503
    assert app_module.jobs == {}


def test_provider_authentication_uses_account_endpoints_and_caches_status(monkeypatch):
    monkeypatch.setattr(
        provider_readiness,
        "AUTH_CHECKS",
        {
            "openrouter": ("https://openrouter.ai/api/v1/key", "test-openrouter-secret"),
        },
    )
    provider_readiness._cache.update(expires_at=0.0, result=None)
    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return type("Response", (), {"status_code": 401})()

    monkeypatch.setattr(provider_readiness.requests, "get", fake_get)
    result = provider_readiness.verify_provider_authentication()
    assert result["openrouter"] == {"status": "rejected", "http_status": 401}
    assert "test-openrouter-secret" not in str(result)
    assert len(calls) == 1
    assert provider_readiness.verify_provider_authentication() == result
    assert len(calls) == 1
    provider_readiness._cache.update(expires_at=0.0, result=None)


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


def test_video_failure_preserves_provider_error(monkeypatch):
    monkeypatch.setattr(qwen_agent, "missing_model_credentials", lambda: [])
    frame = base64.b64encode(image_bytes()).decode("ascii")
    monkeypatch.setattr(qwen_agent, "extract_video_frames", lambda *args, **kwargs: [frame, frame])
    monkeypatch.setattr(
        qwen_agent,
        "_analyze_images",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider outage")),
    )

    with pytest.raises(RuntimeError, match="provider outage"):
        qwen_agent.analyze_video("unused.mp4")


def test_video_uses_one_bounded_vision_request(monkeypatch):
    monkeypatch.setattr(qwen_agent, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(qwen_agent, "VISION_MODEL_ID", "google/gemma-4-26b-a4b-it")
    frame = base64.b64encode(image_bytes()).decode("ascii")
    monkeypatch.setattr(qwen_agent, "extract_video_frames", lambda *args, **kwargs: [frame] * 3)
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return type("Response", (), {
            "status_code": 200,
            "json": lambda self: {
                "choices": [{"message": {"content": '{"classification":"Fake","confidence_score":0.7,"vision_findings":"An inconsistent reflection is visible.","reason":"The reflection warrants review."}'}}],
                "usage": {"prompt_tokens": 150, "completion_tokens": 40, "cost": 0.0001},
            },
        })()

    monkeypatch.setattr(qwen_agent.requests, "post", fake_post)
    result = qwen_agent.analyze_video("unused.mp4")

    assert len(calls) == 1
    url, headers, payload, timeout = calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "google/gemma-4-26b-a4b-it"
    assert payload["max_tokens"] == 350
    assert len(payload["messages"][1]["content"]) == 4
    assert timeout == (10, 90)
    assert result["model_usage"]["cost"] == 0.0001
    assert result["consensus"] == "sampled_frames_single_model"
    assert result["needs_review"] is True


def test_unapproved_model_fails_before_billing(monkeypatch):
    monkeypatch.setattr(qwen_agent, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(qwen_agent, "VISION_MODEL_ID", "expensive/model")
    with patch.object(qwen_agent.requests, "post") as post:
        with pytest.raises(RuntimeError, match="low-cost allowlist"):
            qwen_agent._analyze_images(["image-data"], "Image")
        post.assert_not_called()


def test_pdf_page_limit_rejects_before_render_or_billing(monkeypatch):
    runs = []

    def fake_run(command, **kwargs):
        runs.append(command[0])
        return type("Result", (), {"stdout": "Pages: 4\n"})()

    monkeypatch.setattr(qwen_agent.subprocess, "run", fake_run)
    with patch.object(qwen_agent.requests, "post") as post:
        with pytest.raises(ValueError, match="1 to 3 pages"):
            qwen_agent.analyze_media("claim.pdf", "application/pdf", media_type="Document")
        post.assert_not_called()
    assert runs == ["pdfinfo"]


def test_single_model_result_never_recommends_automatic_policy_action(client, monkeypatch):
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    result = {
        "classification": "Real",
        "confidence_score": 0.95,
        "reason": "No visible artifacts.",
        "vision_findings": "A normal street scene.",
        "vote_breakdown": {"google/gemma-4-26b-a4b-it": {"classification": "Real", "confidence": 0.95}},
        "consensus": "single_model",
        "model_usage": {"cost": 0.0001},
        "needs_review": True,
    }
    with patch.object(app_module, "analyze_media", return_value=result):
        response = client.post("/api/analyze", files={"file": ("claim.jpg", image_bytes(), "image/jpeg")})
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    output = job["result"]
    assert output["multimodal_risk"]["recommended_action"] == "MANUAL_REVIEW"
    assert output["multimodal_risk"]["cross_modal_synergy_applied"] is False
    assert output["multimodal_risk"]["breakdown"]["text_contribution"] == 0
    assert output["needs_review"] is True
