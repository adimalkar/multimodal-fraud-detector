from backend.risk_scorer import BehavioralRiskDecayEngine


def test_unregistered_entity_decay():
    engine = BehavioralRiskDecayEngine()
    res = engine.calculate_decayed_risk("ghost_entity", current_timestamp=1000.0)
    assert res["entity_id"] == "ghost_entity"
    assert res["decayed_risk_score"] == 0.0
    assert res["days_elapsed"] == 0.0
    assert res["rehabilitation_complete"] is True


def test_immediate_risk_no_decay():
    engine = BehavioralRiskDecayEngine(
        default_half_life_days=14.0, residual_risk_floor=0.05
    )
    t0 = 1000.0
    engine.record_infraction("user_1", risk_score=0.80, timestamp=t0)

    res = engine.calculate_decayed_risk("user_1", current_timestamp=t0)
    assert res["original_peak_risk"] == 0.80
    assert res["decayed_risk_score"] == 0.80
    assert res["days_elapsed"] == 0.0
    assert res["rehabilitation_complete"] is False


def test_exponential_half_life_decay():
    hl_days = 10.0
    floor = 0.05
    engine = BehavioralRiskDecayEngine(
        default_half_life_days=hl_days, residual_risk_floor=floor
    )
    t0 = 0.0
    engine.record_infraction("user_2", risk_score=0.85, timestamp=t0)

    # Day 10 (exactly one half-life): (0.85 - 0.05) * 0.5 + 0.05 = 0.45
    t_day_10 = 10.0 * 86400.0
    res_10 = engine.calculate_decayed_risk("user_2", current_timestamp=t_day_10)
    assert abs(res_10["decayed_risk_score"] - 0.45) < 0.001
    assert res_10["days_elapsed"] == 10.0

    # Day 20 (two half-lives): 0.80 * 0.25 + 0.05 = 0.25
    t_day_20 = 20.0 * 86400.0
    res_20 = engine.calculate_decayed_risk("user_2", current_timestamp=t_day_20)
    assert abs(res_20["decayed_risk_score"] - 0.25) < 0.001


def test_clean_event_acceleration():
    engine = BehavioralRiskDecayEngine(
        default_half_life_days=10.0,
        residual_risk_floor=0.05,
        clean_event_discount_factor=0.85,
    )
    t0 = 0.0
    engine.record_infraction("user_clean", risk_score=0.85, timestamp=t0)

    # 2 clean events recorded
    engine.record_clean_event("user_clean", timestamp=100.0)
    engine.record_clean_event("user_clean", timestamp=200.0)

    # At day 10 without discount: 0.45. With 2 clean events (0.85^2 = 0.7225):
    # decayed = 0.05 + 0.80 * 0.5 * 0.7225 = 0.05 + 0.289 = 0.339
    t_day_10 = 10.0 * 86400.0
    res = engine.calculate_decayed_risk("user_clean", current_timestamp=t_day_10)
    assert res["clean_events_count"] == 2
    assert res["clean_events_discount_applied"] is True
    assert abs(res["decayed_risk_score"] - 0.339) < 0.002


def test_residual_risk_floor_enforcement():
    floor = 0.05
    engine = BehavioralRiskDecayEngine(
        default_half_life_days=7.0, residual_risk_floor=floor
    )
    engine.record_infraction("user_old", risk_score=0.90, timestamp=0.0)

    # After 1 year (365 days)
    t_1year = 365.0 * 86400.0
    res = engine.calculate_decayed_risk("user_old", current_timestamp=t_1year)
    assert res["decayed_risk_score"] == floor
    assert res["rehabilitation_complete"] is True


def test_subsequent_infraction_updates_peak():
    engine = BehavioralRiskDecayEngine(
        default_half_life_days=10.0, residual_risk_floor=0.05
    )
    engine.record_infraction("user_repeat", risk_score=0.40, timestamp=0.0)

    # Severe second infraction at day 5
    t_day_5 = 5.0 * 86400.0
    engine.record_infraction("user_repeat", risk_score=0.90, timestamp=t_day_5)

    res = engine.calculate_decayed_risk("user_repeat", current_timestamp=t_day_5)
    assert res["original_peak_risk"] == 0.90
    assert res["decayed_risk_score"] == 0.90
    assert res["clean_events_count"] == 0
