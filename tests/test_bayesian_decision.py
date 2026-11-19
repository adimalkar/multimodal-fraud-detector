from backend.risk_scorer import BayesianCostSensitiveDecisionEngine


def test_bayesian_decision_approve_microtransaction():
    engine = BayesianCostSensitiveDecisionEngine()
    res = engine.evaluate_transaction(
        fraud_probability=0.01,
        transaction_amount=15.0,
    )
    assert res["optimal_action"] == "APPROVE"
    assert res["fraud_probability"] == 0.01
    assert res["transaction_amount"] == 15.0
    assert res["minimized_expected_loss"] == res["expected_losses"]["APPROVE"]
    assert "Approved: low estimated fraud probability" in res["decision_rationale"]


def test_bayesian_decision_step_up_challenge():
    engine = BayesianCostSensitiveDecisionEngine()
    res = engine.evaluate_transaction(
        fraud_probability=0.15,
        transaction_amount=100.0,
    )
    assert res["optimal_action"] == "STEP_UP_CHALLENGE"
    assert (
        res["expected_losses"]["STEP_UP_CHALLENGE"] < res["expected_losses"]["APPROVE"]
    )
    assert (
        res["expected_losses"]["STEP_UP_CHALLENGE"]
        < res["expected_losses"]["BLOCK_TRANSACTION"]
    )
    assert "Step-Up Challenge required" in res["decision_rationale"]


def test_bayesian_decision_manual_review_high_ticket():
    engine = BayesianCostSensitiveDecisionEngine()
    # High value transaction ($800) with 35% suspicion justifies $8 manual review
    res = engine.evaluate_transaction(
        fraud_probability=0.35,
        transaction_amount=800.0,
        review_operational_cost=8.0,
    )
    assert res["optimal_action"] == "MANUAL_REVIEW"
    assert res["expected_losses"]["MANUAL_REVIEW"] < res["expected_losses"]["APPROVE"]
    assert (
        res["expected_losses"]["MANUAL_REVIEW"]
        < res["expected_losses"]["BLOCK_TRANSACTION"]
    )
    assert "Escalated to Manual Analyst Review" in res["decision_rationale"]


def test_bayesian_decision_block_acute_fraud():
    engine = BayesianCostSensitiveDecisionEngine()
    # High fraud certainty (99%) on significant amount ($1500)
    res = engine.evaluate_transaction(
        fraud_probability=0.99,
        transaction_amount=1500.0,
    )
    assert res["optimal_action"] == "BLOCK_TRANSACTION"
    assert res["minimized_expected_loss"] == res["expected_losses"]["BLOCK_TRANSACTION"]
    assert "Blocked: acute fraud probability" in res["decision_rationale"]


def test_bayesian_policy_presets_behavior():
    # In AGGRESSIVE_GROWTH mode, customer churn penalty is high (95% churn on block)
    engine_growth = BayesianCostSensitiveDecisionEngine(policy_mode="AGGRESSIVE_GROWTH")
    # In CONSERVATIVE mode, tolerance for fraud is lower
    engine_conservative = BayesianCostSensitiveDecisionEngine(
        policy_mode="CONSERVATIVE"
    )

    p = 0.40
    amt = 120.0
    res_growth = engine_growth.evaluate_transaction(p, amt)
    res_conservative = engine_conservative.evaluate_transaction(p, amt)

    assert res_growth["policy_mode"] == "AGGRESSIVE_GROWTH"
    assert res_conservative["policy_mode"] == "CONSERVATIVE"
    # Conservative policy has lower block threshold loss due to lower churn weight
    assert (
        res_conservative["expected_losses"]["BLOCK_TRANSACTION"]
        < res_growth["expected_losses"]["BLOCK_TRANSACTION"]
    )


def test_bayesian_decision_boundary_and_savings_calculation():
    engine = BayesianCostSensitiveDecisionEngine()
    # If p=0.45, naive 0.50 threshold chooses APPROVE ($56.25 expected loss),
    # but Bayesian optimal chooses STEP_UP_CHALLENGE ($10.00 expected loss)
    res = engine.evaluate_transaction(
        fraud_probability=0.45,
        transaction_amount=100.0,
    )
    assert res["optimal_action"] == "STEP_UP_CHALLENGE"
    assert res["naive_threshold_action"] == "APPROVE"
    assert res["expected_savings_vs_naive"] > 40.0


def test_bayesian_decision_edge_cases():
    engine = BayesianCostSensitiveDecisionEngine()
    # P=0.0 (absolutely certain legitimate)
    res_zero = engine.evaluate_transaction(0.0, 50.0)
    assert res_zero["optimal_action"] == "APPROVE"
    assert res_zero["minimized_expected_loss"] == 0.0

    # P=1.0 (absolutely certain fraud)
    res_one = engine.evaluate_transaction(1.0, 50.0)
    assert res_one["optimal_action"] == "BLOCK_TRANSACTION"
    assert res_one["expected_losses"]["BLOCK_TRANSACTION"] == 0.0
