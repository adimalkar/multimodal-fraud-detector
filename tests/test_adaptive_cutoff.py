import pytest

from backend.risk_scorer import AdaptiveCutoffOptimizer


def test_perfect_separation_metrics():
    optimizer = AdaptiveCutoffOptimizer()
    scores = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
    labels = [0, 0, 0, 1, 1, 1]

    metrics = optimizer.compute_metrics_at_threshold(scores, labels, threshold=0.5)

    assert metrics["accuracy"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["fpr"] == 0.0
    assert metrics["f1_score"] == 1.0
    assert metrics["mcc"] == 1.0
    assert metrics["expected_financial_cost"] == 0.0


def test_optimize_for_max_f1():
    optimizer = AdaptiveCutoffOptimizer(step_size=0.05)
    # Mixed scores with overlap around 0.4 - 0.6
    scores = [0.1, 0.2, 0.3, 0.45, 0.55, 0.7, 0.85, 0.9]
    labels = [0, 0, 0, 1, 0, 1, 1, 1]

    result = optimizer.optimize_cutoff(scores, labels, strategy="MAX_F1")

    assert 0.0 <= result["optimal_threshold"] <= 1.0
    assert result["strategy"] == "MAX_F1"
    assert result["metrics_at_optimal"]["f1_score"] >= 0.80
    assert "Calibrate operational decision cutoff" in result["recommendation"]


def test_optimize_for_fpr_budget():
    optimizer = AdaptiveCutoffOptimizer(step_size=0.05)
    scores = [0.05, 0.15, 0.25, 0.35, 0.60, 0.80, 0.90]
    labels = [0, 0, 0, 0, 1, 1, 1]

    # Constrain FPR to strictly 0.0
    result = optimizer.optimize_cutoff(
        scores, labels, strategy="FPR_BUDGET", max_fpr=0.0
    )

    assert result["metrics_at_optimal"]["fpr"] == 0.0
    assert result["metrics_at_optimal"]["recall"] == 1.0


def test_optimize_for_cost_minimization():
    optimizer = AdaptiveCutoffOptimizer(step_size=0.05)
    scores = [0.2, 0.4, 0.6, 0.8]
    labels = [0, 1, 0, 1]

    # Extreme fraud loss (cost_fn=10000) vs small review cost (cost_fp=10)
    # should incentivize lower threshold to capture label=1 at score=0.4
    result = optimizer.optimize_cutoff(
        scores, labels, strategy="MIN_COST", cost_fn=10000.0, cost_fp=10.0
    )

    assert result["optimal_threshold"] <= 0.40
    assert result["metrics_at_optimal"]["fn"] == 0


def test_curve_sweep_generation():
    optimizer = AdaptiveCutoffOptimizer(step_size=0.1)
    scores = [0.1, 0.5, 0.9]
    labels = [0, 1, 1]

    curve = optimizer.evaluate_threshold_curve(scores, labels)
    # 0.0, 0.1, ..., 1.0 = 11 steps
    assert len(curve) == 11
    assert curve[0]["threshold"] == 0.0
    assert curve[-1]["threshold"] == 1.0


def test_input_validation():
    with pytest.raises(ValueError, match="step_size must be between"):
        AdaptiveCutoffOptimizer(step_size=0.5)

    optimizer = AdaptiveCutoffOptimizer()

    with pytest.raises(ValueError, match="same length"):
        optimizer.compute_metrics_at_threshold([0.5], [1, 0], threshold=0.5)

    with pytest.raises(ValueError, match="must not be empty"):
        optimizer.compute_metrics_at_threshold([], [], threshold=0.5)
