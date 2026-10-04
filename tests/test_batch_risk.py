from backend.risk_scorer import MultimodalRiskScorer


def test_calculate_confidence_interval_basic():
    scorer = MultimodalRiskScorer()
    # Empty
    assert scorer.calculate_confidence_interval([]) == (0.0, 0.0)
    # Single sample
    assert scorer.calculate_confidence_interval([0.5]) == (0.5, 0.5)
    # Multiple samples
    samples = [0.1, 0.15, 0.12, 0.14, 0.11]
    lower, upper = scorer.calculate_confidence_interval(samples, confidence=0.95)
    assert 0.0 <= lower <= upper <= 1.0
    mean = sum(samples) / len(samples)
    assert lower <= mean <= upper


def test_evaluate_batch_empty():
    scorer = MultimodalRiskScorer()
    res = scorer.evaluate_batch([])
    assert res["total_records"] == 0
    assert res["mean_risk"] == 0.0
    assert res["outlier_count"] == 0


def test_evaluate_batch_cohort_and_outliers():
    scorer = MultimodalRiskScorer()
    # Normal low-risk cohort with 1 extreme fraudulent outlier
    records = [
        {
            "id": f"txn_{i}",
            "text_score": 0.05,
            "visual_score": 0.05,
            "metadata_flags": 0,
        }
        for i in range(15)
    ]
    # Add outlier transaction
    records.append(
        {
            "id": "txn_fraud",
            "text_score": 0.95,
            "visual_score": 0.95,
            "metadata_flags": 4,
        }
    )

    result = scorer.evaluate_batch(records, z_score_outlier_threshold=2.0)
    assert result["total_records"] == 16
    assert result["tier_distribution"]["LOW_RISK"] == 15
    assert result["tier_distribution"]["CRITICAL_FRAUD"] == 1
    assert result["outlier_count"] >= 1
    assert any(o["record_id"] == "txn_fraud" for o in result["outliers"])


def test_evaluate_batch_without_synergy():
    scorer = MultimodalRiskScorer()
    records = [
        {"id": "rec1", "text_score": 0.7, "visual_score": 0.7, "metadata_flags": 0}
    ]
    res_no_syn = scorer.evaluate_batch(records, synergy_boost_enabled=False)
    res_syn = scorer.evaluate_batch(records, synergy_boost_enabled=True)
    assert res_syn["mean_risk"] > res_no_syn["mean_risk"]
