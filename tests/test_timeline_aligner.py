from backend.risk_scorer import ForensicEventTimelineAligner


def test_coherent_timeline_valid():
    aligner = ForensicEventTimelineAligner()
    incident_time = "2026-11-15T14:00:00Z"
    filing_time = "2026-11-15T18:00:00Z"
    events = [
        {
            "event_id": "photo_1",
            "event_type": "PHOTO",
            "timestamp": "2026-11-15T14:20:00Z",
        },
        {
            "event_id": "invoice_1",
            "event_type": "INVOICE",
            "timestamp": "2026-11-15T16:00:00Z",
        },
    ]

    result = aligner.align_and_evaluate(
        incident_time=incident_time,
        filing_time=filing_time,
        evidence_events=events,
    )

    assert result["timeline_risk_score"] == 0.0
    assert result["severity_tier"] == "LOW_RISK"
    assert result["decision"] == "VALID_TIMELINE"
    assert result["total_anomalies"] == 0


def test_pre_existing_damage_recycling_flag():
    aligner = ForensicEventTimelineAligner()
    incident_time = "2026-11-15T14:00:00Z"
    # Photo taken 35 days before incident occurred
    events = [
        {
            "event_id": "bumper_photo",
            "event_type": "PHOTO",
            "timestamp": "2026-10-10T12:00:00Z",
        }
    ]

    result = aligner.align_and_evaluate(
        incident_time=incident_time, evidence_events=events
    )

    assert result["timeline_risk_score"] >= 0.80
    assert result["decision"] == "REJECT_AND_INVESTIGATE"
    assert any("PRE_EXISTING_DAMAGE_PHOTO_RECYCLING" in f for f in result["flags"])


def test_causality_inversion_invoice_predates_incident():
    aligner = ForensicEventTimelineAligner()
    incident_time = "2026-11-15T14:00:00Z"
    events = [
        {
            "event_id": "repair_bill_99",
            "event_type": "INVOICE",
            "timestamp": "2026-11-14T09:00:00Z",
        }
    ]

    result = aligner.align_and_evaluate(
        incident_time=incident_time, evidence_events=events
    )

    assert result["timeline_risk_score"] >= 0.85
    assert any("CAUSALITY_INVERSION" in f for f in result["flags"])


def test_impossible_transit_velocity_flag():
    aligner = ForensicEventTimelineAligner(max_transit_speed_kmh=800.0)
    incident_time = "2026-11-15T14:00:00Z"
    # NYC to Miami (~1750 km) within 20 minutes (~5250 km/h)
    events = [
        {
            "event_id": "doc_nyc",
            "event_type": "PHOTO",
            "timestamp": "2026-11-15T15:00:00Z",
            "gps": (40.7128, -74.0060),
        },
        {
            "event_id": "doc_miami",
            "event_type": "PHOTO",
            "timestamp": "2026-11-15T15:20:00Z",
            "gps": (25.7617, -80.1918),
        },
    ]

    result = aligner.align_and_evaluate(
        incident_time=incident_time, evidence_events=events
    )

    assert any("IMPOSSIBLE_TRANSIT_VELOCITY" in f for f in result["flags"])
    assert result["timeline_risk_score"] >= 0.85


def test_haversine_great_circle_distance():
    aligner = ForensicEventTimelineAligner()
    # NYC to London distance is approx 5570 km
    dist = aligner.calculate_haversine_distance(40.7128, -74.0060, 51.5074, -0.1278)
    assert 5500 < dist < 5650

    # Same location distance is 0.0
    zero_dist = aligner.calculate_haversine_distance(12.0, 77.0, 12.0, 77.0)
    assert zero_dist == 0.0


def test_post_filing_evidence_fabrication():
    aligner = ForensicEventTimelineAligner()
    incident_time = "2026-11-15T14:00:00Z"
    filing_time = "2026-11-15T15:00:00Z"
    events = [
        {
            "event_id": "late_photo",
            "event_type": "PHOTO",
            "timestamp": "2026-11-16T12:00:00Z",  # 21 hours after claim filed
        }
    ]

    result = aligner.align_and_evaluate(
        incident_time=incident_time,
        filing_time=filing_time,
        evidence_events=events,
    )

    assert any("POST_FILING_EVIDENCE_FABRICATION" in f for f in result["flags"])
