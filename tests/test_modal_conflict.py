from backend.risk_scorer import ModalConflictDetector


def test_congruent_modalities():
    detector = ModalConflictDetector()
    res = detector.evaluate_modalities({"text": 0.85, "visual": 0.88, "metadata": 0.82})
    assert res["conflict_detected"] is False
    assert res["conflict_tier"] == "CONGRUENT"
    assert res["conflict_penalty"] == 0.0
    assert res["max_divergence"] < 0.10


def test_mild_discrepancy():
    detector = ModalConflictDetector()
    res = detector.evaluate_modalities({"text": 0.35, "visual": 0.65})
    assert res["conflict_tier"] == "MILD_DISCREPANCY"
    assert res["conflict_detected"] is False
    assert 0.25 <= res["max_divergence"] < 0.45


def test_critical_modal_masking_dilution_prevention():
    detector = ModalConflictDetector()
    # Attacker crafts benign text (0.05) to mask acute visual deepfake (0.95)
    res = detector.evaluate_modalities({"text": 0.05, "visual": 0.95})
    assert res["conflict_detected"] is True
    assert res["conflict_tier"] == "CRITICAL_MODAL_MASKING"
    assert res["max_divergence"] == 0.90
    assert res["conflict_penalty"] > 0.15

    # Standard linear mean is 0.50 (might slip past thresholds)
    assert res["linear_fused_risk"] == 0.50
    # Adjusted risk preserves the critical acute signal
    assert res["adjusted_fused_risk"] > 0.70


def test_high_conflict_three_modalities():
    detector = ModalConflictDetector()
    res = detector.evaluate_modalities({"text": 0.10, "visual": 0.65, "metadata": 0.20})
    assert res["conflict_detected"] is True
    assert res["conflict_tier"] == "HIGH_CONFLICT"
    assert len(res["divergence_pairs"]) == 3
    assert res["conflict_penalty"] > 0.0


def test_single_or_empty_modality():
    detector = ModalConflictDetector()
    res_empty = detector.evaluate_modalities({})
    assert res_empty["conflict_tier"] == "CONGRUENT"
    assert res_empty["adjusted_fused_risk"] == 0.0

    res_single = detector.evaluate_modalities({"visual": 0.72})
    assert res_single["conflict_tier"] == "CONGRUENT"
    assert res_single["adjusted_fused_risk"] == 0.72
    assert len(res_single["divergence_pairs"]) == 0
