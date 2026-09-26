import tempfile
import pytest
from PIL import Image
from starlette.testclient import TestClient
from backend.risk_scorer import MultimodalRiskScorer
from backend.metadata_extractor import extract_metadata
from backend.db_service import save_evaluation, get_analytics_summary
from backend.app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_risk_scorer_heuristics_and_synergy():
    scorer = MultimodalRiskScorer()
    
    # Low risk
    low = scorer.calculate_risk(text_score=0.1, visual_score=0.1, metadata_flags=0)
    assert low["severity_tier"] == "LOW_RISK"
    assert low["recommended_action"] == "APPROVE_AUTOMATICALLY"
    assert not low["cross_modal_synergy_applied"]

    # Critical fraud with compounding synergy
    crit = scorer.calculate_risk(text_score=0.85, visual_score=0.90, metadata_flags=3)
    assert crit["severity_tier"] == "CRITICAL_FRAUD"
    assert crit["recommended_action"] == "BLOCK_TRANSACTION_AND_ALERT_SECURITY"
    assert crit["cross_modal_synergy_applied"] is True
    assert crit["risk_score"] > 0.80

def test_metadata_extractor_image_flags():
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        # Create an exact 1024x1024 synthetic image (AI typical dimension)
        img = Image.new("RGB", (1024, 1024), color=(20, 40, 80))
        img.save(f.name, "JPEG")

        res = extract_metadata(f.name, "Image")
        assert "metadata" in res
        assert "flags" in res
        assert res["flags_count"] > 0
        assert res["metadata"]["dimensions"] == "1024x1024"

def test_metadata_extractor_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        # Mock PDF header with suspicious producer Canva
        f.write(b"%PDF-1.4\n1 0 obj\n<< /Creator (Canva) /Producer (Canva PDF Engine) >>\nendobj\n%%EOF")
        f.flush()

        res = extract_metadata(f.name, "Document")
        assert res["metadata"]["format"] == "PDF"
        assert res["flags_count"] > 0
        assert any("Canva" in flag for flag in res["flags"])

def test_db_save_and_retrieve_risk_metrics():
    rec_id = save_evaluation(
        filename="test_claim.jpg",
        media_type="Image",
        ai_prediction="Fake",
        confidence=0.95,
        final_reasoning="Synthesized pixels and mismatched reflections.",
        vision_findings="Deepfake lighting discrepancy",
        processing_time=1.2,
        risk_score=0.94,
        severity_tier="CRITICAL_FRAUD",
        recommended_action="BLOCK_TRANSACTION_AND_ALERT_SECURITY"
    )
    assert rec_id is not None
    assert rec_id > 0

    stats = get_analytics_summary()
    assert "severity_breakdown" in stats
    assert "critical_fraud" in stats["severity_breakdown"]
    assert stats["severity_breakdown"]["critical_fraud"] >= 1

def test_analytics_stats_endpoint_includes_severity(client):
    response = client.get("/api/analytics/stats")
    assert response.status_code == 200
    data = response.json()
    assert "severity_breakdown" in data
    assert "critical_fraud" in data["severity_breakdown"]
    assert "high_risk" in data["severity_breakdown"]
    assert "suspicious" in data["severity_breakdown"]
    assert "low_risk" in data["severity_breakdown"]
