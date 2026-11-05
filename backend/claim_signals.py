"""Stateless claim-level checks built on the scoring engines in risk_scorer.

Every request gets fresh engine instances and nothing is stored. A section is
None when the caller gave it no input, so a skipped check never reads as a
passed one. Scores are uncalibrated heuristics for human review.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    from backend.risk_scorer import (
        BehavioralRiskDecayEngine,
        DeviceGeoAnomalyDetector,
        EntityCollusionDetector,
        ModalConflictDetector,
        TransactionVelocityTracker,
    )
except ImportError:
    from risk_scorer import (
        BehavioralRiskDecayEngine,
        DeviceGeoAnomalyDetector,
        EntityCollusionDetector,
        ModalConflictDetector,
        TransactionVelocityTracker,
    )

MAX_SIGNAL_ROWS = 500
NOTICE = (
    "These are uncalibrated heuristic signals to help a reviewer prioritise, "
    "not a fraud decision."
)

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Score = Annotated[float, Field(ge=0.0, le=1.0)]
Timestamp = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class ClaimEvent(BaseModel):
    claimant_id: Identifier
    timestamp: Timestamp
    lat: Optional[Annotated[float, Field(ge=-90.0, le=90.0)]] = None
    lon: Optional[Annotated[float, Field(ge=-180.0, le=180.0)]] = None
    device_fingerprint: Optional[Annotated[str, Field(max_length=128)]] = None
    is_vpn_or_datacenter: bool = False


class ClaimEntity(BaseModel):
    entity_id: Identifier
    base_risk: Score = 0.0
    attributes: Dict[Identifier, Annotated[str, Field(max_length=256)]] = Field(
        default_factory=dict, max_length=20
    )


class PriorFinding(BaseModel):
    entity_id: Identifier
    risk_score: Score
    timestamp: Timestamp
    clean_events_since: Annotated[int, Field(ge=0, le=1000)] = 0


class ClaimSignalsRequest(BaseModel):
    events: List[ClaimEvent] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    entities: List[ClaimEntity] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    modality_scores: Dict[Identifier, Score] = Field(default_factory=dict, max_length=10)
    prior_findings: List[PriorFinding] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    as_of: Optional[Timestamp] = None

    def is_empty(self) -> bool:
        return not (self.events or self.entities or self.modality_scores or self.prior_findings)


def _velocity(events: List[ClaimEvent]) -> Optional[List[Dict[str, Any]]]:
    if not events:
        return None
    tracker = TransactionVelocityTracker()
    peaks: Dict[str, Dict[str, Any]] = {}
    for event in events:
        state = tracker.record_event(event.claimant_id, timestamp=event.timestamp)
        peak = peaks.setdefault(event.claimant_id, {
            "claimant_id": event.claimant_id, "events": 0, "peak_window_count": 0,
            "peak_rate_per_minute": 0.0, "velocity_multiplier": 1.0, "burst_flagged": False,
        })
        peak["events"] += 1
        peak["burst_flagged"] = peak["burst_flagged"] or state["burst_flagged"]
        if state["window_count"] > peak["peak_window_count"]:
            peak["peak_window_count"] = state["window_count"]
            peak["peak_rate_per_minute"] = state["rate_per_minute"]
            peak["velocity_multiplier"] = state["velocity_multiplier"]
    return sorted(peaks.values(), key=lambda item: -item["peak_window_count"])


def _travel(events: List[ClaimEvent]) -> Optional[List[Dict[str, Any]]]:
    located = [event for event in events if event.lat is not None and event.lon is not None]
    if not located:
        return None
    detector = DeviceGeoAnomalyDetector()
    worst: Dict[str, Dict[str, Any]] = {}
    flags: Dict[str, List[str]] = {}
    for event in located:
        result = detector.record_and_evaluate(
            event.claimant_id, event.lat, event.lon, timestamp=event.timestamp,
            device_fingerprint=event.device_fingerprint,
            is_vpn_or_datacenter=event.is_vpn_or_datacenter,
        )
        seen = flags.setdefault(event.claimant_id, [])
        seen.extend(flag for flag in result["anomaly_flags"] if flag not in seen)
        current = worst.get(event.claimant_id)
        if current is None or result["geo_risk_score"] > current["geo_risk_score"]:
            worst[event.claimant_id] = result
    return sorted(
        ({**result, "anomaly_flags": flags[claimant]} for claimant, result in worst.items()),
        key=lambda item: -item["geo_risk_score"],
    )


def _network(entities: List[ClaimEntity]) -> Optional[Dict[str, Any]]:
    if not entities:
        return None
    detector = EntityCollusionDetector()
    for entity in entities:
        detector.register_entity(entity.entity_id, entity.attributes, base_risk=entity.base_risk)
    return {
        "rings": detector.detect_collusion_rings(),
        "entities": sorted(
            (detector.compute_propagated_risk(entity_id) for entity_id in detector.entities),
            key=lambda item: -item["propagated_risk"],
        ),
    }


def _history(findings: List[PriorFinding], as_of: Optional[float]) -> Optional[List[Dict[str, Any]]]:
    if not findings:
        return None
    engine = BehavioralRiskDecayEngine()
    ordered = sorted(findings, key=lambda finding: finding.timestamp)
    for finding in ordered:
        engine.record_infraction(finding.entity_id, finding.risk_score, timestamp=finding.timestamp)
        engine.profiles[finding.entity_id]["clean_events_since"] = finding.clean_events_since
    now = as_of if as_of is not None else max(finding.timestamp for finding in ordered)
    return sorted(
        (engine.calculate_decayed_risk(entity_id, now) for entity_id in engine.profiles),
        key=lambda item: -item["decayed_risk_score"],
    )


def evaluate_claim_signals(request: ClaimSignalsRequest) -> Dict[str, Any]:
    events = sorted(request.events, key=lambda event: event.timestamp)
    return {
        "persisted": False,
        "notice": NOTICE,
        "velocity": _velocity(events),
        "travel": _travel(events),
        "network": _network(request.entities),
        "conflict": (
            ModalConflictDetector().evaluate_modalities(request.modality_scores)
            if request.modality_scores else None
        ),
        "history": _history(request.prior_findings, request.as_of),
    }
