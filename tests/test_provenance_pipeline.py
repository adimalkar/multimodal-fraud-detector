"""Provenance runs before the model, and an unreadable model answer completes the job without a score."""

import io
from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient

from backend import app as app_module
from backend import db_service
from backend.app import app, jobs
from backend.guardrails import rate_limiter
from backend.qwen_agent import ModelOutputUnusable

AI_JPEG = Path(__file__).parent / "fixtures" / "c2pa_ai_generated_untrusted.jpg"
REAL = {"classification": "Real", "confidence_score": 0.9, "reason": "Looks fine.", "vision_findings": "A car.",
        "vote_breakdown": {"google/gemma-4-26b-a4b-it": {"classification": "Real", "confidence": 0.9}},
        "consensus": "single_model", "model_usage": {"calls": 1, "cost": 0.0001}, "needs_review": True}


def plain_jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 140, 160)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_service, "DATABASE_URL", None)
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "evidence.db"))
    jobs.clear()
    rate_limiter.reset()
    monkeypatch.setattr(app_module, "missing_model_credentials", lambda: [])
    monkeypatch.setattr(app_module, "verify_provider_authentication",
                        lambda: {"openrouter": {"status": "authenticated", "http_status": 200}})
    with TestClient(app) as test_client:
        yield test_client
    jobs.clear()
    rate_limiter.reset()


def screen(client, name, data):
    response = client.post("/api/analyze", files={"file": (name, data, "image/jpeg")})
    assert response.status_code == 200, response.text
    return client.get(f"/api/jobs/{response.json()['job_id']}").json()


def test_signed_ai_declaration_skips_the_model(client, monkeypatch):
    monkeypatch.setattr(app_module, "analyze_media", lambda *args, **kwargs: pytest.fail("model was called"))
    job = screen(client, "render.jpg", AI_JPEG.read_bytes())
    result = job["result"]
    assert job["status"] == "completed"
    assert result["classification"] == "Fake"
    assert result["model_usage"]["calls"] == 0
    assert result["multimodal_risk"]["risk_score"] == 0.95
    assert result["multimodal_risk"]["recommended_action"] == "MANUAL_REVIEW"
    assert result["multimodal_risk"]["breakdown"] is None
    assert "declare this file AI-generated" in result["multimodal_risk"]["metadata_flags"][0]
    assert result["provenance"]["decisive"] is True
    assert client.get("/api/analytics/stats").json()["total_records"] == 1


def test_moderate_finding_raises_a_low_model_score(client, monkeypatch):
    monkeypatch.setattr(app_module, "analyze_media", lambda *args, **kwargs: {**REAL, "visible_watermark": "Veo"})
    result = screen(client, "claim.jpg", plain_jpeg())["result"]
    assert result["classification"] == "Real"
    assert result["multimodal_risk"]["risk_score"] == 0.70
    assert result["multimodal_risk"]["severity_tier"] == "HIGH_RISK"
    assert any("Veo" in flag for flag in result["multimodal_risk"]["metadata_flags"])


def test_provenance_never_lowers_a_score(client, monkeypatch):
    fake = {**REAL, "classification": "Fake", "confidence_score": 0.98, "visible_watermark": "Veo",
            "vote_breakdown": {"google/gemma-4-26b-a4b-it": {"classification": "Fake", "confidence": 0.98}}}
    monkeypatch.setattr(app_module, "analyze_media", lambda *args, **kwargs: fake)
    assert screen(client, "claim.jpg", plain_jpeg())["result"]["multimodal_risk"]["risk_score"] == 0.98


def test_unreadable_model_answer_completes_without_a_score(client, monkeypatch):
    def unusable(*args, **kwargs):
        raise ModelOutputUnusable("output is not a JSON object")

    monkeypatch.setattr(app_module, "analyze_media", unusable)
    job = screen(client, "claim.jpg", plain_jpeg())
    result = job["result"]
    assert job["status"] == "completed"
    assert result["classification"] == "Unknown"
    assert result["multimodal_risk"]["risk_score"] is None
    assert result["multimodal_risk"]["severity_tier"] is None
    assert "didn't return a usable answer" in result["reason"]
    recent = client.get("/api/analytics/stats").json()["recent_evaluations"][0]
    assert recent["ai_prediction"] == "Unknown" and recent["risk_score"] is None


def test_unreadable_answer_keeps_a_provenance_floor(client, monkeypatch):
    monkeypatch.setattr(app_module, "run_provenance", lambda *args: {
        "checks": [], "decisive": False,
        "findings": [{"kind": "visible_watermark", "strength": "moderate", "source": "visible_watermark",
                      "summary": "Visible text along the frame edge matches an AI generator's mark: \"Sora\"."}]})

    def unusable(*args, **kwargs):
        raise ModelOutputUnusable("output is not a JSON object")

    monkeypatch.setattr(app_module, "analyze_media", unusable)
    result = screen(client, "claim.jpg", plain_jpeg())["result"]
    assert result["multimodal_risk"]["risk_score"] == 0.70


def test_provider_error_still_fails_the_job(client, monkeypatch):
    def down(*args, **kwargs):
        raise RuntimeError("OpenRouter vision request failed with HTTP 502")

    monkeypatch.setattr(app_module, "analyze_media", down)
    job = screen(client, "claim.jpg", plain_jpeg())
    assert job["status"] == "failed"
    assert "HTTP 502" in job["error"]


def test_provenance_crash_does_not_block_screening(client, monkeypatch):
    def broken(*args):
        raise ValueError("unexpected")

    monkeypatch.setattr(app_module, "inspect_provenance", broken)
    monkeypatch.setattr(app_module, "analyze_media", lambda *args, **kwargs: REAL)
    result = screen(client, "claim.jpg", plain_jpeg())["result"]
    assert result["classification"] == "Real"
    assert result["provenance"]["error"]
