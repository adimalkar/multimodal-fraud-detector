import math
import time
from typing import Any


class MultimodalRiskScorer:
    """
    Core scoring engine for the Multimodal Fraud Detection system.
    Aggregates signals from text (NLP), image/video, and metadata to
    compute a unified risk probability score using a weighted heuristic approach.
    """

    def __init__(
        self,
        text_weight: float = 0.4,
        visual_weight: float = 0.4,
        metadata_weight: float = 0.2,
    ):
        self.weights = {
            "text": text_weight,
            "visual": visual_weight,
            "metadata": metadata_weight,
        }

        # Ensure weights normalize to 1.0
        total = sum(self.weights.values())
        self.weights = {k: v / total for k, v in self.weights.items()}

    def calculate_risk(
        self,
        text_score: float,
        visual_score: float,
        metadata_flags: int,
        synergy_boost_enabled: bool = True,
    ) -> dict[str, Any]:
        """
        Calculate the aggregate fraud risk score with cross-modality compounding verification.

        Args:
            text_score (float): Probability of fraud based on text analysis (0.0 to 1.0)
            visual_score (float): Probability of fraud based on visual/deepfake analysis (0.0 to 1.0)
            metadata_flags (int): Number of suspicious metadata flags (e.g., mismatched geolocation)
            synergy_boost_enabled (bool): Whether to apply cross-modal compounding multiplier when multiple modalities alert

        Returns:
            Dict: Comprehensive risk assessment containing the final score, severity tier, and policy actions
        """
        # Cap metadata impact at 1.0 (assuming 5 flags is max severity)
        normalized_metadata = min(metadata_flags / 5.0, 1.0)

        base_score = (
            (text_score * self.weights["text"])
            + (visual_score * self.weights["visual"])
            + (normalized_metadata * self.weights["metadata"])
        )

        # Apply compounding synergy if multiple modalities independently detect high risk (> 0.65)
        synergy_applied = False
        if synergy_boost_enabled and (text_score >= 0.65 and visual_score >= 0.65):
            synergy_applied = True
            base_score = min(1.0, base_score * 1.15)

        final_score = min(1.0, max(0.0, base_score))
        tier = self._determine_tier(final_score)

        # Generate explainable factor breakdown
        risk_factors = []
        if text_score >= 0.5:
            risk_factors.append(
                f"Elevated NLP fraud pattern ({round(text_score * 100, 1)}%)"
            )
        if visual_score >= 0.5:
            risk_factors.append(
                f"Suspicious visual/deepfake artifacts detected ({round(visual_score * 100, 1)}%)"
            )
        if metadata_flags > 0:
            risk_factors.append(f"Metadata anomalies flagged ({metadata_flags} flags)")
        if synergy_applied:
            risk_factors.append(
                "Cross-modality compounding synergy multiplier applied (+15%)"
            )

        return {
            "risk_score": round(final_score, 4),
            "severity_tier": tier,
            "recommended_action": self._determine_action(tier),
            "cross_modal_synergy_applied": synergy_applied,
            "risk_factors": risk_factors,
            "breakdown": {
                "text_contribution": round(text_score * self.weights["text"], 4),
                "visual_contribution": round(visual_score * self.weights["visual"], 4),
                "metadata_contribution": round(
                    normalized_metadata * self.weights["metadata"], 4
                ),
            },
        }

    def _determine_tier(self, score: float) -> str:
        if score >= 0.80:
            return "CRITICAL_FRAUD"
        elif score >= 0.60:
            return "HIGH_RISK"
        elif score >= 0.35:
            return "SUSPICIOUS"
        return "LOW_RISK"

    def _determine_action(self, tier: str) -> str:
        actions = {
            "CRITICAL_FRAUD": "BLOCK_TRANSACTION_AND_ALERT_SECURITY",
            "HIGH_RISK": "ESCALATE_TO_SENIOR_ANALYST_QUEUE",
            "SUSPICIOUS": "REQUIRE_STEP_UP_MFA_AUTHENTICATION",
            "LOW_RISK": "APPROVE_AUTOMATICALLY",
        }
        return actions.get(tier, "MANUAL_REVIEW")

    def calculate_confidence_interval(
        self, samples: list[float], confidence: float = 0.95
    ) -> tuple[float, float]:
        """
        Calculate the standard error and confidence interval for a list of risk scores.
        Defaults to 95% confidence using normal approximation.
        """
        if not samples:
            return (0.0, 0.0)
        n = len(samples)
        mean = sum(samples) / n
        if n < 2:
            return (round(mean, 4), round(mean, 4))

        variance = sum((x - mean) ** 2 for x in samples) / (n - 1)
        std_dev = math.sqrt(variance)
        std_error = std_dev / math.sqrt(n)

        # Critical value z for common confidence levels
        z_multiplier = 1.96 if confidence >= 0.95 else 1.645
        margin = z_multiplier * std_error
        lower = max(0.0, round(mean - margin, 4))
        upper = min(1.0, round(mean + margin, 4))
        return (lower, upper)

    def evaluate_batch(
        self,
        records: list[dict[str, Any]],
        synergy_boost_enabled: bool = True,
        z_score_outlier_threshold: float = 2.0,
    ) -> dict[str, Any]:
        """
        Process a batch of multimodal transaction records, computing individual risk scores,
        aggregate cohort statistics, tier distributions, and identifying statistical outliers.
        """
        if not records:
            return {
                "total_records": 0,
                "mean_risk": 0.0,
                "std_dev": 0.0,
                "confidence_interval_95": [0.0, 0.0],
                "tier_distribution": {
                    "CRITICAL_FRAUD": 0,
                    "HIGH_RISK": 0,
                    "SUSPICIOUS": 0,
                    "LOW_RISK": 0,
                },
                "outlier_count": 0,
                "outliers": [],
                "scored_records": [],
            }

        scored: list[dict[str, Any]] = []
        raw_scores: list[float] = []

        for idx, rec in enumerate(records):
            text_score = float(rec.get("text_score", 0.0))
            visual_score = float(rec.get("visual_score", 0.0))
            metadata_flags = int(rec.get("metadata_flags", 0))
            record_id = rec.get("id", f"record_{idx}")

            assessment = self.calculate_risk(
                text_score=text_score,
                visual_score=visual_score,
                metadata_flags=metadata_flags,
                synergy_boost_enabled=synergy_boost_enabled,
            )
            assessment["record_id"] = record_id
            scored.append(assessment)
            raw_scores.append(assessment["risk_score"])

        n = len(raw_scores)
        mean_risk = sum(raw_scores) / n
        variance = (
            sum((s - mean_risk) ** 2 for s in raw_scores) / (n - 1) if n > 1 else 0.0
        )
        std_dev = math.sqrt(variance)

        # Identify outliers (scores deviating significantly from cohort mean)
        outliers: list[dict[str, Any]] = []
        for item in scored:
            score = item["risk_score"]
            z_score = ((score - mean_risk) / std_dev) if std_dev > 0 else 0.0
            if abs(z_score) >= z_score_outlier_threshold:
                outliers.append(
                    {
                        "record_id": item["record_id"],
                        "risk_score": score,
                        "z_score": round(z_score, 2),
                        "severity_tier": item["severity_tier"],
                    }
                )

        # Tier breakdown
        tiers: dict[str, int] = {
            "CRITICAL_FRAUD": 0,
            "HIGH_RISK": 0,
            "SUSPICIOUS": 0,
            "LOW_RISK": 0,
        }
        for item in scored:
            tier = item["severity_tier"]
            tiers[tier] = tiers.get(tier, 0) + 1

        ci = self.calculate_confidence_interval(raw_scores, confidence=0.95)

        return {
            "total_records": n,
            "mean_risk": round(mean_risk, 4),
            "std_dev": round(std_dev, 4),
            "confidence_interval_95": [ci[0], ci[1]],
            "tier_distribution": tiers,
            "outlier_count": len(outliers),
            "outliers": outliers,
            "scored_records": scored,
        }


