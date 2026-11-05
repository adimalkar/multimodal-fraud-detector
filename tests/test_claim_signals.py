import pytest
from starlette.testclient import TestClient

from backend import app as app_module
from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


BASE_TS = 1_790_000_000.0


def test_every_engine_runs_on_a_single_request(client):
    response = client.post("/api/claims/signals", json={
        "events": [
            {"claimant_id": "c-1", "timestamp": BASE_TS, "lat": 53.35, "lon": -6.26,
             "device_fingerprint": "dev-a"},
            {"claimant_id": "c-1", "timestamp": BASE_TS + 60, "lat": 1.35, "lon": 103.82,
             "device_fingerprint": "dev-b"},
            {"claimant_id": "c-1", "timestamp": BASE_TS + 120, "lat": 1.35, "lon": 103.82},
        ],
        "entities": [
            {"entity_id": "c-1", "base_risk": 0.8, "attributes": {"bank": "IE-1"}},
            {"entity_id": "c-2", "base_risk": 0.1, "attributes": {"bank": "IE-1"}},
        ],
        "modality_scores": {"visual": 0.95, "text": 0.05, "metadata": 0.1},
        "prior_findings": [{"entity_id": "c-1", "risk_score": 0.9, "timestamp": BASE_TS - 14 * 86400}],
        "as_of": BASE_TS,
    })
    assert response.status_code == 200
    data = response.json()

    assert data["persisted"] is False
    assert "not a fraud decision" in data["notice"]
    claimant = data["velocity"][0]
    assert claimant["claimant_id"] == "c-1"
    assert claimant["peak_window_count"] == 3
    assert claimant["burst_flagged"] is True
    travel = data["travel"][0]
    assert travel["impossible_travel_detected"] is True
    assert any("IMPOSSIBLE" in flag for flag in travel["anomaly_flags"])
    assert data["network"]["rings"], "shared bank account should form a ring"
    linked = next(e for e in data["network"]["entities"] if e["entity_id"] == "c-2")
    assert linked["propagated_risk"] > linked["base_risk"]
    assert data["conflict"]["conflict_tier"] == "CRITICAL_MODAL_MASKING"
    assert data["history"][0]["decayed_risk_score"] < 0.9


def test_sections_without_input_are_null_rather_than_clean(client):
    """A skipped check must not look like a passed check."""
    response = client.post("/api/claims/signals", json={
        "modality_scores": {"visual": 0.2, "text": 0.25},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["velocity"] is None
    assert data["travel"] is None
    assert data["network"] is None
    assert data["history"] is None
    assert data["conflict"]["conflict_tier"] == "CONGRUENT"


def test_empty_request_is_rejected(client):
    response = client.post("/api/claims/signals", json={})
    assert response.status_code == 400


def test_events_are_evaluated_in_time_order(client):
    """Out-of-order input must not hide a travel anomaly."""
    response = client.post("/api/claims/signals", json={"events": [
        {"claimant_id": "c-1", "timestamp": BASE_TS + 60, "lat": 1.35, "lon": 103.82},
        {"claimant_id": "c-1", "timestamp": BASE_TS, "lat": 53.35, "lon": -6.26},
    ]})
    assert response.status_code == 200
    assert response.json()["travel"][0]["impossible_travel_detected"] is True


def test_claimants_do_not_share_velocity_or_travel_state(client):
    response = client.post("/api/claims/signals", json={"events": [
        {"claimant_id": "c-1", "timestamp": BASE_TS, "lat": 53.35, "lon": -6.26},
        {"claimant_id": "c-2", "timestamp": BASE_TS + 1, "lat": 1.35, "lon": 103.82},
    ]})
    data = response.json()
    assert all(item["peak_window_count"] == 1 for item in data["velocity"])
    assert all(not item["impossible_travel_detected"] for item in data["travel"])


def test_requests_do_not_leak_state_between_calls(client):
    payload = {"events": [{"claimant_id": "c-1", "timestamp": BASE_TS, "lat": 53.35, "lon": -6.26}]}
    client.post("/api/claims/signals", json=payload)
    second = client.post("/api/claims/signals", json=payload).json()
    assert second["velocity"][0]["peak_window_count"] == 1


@pytest.mark.parametrize("payload", [
    {"events": [{"claimant_id": "c", "timestamp": BASE_TS, "lat": 91, "lon": 0}]},
    {"events": [{"claimant_id": "c", "timestamp": BASE_TS, "lat": 0, "lon": 181}]},
    {"entities": [{"entity_id": "c", "base_risk": 1.5}]},
    {"modality_scores": {"visual": 2}},
    {"events": [{"claimant_id": "c", "timestamp": BASE_TS, "lat": 0, "lon": 0}] * 501},
    {"entities": [{"entity_id": f"c{i}"} for i in range(501)]},
])
def test_out_of_range_input_is_rejected(client, payload):
    assert client.post("/api/claims/signals", json=payload).status_code == 422


def test_durable_mode_requires_a_tenant(client, monkeypatch):
    monkeypatch.setattr(app_module, "DURABLE_JOBS_ENABLED", True)
    monkeypatch.setenv("ANALYSIS_TOKENS_JSON", '{"tenant-a": "' + "t" * 32 + '"}')
    payload = {"modality_scores": {"visual": 0.2, "text": 0.25}}
    assert client.post("/api/claims/signals", json=payload).status_code == 401
    authorized = client.post("/api/claims/signals", json=payload,
                             headers={"Authorization": "Bearer " + "t" * 32})
    assert authorized.status_code == 200
