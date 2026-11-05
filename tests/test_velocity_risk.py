from backend.risk_scorer import TransactionVelocityTracker


def test_velocity_tracker_single_event():
    tracker = TransactionVelocityTracker(window_seconds=60.0, burst_threshold=3)
    res = tracker.record_event("user_123", timestamp=100.0)
    assert res["entity_id"] == "user_123"
    assert res["window_count"] == 1
    assert res["velocity_multiplier"] == 1.0
    assert not res["burst_flagged"]


def test_velocity_tracker_burst_multiplier():
    tracker = TransactionVelocityTracker(
        window_seconds=60.0, burst_threshold=3, max_multiplier=1.6
    )
    # Record 3 events at t=10, 20, 30
    tracker.record_event("user_abc", timestamp=10.0)
    tracker.record_event("user_abc", timestamp=20.0)
    res3 = tracker.record_event("user_abc", timestamp=30.0)
    assert res3["window_count"] == 3
    assert res3["burst_flagged"]
    assert res3["velocity_multiplier"] == 1.0

    # 4th event exceeds threshold, increases multiplier
    res4 = tracker.record_event("user_abc", timestamp=40.0)
    assert res4["window_count"] == 4
    assert res4["velocity_multiplier"] > 1.0

    # 8th event hits max multiplier
    for i in range(5):
        res_high = tracker.record_event("user_abc", timestamp=41.0 + i)
    assert res_high["velocity_multiplier"] >= 1.6


def test_velocity_tracker_window_eviction():
    tracker = TransactionVelocityTracker(window_seconds=10.0, burst_threshold=2)
    tracker.record_event("user_xyz", timestamp=10.0)
    tracker.record_event("user_xyz", timestamp=15.0)

    # Next event at t=26 (outside 10s window of t=10 and t=15)
    res_later = tracker.record_event("user_xyz", timestamp=26.0)
    assert res_later["window_count"] == 1
    assert res_later["velocity_multiplier"] == 1.0


def test_compute_adjusted_risk():
    tracker = TransactionVelocityTracker(burst_threshold=2, max_multiplier=1.5)
    tracker.record_event("user_999", timestamp=10.0)
    tracker.record_event("user_999", timestamp=20.0)

    # 3rd event should increase multiplier
    adj = tracker.compute_adjusted_risk(0.60, "user_999", timestamp=30.0)
    assert adj["base_risk_score"] == 0.60
    assert adj["adjusted_risk_score"] > 0.60
    assert adj["velocity_multiplier"] > 1.0
    assert adj["burst_flagged"]
