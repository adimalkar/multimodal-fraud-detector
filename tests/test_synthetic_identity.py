from backend.risk_scorer import SyntheticIdentityScorer


def test_legitimate_identity_passes():
    scorer = SyntheticIdentityScorer()
    result = scorer.evaluate_identity(
        name="Aditya Malkar",
        email="aditya.malkar@gmail.com",
        phone_carrier="MOBILE",
        account_age_days=180,
    )

    assert result["synthetic_risk_score"] < 0.20
    assert result["risk_tier"] == "LOW_RISK"
    assert result["decision"] == "APPROVE"
    assert len(result["flags"]) == 0
    assert result["component_risks"]["domain_risk"] == 0.0


def test_disposable_email_domain_triggers_critical_fraud():
    scorer = SyntheticIdentityScorer()
    result = scorer.evaluate_identity(
        name="Test User",
        email="anonymous123@mailinator.com",
        phone_carrier="MOBILE",
        account_age_days=10,
    )

    assert result["synthetic_risk_score"] >= 0.85
    assert result["risk_tier"] == "CRITICAL_SYNTHETIC_FRAUD"
    assert result["decision"] == "REJECT"
    assert any("DISPOSABLE_BURNER_EMAIL_DOMAIN" in f for f in result["flags"])
    assert result["identity_metadata"]["is_disposable_domain"] is True


def test_high_entropy_handle_and_name_mismatch():
    scorer = SyntheticIdentityScorer()
    result = scorer.evaluate_identity(
        name="Robert Evans",
        email="z7q9k2x4v1b@outlook.com",
        phone_carrier="MOBILE",
        account_age_days=50,
    )

    assert result["synthetic_risk_score"] > 0.30
    assert any("HIGH_ENTROPY_RANDOM_EMAIL_HANDLE" in f for f in result["flags"])
    assert any("NAME_EMAIL_IDENTITY_MISMATCH" in f for f in result["flags"])
    assert result["component_risks"]["handle_randomness_risk"] >= 0.60


def test_voip_carrier_and_fresh_account_flags():
    scorer = SyntheticIdentityScorer()
    result = scorer.evaluate_identity(
        name="Alex Smith",
        email="alex.smith@gmail.com",
        phone_carrier="VOIP",
        account_age_days=1,
    )

    assert any("HIGH_RISK_TELEPHONY_CARRIER (VOIP)" in f for f in result["flags"])
    assert any("NEWLY_CREATED_ACCOUNT_UNDER_48H" in f for f in result["flags"])
    assert result["component_risks"]["carrier_risk"] == 0.75
    assert result["component_risks"]["tenure_risk"] == 0.70


def test_shannon_entropy_properties():
    scorer = SyntheticIdentityScorer()
    assert scorer.calculate_shannon_entropy("") == 0.0
    assert scorer.calculate_shannon_entropy("aaaaaaa") == 0.0
    # Two symbols equally distributed: -2 * 0.5 * log2(0.5) = 1.0 bit
    assert abs(scorer.calculate_shannon_entropy("abab") - 1.0) < 1e-4


def test_name_handle_alignment_initials():
    scorer = SyntheticIdentityScorer()
    # First initial + last name
    score = scorer.compute_name_handle_alignment("Aditya Malkar", "amalkar")
    assert score == 0.85

    # Reverse
    score_rev = scorer.compute_name_handle_alignment("Aditya Malkar", "malkara")
    assert score_rev == 0.80

    # Total mismatch
    mismatch = scorer.compute_name_handle_alignment("Bruce Wayne", "clarkkent")
    assert mismatch == 0.0