class TransactionVelocityTracker:
    """
    Tracks and penalizes high-frequency transactional bursts across entities (user/IP/device).
    Applies sliding-window time-decayed velocity multipliers to base multimodal risk scores.
    """

    def __init__(
        self,
        window_seconds: float = 300.0,
        burst_threshold: int = 3,
        max_multiplier: float = 1.6,
    ):
        self.window_seconds = window_seconds
        self.burst_threshold = burst_threshold
        self.max_multiplier = max_multiplier
        # entity_id -> list of timestamps
        self.history: dict[str, list[float]] = {}

    def record_event(
        self, entity_id: str, timestamp: float | None = None
    ) -> dict[str, Any]:
        """
        Records a transaction event for an entity, evicts stale timestamps,
        and computes the instantaneous velocity multiplier.
        """
        now = timestamp if timestamp is not None else time.time()
        cutoff = now - self.window_seconds

        if entity_id not in self.history:
            self.history[entity_id] = []

        # Evict timestamps outside the window
        valid_ts = [t for t in self.history[entity_id] if t >= cutoff]
        valid_ts.append(now)
        self.history[entity_id] = valid_ts

        window_count = len(valid_ts)
        rate_per_min = round((window_count / (self.window_seconds / 60.0)), 2)

        # Multiplier scales progressively once burst threshold is reached
        if window_count > self.burst_threshold:
            excess = window_count - self.burst_threshold
            scale = min(1.0, excess / 5.0)
            multiplier = 1.0 + scale * (self.max_multiplier - 1.0)
        else:
            multiplier = 1.0

        burst_flagged = window_count >= self.burst_threshold

        return {
            "entity_id": entity_id,
            "window_count": window_count,
            "rate_per_minute": rate_per_min,
            "velocity_multiplier": round(multiplier, 3),
            "burst_flagged": burst_flagged,
        }

    def compute_adjusted_risk(
        self,
        base_risk_score: float,
        entity_id: str,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """
        Combines base multimodal risk with transaction velocity multiplier.
        """
        v_data = self.record_event(entity_id, timestamp=timestamp)
        adjusted_score = min(
            1.0, max(0.0, base_risk_score * v_data["velocity_multiplier"])
        )

        return {
            "base_risk_score": round(base_risk_score, 4),
            "adjusted_risk_score": round(adjusted_score, 4),
            "velocity_multiplier": v_data["velocity_multiplier"],
            "window_count": v_data["window_count"],
            "rate_per_minute": v_data["rate_per_minute"],
            "burst_flagged": v_data["burst_flagged"],
        }
