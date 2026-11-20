import pytest

from backend.risk_scorer import RiskPopulationDriftMonitor


def test_identical_distributions_no_drift():
    monitor = RiskPopulationDriftMonitor(default_bins=5)
    sample = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

    result = monitor.evaluate_drift(sample, sample)

    assert result["psi"] < 0.05
    assert result["wasserstein_distance"] == 0.0
    assert result["drift_level"] == "STABLE"
    assert result["requires_retraining"] is False
    assert result["recommended_action"] == "NO_ACTION_REQUIRED"
    assert result["mean_shift"] == 0.0


def test_moderate_distribution_drift():
    monitor = RiskPopulationDriftMonitor(default_bins=10)
    # Baseline: centered around lower risk [0.1, 0.3]
    reference = [0.05, 0.10, 0.12, 0.15, 0.18, 0.22, 0.25, 0.28, 0.32, 0.35] * 10
    # Current: moderately shifted upwards [0.25, 0.55]
    current = [0.20, 0.25, 0.30, 0.35, 0.40, 0.42, 0.45, 0.48, 0.50, 0.55] * 10

    result = monitor.evaluate_drift(reference, current)

    assert result["psi"] >= 0.10
    assert result["wasserstein_distance"] > 0.0
    assert result["drift_level"] in ("MODERATE_DRIFT", "SIGNIFICANT_DRIFT")
    assert result["mean_shift"] > 0.0
    assert len(result["bin_breakdown"]) == 10


def test_significant_fraud_surge_drift():
    monitor = RiskPopulationDriftMonitor(default_bins=5)
    # Baseline: strictly low-risk benign transactions
    reference = [0.01, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15] * 20
    # Current: massive fraud wave attacking system with extreme risk scores
    current = [0.75, 0.80, 0.85, 0.90, 0.92, 0.95, 0.98] * 20

    result = monitor.evaluate_drift(reference, current)

    assert result["psi"] >= 0.25
    assert result["drift_level"] == "SIGNIFICANT_DRIFT"
    assert result["requires_retraining"] is True
    assert result["recommended_action"] == "RETRAIN_MODEL_AND_RECALIBRATE_CUTOFFS"
    assert result["mean_shift"] > 0.60


def test_wasserstein_distance_metric():
    monitor = RiskPopulationDriftMonitor()
    # Direct 1.0 unit shift
    u = [1.0, 2.0, 3.0]
    v = [2.0, 3.0, 4.0]

    w_dist = monitor.compute_wasserstein_distance(u, v)
    assert abs(w_dist - 1.0) < 1e-4

    # Identical samples
    assert monitor.compute_wasserstein_distance([5.0, 5.0], [5.0, 5.0]) == 0.0


def test_drift_monitor_input_validation():
    monitor = RiskPopulationDriftMonitor()

    with pytest.raises(ValueError, match="at least 2"):
        RiskPopulationDriftMonitor(default_bins=1)

    with pytest.raises(ValueError, match="non-empty"):
        monitor.compute_psi([], [0.5])

    with pytest.raises(ValueError, match="non-empty"):
        monitor.compute_psi([0.5], [])

    with pytest.raises(ValueError, match="must not be empty"):
        monitor.compute_wasserstein_distance([], [1.0])


def test_constant_value_edge_case():
    monitor = RiskPopulationDriftMonitor()
    psi_val, breakdown = monitor.compute_psi([0.5, 0.5], [0.5, 0.5])
    assert psi_val == 0.0
    assert breakdown == []
