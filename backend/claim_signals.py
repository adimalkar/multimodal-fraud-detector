"""Stateless claim-level checks built on the scoring engines in risk_scorer.

Every request gets fresh engine instances and nothing is stored. A section is
None when the caller gave it no input, so a skipped check never reads as a
passed one. Scores are uncalibrated heuristics for human review.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from backend.risk_scorer import (
        BayesianCostSensitiveDecisionEngine,
        BehavioralRiskDecayEngine,
        DeviceGeoAnomalyDetector,
        EntityCollusionDetector,
        ForensicEventTimelineAligner,
        ModalConflictDetector,
        PerceptualHashCollisionDetector,
        RiskPopulationDriftMonitor,
        SyntheticIdentityScorer,
        TransactionVelocityTracker,
    )
except ImportError:
    from risk_scorer import (
        BayesianCostSensitiveDecisionEngine,
        BehavioralRiskDecayEngine,
        DeviceGeoAnomalyDetector,
        EntityCollusionDetector,
        ForensicEventTimelineAligner,
        ModalConflictDetector,
        PerceptualHashCollisionDetector,
        RiskPopulationDriftMonitor,
        SyntheticIdentityScorer,
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


class IdentityProfile(BaseModel):
    entity_id: Optional[Identifier] = None
    name: Annotated[str, Field(min_length=1, max_length=128)]
    email: Annotated[str, Field(min_length=3, max_length=256)]
    phone_carrier: Annotated[str, Field(min_length=1, max_length=32)] = "MOBILE"
    account_age_days: Optional[Annotated[int, Field(ge=0, le=36500)]] = None

    @field_validator("email")
    @classmethod
    def _validate_email_format(cls, value: str) -> str:
        cleaned = value.strip()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("email must contain non-empty local and domain parts separated by '@'")
        return cleaned


class TimelineEvidenceEvent(BaseModel):
    event_id: Identifier
    event_type: Annotated[str, Field(min_length=1, max_length=32)]
    timestamp: Timestamp
    lat: Optional[Annotated[float, Field(ge=-90.0, le=90.0)]] = None
    lon: Optional[Annotated[float, Field(ge=-180.0, le=180.0)]] = None

    @model_validator(mode="after")
    def _validate_coordinates_pair(self) -> TimelineEvidenceEvent:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must both be provided together or both omitted")
        return self


class TimelineInput(BaseModel):
    incident_time: Timestamp
    filing_time: Optional[Timestamp] = None
    evidence_events: List[TimelineEvidenceEvent] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)


class DocumentHashItem(BaseModel):
    entity_id: Identifier
    image_id: Identifier
    phash: Annotated[str, Field(min_length=1, max_length=18)]
    timestamp: Optional[Timestamp] = None

    @field_validator("phash")
    @classmethod
    def _validate_hex_phash(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,16}", cleaned):
            raise ValueError("phash must be a 1-to-16 digit hexadecimal string")
        return cleaned


class CostDecisionInput(BaseModel):
    fraud_probability: Score
    transaction_amount: Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
    customer_lifetime_value: Optional[Annotated[float, Field(ge=0.0, allow_inf_nan=False)]] = None
    chargeback_fee: Optional[Annotated[float, Field(ge=0.0, allow_inf_nan=False)]] = None
    review_operational_cost: Optional[Annotated[float, Field(ge=0.0, allow_inf_nan=False)]] = None
    policy_mode: Annotated[
        str, Field(pattern="^(BALANCED|AGGRESSIVE_GROWTH|STRICT_FRAUD_CONTROL)$")
    ] = "BALANCED"


class PopulationDriftInput(BaseModel):
    reference_scores: List[Score] = Field(min_length=2, max_length=MAX_SIGNAL_ROWS)
    current_scores: List[Score] = Field(min_length=2, max_length=MAX_SIGNAL_ROWS)
    num_bins: Annotated[int, Field(ge=2, le=20)] = 10


class ClaimSignalsRequest(BaseModel):
    events: List[ClaimEvent] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    entities: List[ClaimEntity] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    modality_scores: Dict[Identifier, Score] = Field(default_factory=dict, max_length=10)
    prior_findings: List[PriorFinding] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    identities: List[IdentityProfile] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    timeline: Optional[TimelineInput] = None
    hashes: List[DocumentHashItem] = Field(default_factory=list, max_length=MAX_SIGNAL_ROWS)
    decision: Optional[CostDecisionInput] = None
    drift: Optional[PopulationDriftInput] = None
    as_of: Optional[Timestamp] = None

    def is_empty(self) -> bool:
        return not (
            self.events
            or self.entities
            or self.modality_scores
            or self.prior_findings
            or self.identities
            or self.timeline
            or self.hashes
            or self.decision
            or self.drift
        )


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


def _identities(identities: List[IdentityProfile]) -> Optional[List[Dict[str, Any]]]:
    if not identities:
        return None
    scorer = SyntheticIdentityScorer()
    results: List[Dict[str, Any]] = []
    for profile in identities:
        evaluation = scorer.evaluate_identity(
            name=profile.name,
            email=profile.email,
            phone_carrier=profile.phone_carrier,
            account_age_days=profile.account_age_days,
        )
        if profile.entity_id is not None:
            evaluation["entity_id"] = profile.entity_id
        results.append(evaluation)
    return sorted(results, key=lambda item: -item["synthetic_risk_score"])


def _timeline(timeline: Optional[TimelineInput]) -> Optional[Dict[str, Any]]:
    if timeline is None:
        return None
    aligner = ForensicEventTimelineAligner()
    evidence = [
        {
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "timestamp": ev.timestamp,
            **({"gps": (ev.lat, ev.lon)} if ev.lat is not None and ev.lon is not None else {}),
        }
        for ev in timeline.evidence_events
    ]
    return aligner.align_and_evaluate(
        incident_time=timeline.incident_time,
        filing_time=timeline.filing_time,
        evidence_events=evidence,
    )


def _hashes(hashes: List[DocumentHashItem]) -> Optional[List[Dict[str, Any]]]:
    if not hashes:
        return None
    detector = PerceptualHashCollisionDetector()
    ordered = sorted(
        hashes,
        key=lambda item: (item.timestamp is None, item.timestamp if item.timestamp is not None else 0.0),
    )
    scans = [
        detector.register_and_scan(
            entity_id=item.entity_id,
            image_id=item.image_id,
            phash=item.phash,
            timestamp=item.timestamp,
        )
        for item in ordered
    ]
    return sorted(scans, key=lambda item: (-item["duplicate_risk_score"], -item["collision_count"]))


def _decision(decision: Optional[CostDecisionInput]) -> Optional[Dict[str, Any]]:
    if decision is None:
        return None
    engine = BayesianCostSensitiveDecisionEngine(policy_mode=decision.policy_mode)
    return engine.evaluate_transaction(
        fraud_probability=decision.fraud_probability,
        transaction_amount=decision.transaction_amount,
        customer_lifetime_value=decision.customer_lifetime_value,
        chargeback_fee=decision.chargeback_fee,
        review_operational_cost=decision.review_operational_cost,
        policy_override=decision.policy_mode,
    )


def _drift(drift: Optional[PopulationDriftInput]) -> Optional[Dict[str, Any]]:
    if drift is None:
        return None
    monitor = RiskPopulationDriftMonitor(default_bins=drift.num_bins)
    return monitor.evaluate_drift(
        reference_scores=drift.reference_scores,
        current_scores=drift.current_scores,
        num_bins=drift.num_bins,
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
        "identities": _identities(request.identities),
        "timeline": _timeline(request.timeline),
        "hashes": _hashes(request.hashes),
        "decision": _decision(request.decision),
        "drift": _drift(request.drift),
    }
