from backend.risk_scorer import DeviceGeoAnomalyDetector


def test_haversine_identical_coordinates():
    dist = DeviceGeoAnomalyDetector.haversine_distance(
        40.7128, -74.0060, 40.7128, -74.0060
    )
    assert dist == 0.0


def test_haversine_nyc_to_london():
    # NYC (40.7128, -74.0060) to London (51.5074, -0.1278) ~ 5570 km
    dist = DeviceGeoAnomalyDetector.haversine_distance(
        40.7128, -74.0060, 51.5074, -0.1278
    )
    assert 5500.0 < dist < 5600.0


def test_first_event_initial_baseline():
    detector = DeviceGeoAnomalyDetector()
    res = detector.record_and_evaluate(
        user_id="user_test1",
        lat=40.7128,
        lon=-74.0060,
        timestamp=1000.0,
        device_fingerprint="dev_fp_1",
    )
    assert res["user_id"] == "user_test1"
    assert res["geo_risk_score"] == 0.0
    assert not res["impossible_travel_detected"]
    assert res["severity_tier"] == "LOW_RISK"
    assert res["calculated_speed_kmh"] == 0.0
    assert len(res["anomaly_flags"]) == 0


def test_plausible_travel_speed():
    detector = DeviceGeoAnomalyDetector()
    # Event 1 in Philadelphia
    detector.record_and_evaluate(
        user_id="user_traveler",
        lat=39.9526,
        lon=-75.1652,
        timestamp=1000.0,
        device_fingerprint="phone_1",
    )
    # Event 2 in NYC (~130 km away) 2.5 hours later (speed ~ 52 km/h)
    res = detector.record_and_evaluate(
        user_id="user_traveler",
        lat=40.7128,
        lon=-74.0060,
        timestamp=1000.0 + (2.5 * 3600.0),
        device_fingerprint="phone_1",
    )
    assert not res["impossible_travel_detected"]
    assert 40.0 < res["calculated_speed_kmh"] < 65.0
    assert res["severity_tier"] == "LOW_RISK"
    assert len(res["anomaly_flags"]) == 0


def test_impossible_travel_transatlantic():
    detector = DeviceGeoAnomalyDetector(max_plausible_speed_kmh=900.0)
    # Event 1 in New York at t=0
    detector.record_and_evaluate(
        user_id="user_supersonic",
        lat=40.7128,
        lon=-74.0060,
        timestamp=0.0,
        device_fingerprint="laptop_1",
    )
    # Event 2 in London (~5570 km away) 30 minutes later (speed > 11,000 km/h)
    res = detector.record_and_evaluate(
        user_id="user_supersonic",
        lat=51.5074,
        lon=-0.1278,
        timestamp=1800.0,
        device_fingerprint="laptop_1",
    )
    assert res["impossible_travel_detected"] is True
    assert res["calculated_speed_kmh"] > 9000.0
    assert res["geo_risk_score"] >= 0.80
    assert res["severity_tier"] in ("HIGH_RISK", "CRITICAL_FRAUD")
    assert any("IMPOSSIBLE_TRAVEL_SPEED" in flag for flag in res["anomaly_flags"])


def test_impossible_concurrent_travel():
    detector = DeviceGeoAnomalyDetector()
    # Event 1 at t=100 in Los Angeles
    detector.record_and_evaluate(
        user_id="user_clone",
        lat=34.0522,
        lon=-118.2437,
        timestamp=100.0,
    )
    # Event 2 at t=101 (1 second later) in Chicago (~2800 km away)
    res = detector.record_and_evaluate(
        user_id="user_clone",
        lat=41.8781,
        lon=-87.6298,
        timestamp=101.0,
    )
    assert res["impossible_travel_detected"] is True
    assert res["geo_risk_score"] >= 0.90
    assert res["severity_tier"] == "CRITICAL_FRAUD"
    assert any("IMPOSSIBLE_CONCURRENT_TRAVEL" in flag for flag in res["anomaly_flags"])


def test_device_fingerprint_churn():
    detector = DeviceGeoAnomalyDetector(max_allowed_devices_in_window=3)
    user = "user_churn"
    t = 1000.0

    # User uses 3 distinct devices: allowed
    for i in range(3):
        detector.record_and_evaluate(
            user_id=user,
            lat=40.0,
            lon=-74.0,
            timestamp=t + (i * 60.0),
            device_fingerprint=f"device_{i}",
        )

    # 4th distinct device exceeds max_allowed_devices_in_window (3)
    res = detector.record_and_evaluate(
        user_id=user,
        lat=40.0,
        lon=-74.0,
        timestamp=t + 300.0,
        device_fingerprint="device_4th_unusual",
    )
    assert res["device_churn_detected"] is True
    assert res["distinct_devices_count"] == 4
    assert res["geo_risk_score"] >= 0.60
    assert any("HIGH_DEVICE_CHURN" in flag for flag in res["anomaly_flags"])


def test_vpn_datacenter_proxy_flag():
    detector = DeviceGeoAnomalyDetector()
    res = detector.record_and_evaluate(
        user_id="user_vpn",
        lat=37.7749,
        lon=-122.4194,
        timestamp=100.0,
        is_vpn_or_datacenter=True,
    )
    assert res["geo_risk_score"] >= 0.35
    assert res["severity_tier"] == "SUSPICIOUS"
    assert "DATACENTER_OR_ANONYMOUS_PROXY_DETECTED" in res["anomaly_flags"]


def test_history_bounding():
    detector = DeviceGeoAnomalyDetector()
    user = "user_stream"
    for i in range(30):
        detector.record_and_evaluate(
            user_id=user,
            lat=40.0 + (i * 0.001),
            lon=-74.0,
            timestamp=float(i * 10),
        )
    assert len(detector.location_history[user]) <= 20
