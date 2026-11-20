import bisect
import math
import re
import time
from typing import Any, ClassVar


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


class EntityCollusionDetector:
    """
    Detects cross-entity collusion syndicates and calculates graph risk propagation
    over shared device, IP, and account attributes.
    """

    def __init__(
        self,
        damping_factor: float = 0.35,
        min_syndicate_size: int = 2,
        high_risk_threshold: float = 0.65,
    ):
        self.damping_factor = damping_factor
        self.min_syndicate_size = min_syndicate_size
        self.high_risk_threshold = high_risk_threshold
        # entity_id -> {"base_risk": float, "attributes": dict[str, str]}
        self.entities: dict[str, dict[str, Any]] = {}
        # attribute_key:value -> set of entity_ids
        self.attribute_index: dict[str, set[str]] = {}

    def register_entity(
        self,
        entity_id: str,
        attributes: dict[str, Any],
        base_risk: float = 0.0,
    ) -> None:
        """
        Registers an entity with its associated identifiers (e.g. ip, device_hash, ssn_hash, bank_id).
        """
        self.entities[entity_id] = {
            "base_risk": min(1.0, max(0.0, float(base_risk))),
            "attributes": {
                k: str(v)
                for k, v in attributes.items()
                if v is not None and str(v).strip()
            },
        }
        for k, v in self.entities[entity_id]["attributes"].items():
            attr_key = f"{k}:{v}"
            if attr_key not in self.attribute_index:
                self.attribute_index[attr_key] = set()
            self.attribute_index[attr_key].add(entity_id)

    def get_neighbors(self, entity_id: str) -> tuple[set[str], list[str]]:
        """
        Finds all entities connected through at least one shared attribute.
        Returns: (set of neighbor entity_ids, list of shared attribute keys).
        """
        if entity_id not in self.entities:
            return set(), []

        neighbors: set[str] = set()
        shared_attrs: set[str] = set()
        for k, v in self.entities[entity_id]["attributes"].items():
            attr_key = f"{k}:{v}"
            connected = self.attribute_index.get(attr_key, set())
            for neighbor in connected:
                if neighbor != entity_id:
                    neighbors.add(neighbor)
                    shared_attrs.add(attr_key)

        return neighbors, sorted(shared_attrs)

    def detect_collusion_rings(self) -> list[dict[str, Any]]:
        """
        Identifies connected components (collusion clusters) in the entity graph.
        Computes ring density, shared attributes, and syndication risk tier.
        """
        visited: set[str] = set()
        rings: list[dict[str, Any]] = []

        for entity_id in self.entities:
            if entity_id in visited:
                continue

            # BFS to find connected component
            component: list[str] = []
            queue = [entity_id]
            visited.add(entity_id)

            while queue:
                curr = queue.pop(0)
                component.append(curr)
                neighbors, _ = self.get_neighbors(curr)
                for n in neighbors:
                    if n not in visited:
                        visited.add(n)
                        queue.append(n)

            if len(component) >= self.min_syndicate_size:
                ring_risks = [self.entities[e]["base_risk"] for e in component]
                max_risk = max(ring_risks) if ring_risks else 0.0
                mean_risk = sum(ring_risks) / len(ring_risks) if ring_risks else 0.0

                # Collect all shared attributes inside the component
                all_shared_attrs: set[str] = set()
                for e in component:
                    for k, v in self.entities[e]["attributes"].items():
                        attr_key = f"{k}:{v}"
                        if len(self.attribute_index.get(attr_key, set())) > 1:
                            all_shared_attrs.add(attr_key)

                is_syndicate = (
                    max_risk >= self.high_risk_threshold
                    or len(all_shared_attrs) >= 2
                    or len(component) >= 3
                )

                # Synergy penalty scales with cluster size and max risk
                penalty = 0.0
                if is_syndicate:
                    size_factor = min(0.15, (len(component) - 1) * 0.05)
                    risk_factor = max_risk * 0.15
                    penalty = round(size_factor + risk_factor, 3)

                ring_id = f"ring_{len(rings) + 1}"
                rings.append(
                    {
                        "ring_id": ring_id,
                        "size": len(component),
                        "entities": sorted(component),
                        "shared_attributes": sorted(all_shared_attrs),
                        "mean_base_risk": round(mean_risk, 4),
                        "max_base_risk": round(max_risk, 4),
                        "is_syndicate": is_syndicate,
                        "syndicate_risk_penalty": penalty,
                    }
                )

        return rings

    def compute_propagated_risk(self, entity_id: str) -> dict[str, Any]:
        """
        Computes the network-propagated fraud risk for an entity based on
        its base risk score and the maximum risk of its connected cluster neighbors.
        """
        if entity_id not in self.entities:
            return {
                "entity_id": entity_id,
                "base_risk": 0.0,
                "propagated_risk": 0.0,
                "network_risk_boost": 0.0,
                "neighbor_count": 0,
                "shared_attributes": [],
                "syndicate_flagged": False,
            }

        base_risk = self.entities[entity_id]["base_risk"]
        neighbors, shared_attrs = self.get_neighbors(entity_id)

        if not neighbors:
            return {
                "entity_id": entity_id,
                "base_risk": round(base_risk, 4),
                "propagated_risk": round(base_risk, 4),
                "network_risk_boost": 0.0,
                "neighbor_count": 0,
                "shared_attributes": [],
                "syndicate_flagged": False,
            }

        neighbor_risks = [self.entities[n]["base_risk"] for n in neighbors]
        max_neighbor_risk = max(neighbor_risks) if neighbor_risks else 0.0

        # Network risk boost: scales with the most severe neighbor and the number of shared attributes
        attr_multiplier = min(1.5, 1.0 + (len(shared_attrs) - 1) * 0.15)
        raw_boost = max_neighbor_risk * self.damping_factor * attr_multiplier
        propagated_risk = min(1.0, max(base_risk, base_risk + raw_boost))

        syndicate_flagged = (
            max_neighbor_risk >= self.high_risk_threshold
            or len(neighbors) >= 2
            or len(shared_attrs) >= 2
        )

        return {
            "entity_id": entity_id,
            "base_risk": round(base_risk, 4),
            "propagated_risk": round(propagated_risk, 4),
            "network_risk_boost": round(propagated_risk - base_risk, 4),
            "neighbor_count": len(neighbors),
            "shared_attributes": shared_attrs,
            "syndicate_flagged": syndicate_flagged,
        }


class DeviceGeoAnomalyDetector:
    """
    Detects impossible travel velocity, rapid geolocation shifts,
    and device fingerprint churn across sequential user events.
    """

    EARTH_RADIUS_KM = 6371.0

    def __init__(
        self,
        max_plausible_speed_kmh: float = 900.0,
        device_churn_window_seconds: float = 86400.0,
        max_allowed_devices_in_window: int = 3,
    ):
        self.max_plausible_speed_kmh = max_plausible_speed_kmh
        self.device_churn_window_seconds = device_churn_window_seconds
        self.max_allowed_devices_in_window = max_allowed_devices_in_window
        # user_id -> list of recent location records: {"lat": float, "lon": float, "timestamp": float}
        self.location_history: dict[str, list[dict[str, Any]]] = {}
        # user_id -> list of (device_fp, timestamp)
        self.device_history: dict[str, list[tuple[str, float]]] = {}

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculates great-circle distance between two geographic coordinates in kilometers.
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
        return DeviceGeoAnomalyDetector.EARTH_RADIUS_KM * c

    def record_and_evaluate(
        self,
        user_id: str,
        lat: float,
        lon: float,
        timestamp: float | None = None,
        device_fingerprint: str | None = None,
        is_vpn_or_datacenter: bool = False,
    ) -> dict[str, Any]:
        """
        Evaluates geolocation velocity against historical baseline, tracks device churn,
        and generates explainable anomaly signals and a composite geo-risk score.
        """
        now = timestamp if timestamp is not None else time.time()
        flags: list[str] = []
        impossible_travel = False
        calculated_speed_kmh = 0.0
        distance_km = 0.0
        time_delta_seconds = 0.0
        risk_components: list[float] = [0.0]

        # 1. Geolocation and Impossible Travel Check
        if self.location_history.get(user_id):
            last_record = self.location_history[user_id][-1]
            time_delta_seconds = now - last_record["timestamp"]

            if time_delta_seconds >= 0.0:
                distance_km = self.haversine_distance(
                    last_record["lat"], last_record["lon"], lat, lon
                )

                hours = time_delta_seconds / 3600.0
                if hours < 0.001:  # Sub-3.6 seconds
                    if distance_km > 5.0:
                        calculated_speed_kmh = round(distance_km / 0.001, 1)
                        impossible_travel = True
                        flags.append(
                            f"IMPOSSIBLE_CONCURRENT_TRAVEL ({round(distance_km, 1)}km in {round(time_delta_seconds, 1)}s)"
                        )
                        risk_components.append(0.95)
                else:
                    calculated_speed_kmh = round(distance_km / hours, 1)
                    if calculated_speed_kmh > self.max_plausible_speed_kmh:
                        impossible_travel = True
                        flags.append(
                            f"IMPOSSIBLE_TRAVEL_SPEED ({calculated_speed_kmh} km/h > {self.max_plausible_speed_kmh} km/h)"
                        )
                        excess_ratio = (
                            calculated_speed_kmh / self.max_plausible_speed_kmh
                        )
                        risk_score_speed = min(0.90, 0.50 + (excess_ratio - 1.0) * 0.15)
                        risk_components.append(round(risk_score_speed, 3))

        # Store location update
        if user_id not in self.location_history:
            self.location_history[user_id] = []
        self.location_history[user_id].append(
            {
                "lat": lat,
                "lon": lon,
                "timestamp": now,
            }
        )
        if len(self.location_history[user_id]) > 20:
            self.location_history[user_id] = self.location_history[user_id][-20:]

        # 2. Device Fingerprint Churn Check
        device_churn = False
        distinct_devices = 0
        if device_fingerprint:
            if user_id not in self.device_history:
                self.device_history[user_id] = []

            cutoff = now - self.device_churn_window_seconds
            self.device_history[user_id] = [
                (dev, ts) for dev, ts in self.device_history[user_id] if ts >= cutoff
            ]
            self.device_history[user_id].append((device_fingerprint, now))

            unique_devs = {dev for dev, _ in self.device_history[user_id]}
            distinct_devices = len(unique_devs)
            if distinct_devices > self.max_allowed_devices_in_window:
                device_churn = True
                flags.append(
                    f"HIGH_DEVICE_CHURN ({distinct_devices} distinct devices in 24h)"
                )
                risk_components.append(0.65)

        # 3. Datacenter / VPN Anonymizer Check
        if is_vpn_or_datacenter:
            flags.append("DATACENTER_OR_ANONYMOUS_PROXY_DETECTED")
            risk_components.append(0.35)

        geo_risk_score = min(1.0, max(risk_components))

        # Determine Severity Tier
        if geo_risk_score >= 0.80:
            tier = "CRITICAL_FRAUD"
        elif geo_risk_score >= 0.60:
            tier = "HIGH_RISK"
        elif geo_risk_score >= 0.30:
            tier = "SUSPICIOUS"
        else:
            tier = "LOW_RISK"

        return {
            "user_id": user_id,
            "geo_risk_score": round(geo_risk_score, 4),
            "severity_tier": tier,
            "impossible_travel_detected": impossible_travel,
            "calculated_speed_kmh": calculated_speed_kmh,
            "distance_km": round(distance_km, 2),
            "time_delta_seconds": round(time_delta_seconds, 2),
            "device_churn_detected": device_churn,
            "distinct_devices_count": distinct_devices,
            "anomaly_flags": flags,
        }


class BehavioralRiskDecayEngine:
    """
    Applies temporal exponential half-life decay to past risk scores and infractions.
    Provides calibrated risk rehabilitation based on elapsed time and subsequent verified clean events.
    """

    def __init__(
        self,
        default_half_life_days: float = 14.0,
        residual_risk_floor: float = 0.05,
        clean_event_discount_factor: float = 0.90,
    ):
        self.default_half_life_days = default_half_life_days
        self.residual_risk_floor = residual_risk_floor
        self.clean_event_discount_factor = clean_event_discount_factor
        # entity_id -> {"peak_risk": float, "last_infraction_ts": float, "clean_events_since": int}
        self.profiles: dict[str, dict[str, Any]] = {}

    def record_infraction(
        self,
        entity_id: str,
        risk_score: float,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """
        Records a new risk infraction for an entity, updating their peak risk profile.
        """
        now = timestamp if timestamp is not None else time.time()
        score = min(1.0, max(0.0, float(risk_score)))

        if entity_id not in self.profiles:
            self.profiles[entity_id] = {
                "peak_risk": score,
                "last_infraction_ts": now,
                "clean_events_since": 0,
            }
        else:
            current_decayed = self.calculate_decayed_risk(entity_id, now)[
                "decayed_risk_score"
            ]
            self.profiles[entity_id] = {
                "peak_risk": max(score, current_decayed),
                "last_infraction_ts": now,
                "clean_events_since": 0,
            }

        return {
            "entity_id": entity_id,
            "recorded_risk": score,
            "timestamp": now,
            "clean_events_since": 0,
        }

    def record_clean_event(
        self,
        entity_id: str,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """
        Records a verified benign transaction, accelerating risk rehabilitation.
        """
        now = timestamp if timestamp is not None else time.time()
        if entity_id in self.profiles:
            self.profiles[entity_id]["clean_events_since"] += 1
            count = self.profiles[entity_id]["clean_events_since"]
        else:
            count = 1

        decay_info = self.calculate_decayed_risk(entity_id, now)
        return {
            "entity_id": entity_id,
            "clean_events_count": count,
            "decayed_risk_score": decay_info["decayed_risk_score"],
        }

    def calculate_decayed_risk(
        self,
        entity_id: str,
        current_timestamp: float | None = None,
        half_life_days: float | None = None,
    ) -> dict[str, Any]:
        """
        Calculates time-decayed risk score using exponential half-life formula:
        R(t) = R_floor + (R_peak - R_floor) * (0.5 ** (delta_days / half_life)) * (discount ** clean_events)
        """
        now = current_timestamp if current_timestamp is not None else time.time()
        if entity_id not in self.profiles:
            return {
                "entity_id": entity_id,
                "original_peak_risk": 0.0,
                "decayed_risk_score": 0.0,
                "days_elapsed": 0.0,
                "half_life_days": half_life_days or self.default_half_life_days,
                "clean_events_discount_applied": False,
                "clean_events_count": 0,
                "rehabilitation_complete": True,
            }

        profile = self.profiles[entity_id]
        peak = profile["peak_risk"]
        infraction_ts = profile["last_infraction_ts"]
        clean_count = profile["clean_events_since"]

        hl_days = (
            half_life_days
            if half_life_days is not None
            else self.default_half_life_days
        )
        elapsed_seconds = max(0.0, now - infraction_ts)
        elapsed_days = elapsed_seconds / 86400.0

        # Base exponential decay
        decay_factor = 0.5 ** (elapsed_days / max(0.001, hl_days))

        # Clean event bonus discount
        behavior_discount = self.clean_event_discount_factor**clean_count

        excess_risk = max(0.0, peak - self.residual_risk_floor)
        decayed = self.residual_risk_floor + (
            excess_risk * decay_factor * behavior_discount
        )
        floor_limit = (
            self.residual_risk_floor if peak >= self.residual_risk_floor else 0.0
        )
        final_decayed = min(peak, max(floor_limit, decayed))

        # Check if rehabilitation reached floor
        rehab_complete = final_decayed <= (self.residual_risk_floor + 0.005)

        return {
            "entity_id": entity_id,
            "original_peak_risk": round(peak, 4),
            "decayed_risk_score": round(final_decayed, 4),
            "days_elapsed": round(elapsed_days, 2),
            "half_life_days": hl_days,
            "clean_events_discount_applied": clean_count > 0,
            "clean_events_count": clean_count,
            "rehabilitation_complete": rehab_complete,
        }


class ModalConflictDetector:
    """
    Detects inter-modal divergence, discrepancy anomalies, and adversarial masking
    where acute fraud signals in one modality are diluted by benign signals in others.
    """

    def __init__(
        self,
        conflict_divergence_threshold: float = 0.45,
        masking_boost_factor: float = 0.25,
    ):
        self.conflict_divergence_threshold = conflict_divergence_threshold
        self.masking_boost_factor = masking_boost_factor

    def evaluate_modalities(
        self,
        modality_scores: dict[str, float],
    ) -> dict[str, Any]:
        """
        Analyzes discrepancy across named modalities (e.g. {'text': 0.1, 'visual': 0.95, 'metadata': 0.2}).
        Calculates pairwise divergence, max spread, conflict entropy, and anti-masking penalty.
        """
        clean_scores = {
            k: min(1.0, max(0.0, float(v)))
            for k, v in modality_scores.items()
            if v is not None
        }

        if len(clean_scores) < 2:
            single_score = next(iter(clean_scores.values())) if clean_scores else 0.0
            return {
                "max_divergence": 0.0,
                "mean_divergence": 0.0,
                "conflict_detected": False,
                "conflict_tier": "CONGRUENT",
                "divergence_pairs": [],
                "conflict_penalty": 0.0,
                "linear_fused_risk": round(single_score, 4),
                "adjusted_fused_risk": round(single_score, 4),
            }

        pairs = []
        keys = list(clean_scores.keys())
        diffs = []
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                k1, k2 = keys[i], keys[j]
                diff = abs(clean_scores[k1] - clean_scores[k2])
                diffs.append(diff)
                pairs.append(
                    {
                        "modality_a": k1,
                        "modality_b": k2,
                        "score_a": clean_scores[k1],
                        "score_b": clean_scores[k2],
                        "divergence": round(diff, 4),
                    }
                )

        max_div = max(diffs) if diffs else 0.0
        mean_div = sum(diffs) / len(diffs) if diffs else 0.0
        peak_score = max(clean_scores.values())
        linear_mean = sum(clean_scores.values()) / len(clean_scores)

        # Detect conflict tier
        conflict_detected = max_div >= self.conflict_divergence_threshold
        if max_div >= 0.70 and peak_score >= 0.75:
            tier = "CRITICAL_MODAL_MASKING"
            penalty = round(self.masking_boost_factor * (max_div / 1.0), 3)
        elif conflict_detected:
            tier = "HIGH_CONFLICT"
            penalty = round(self.masking_boost_factor * 0.6 * (max_div / 1.0), 3)
        elif max_div >= 0.25:
            tier = "MILD_DISCREPANCY"
            penalty = 0.0
        else:
            tier = "CONGRUENT"
            penalty = 0.0

        # Anti-masking adjusted risk ensures peak fraud signal is preserved
        adjusted_risk = min(
            1.0,
            max(
                linear_mean + penalty,
                peak_score * (1.0 - (1.0 - max_div) * 0.2),
            ),
        )

        return {
            "max_divergence": round(max_div, 4),
            "mean_divergence": round(mean_div, 4),
            "conflict_detected": conflict_detected,
            "conflict_tier": tier,
            "divergence_pairs": pairs,
            "conflict_penalty": penalty,
            "linear_fused_risk": round(linear_mean, 4),
            "adjusted_fused_risk": round(adjusted_risk, 4),
        }


class BayesianCostSensitiveDecisionEngine:
    """
    Bayesian cost-sensitive risk decision engine.
    Optimizes fraud mitigation actions by minimizing expected loss across
    false positive churn, operational review expense, friction abandonment,
    and direct chargeback losses.
    """

    POLICY_PRESETS: ClassVar[dict[str, dict[str, float]]] = {
        "BALANCED": {
            "churn_on_block_probability": 0.80,
            "friction_drop_rate": 0.04,
            "stepup_fraud_block_rate": 0.92,
            "analyst_catch_rate": 0.96,
            "analyst_false_reject_rate": 0.01,
        },
        "CONSERVATIVE": {
            "churn_on_block_probability": 0.60,
            "friction_drop_rate": 0.02,
            "stepup_fraud_block_rate": 0.95,
            "analyst_catch_rate": 0.98,
            "analyst_false_reject_rate": 0.02,
        },
        "AGGRESSIVE_GROWTH": {
            "churn_on_block_probability": 0.95,
            "friction_drop_rate": 0.07,
            "stepup_fraud_block_rate": 0.88,
            "analyst_catch_rate": 0.94,
            "analyst_false_reject_rate": 0.005,
        },
    }

    def __init__(
        self,
        default_ltv: float = 250.0,
        default_chargeback_fee: float = 25.0,
        default_review_cost: float = 8.0,
        policy_mode: str = "BALANCED",
    ):
        self.default_ltv = default_ltv
        self.default_chargeback_fee = default_chargeback_fee
        self.default_review_cost = default_review_cost
        self.policy_mode = (
            policy_mode if policy_mode in self.POLICY_PRESETS else "BALANCED"
        )
        self.params = self.POLICY_PRESETS[self.policy_mode]

    def evaluate_transaction(
        self,
        fraud_probability: float,
        transaction_amount: float,
        customer_lifetime_value: float | None = None,
        chargeback_fee: float | None = None,
        review_operational_cost: float | None = None,
        policy_override: str | None = None,
    ) -> dict[str, Any]:
        """
        Calculates expected loss for each mitigation action and selects the optimal Bayes decision.
        """
        p = min(1.0, max(0.0, float(fraud_probability)))
        amt = max(0.0, float(transaction_amount))
        ltv = float(
            customer_lifetime_value
            if customer_lifetime_value is not None
            else self.default_ltv
        )
        cb_fee = float(
            chargeback_fee
            if chargeback_fee is not None
            else self.default_chargeback_fee
        )
        rev_cost = float(
            review_operational_cost
            if review_operational_cost is not None
            else self.default_review_cost
        )

        policy = self.POLICY_PRESETS.get(
            policy_override or self.policy_mode, self.params
        )

        # 1. APPROVE: Loss is incurred only if transaction is fraudulent (chargeback + direct amount)
        loss_fraud = amt + cb_fee
        e_approve = p * loss_fraud

        # 2. BLOCK_TRANSACTION: Loss is customer churn if the customer is legitimate
        p_legit = 1.0 - p
        e_block = p_legit * policy["churn_on_block_probability"] * ltv

        # 3. STEP_UP_CHALLENGE (e.g. 3D-Secure, Passkey, MFA, ID selfie):
        # Legitimate users experience friction drop; fraud is partially mitigated
        e_stepup = (
            p_legit * (policy["friction_drop_rate"] * ltv)
            + p * (1.0 - policy["stepup_fraud_block_rate"]) * loss_fraud
        )

        # 4. MANUAL_REVIEW:
        # Operational review cost always incurred; analyst catch rate and false reject rate applied
        e_review = (
            rev_cost
            + p * (1.0 - policy["analyst_catch_rate"]) * loss_fraud
            + p_legit * policy["analyst_false_reject_rate"] * ltv
        )

        expected_losses = {
            "APPROVE": round(e_approve, 4),
            "STEP_UP_CHALLENGE": round(e_stepup, 4),
            "MANUAL_REVIEW": round(e_review, 4),
            "BLOCK_TRANSACTION": round(e_block, 4),
        }

        # Select minimal expected loss action
        optimal_action = min(expected_losses, key=expected_losses.get)
        min_loss = expected_losses[optimal_action]

        # Naive rule baseline (0.50 cutoff: approve if <= 0.50 else block)
        naive_action = "APPROVE" if p <= 0.50 else "BLOCK_TRANSACTION"
        naive_loss = expected_losses[naive_action]
        expected_savings = round(max(0.0, naive_loss - min_loss), 4)

        rationale = self._generate_rationale(
            optimal_action, p, amt, min_loss, expected_losses
        )

        return {
            "optimal_action": optimal_action,
            "fraud_probability": round(p, 4),
            "transaction_amount": round(amt, 2),
            "expected_losses": expected_losses,
            "minimized_expected_loss": round(min_loss, 4),
            "naive_threshold_action": naive_action,
            "expected_savings_vs_naive": expected_savings,
            "policy_mode": policy_override or self.policy_mode,
            "decision_rationale": rationale,
        }

    def _generate_rationale(
        self,
        action: str,
        p: float,
        amt: float,
        min_loss: float,
        losses: dict[str, float],
    ) -> str:
        pct = round(p * 100, 1)
        if action == "APPROVE":
            return (
                f"Approved: low estimated fraud probability ({pct}%) makes direct approval "
                f"the lowest risk cost (${min_loss:.2f}) compared to user friction or review."
            )
        elif action == "STEP_UP_CHALLENGE":
            return (
                f"Step-Up Challenge required: at {pct}% fraud risk for ${amt:.2f}, "
                f"automated step-up authentication minimizes loss (${min_loss:.2f}) "
                f"by blocking {int(self.params['stepup_fraud_block_rate'] * 100)}% of fraud with low user drop-off."
            )
        elif action == "MANUAL_REVIEW":
            return (
                f"Escalated to Manual Analyst Review: high transaction value (${amt:.2f}) "
                f"at {pct}% risk justifies operational review expense to minimize expected loss (${min_loss:.2f})."
            )
        else:  # BLOCK_TRANSACTION
            return (
                f"Blocked: acute fraud probability ({pct}%) on ${amt:.2f} transaction makes "
                f"immediate block optimal (${min_loss:.2f}), avoiding imminent chargeback liability."
            )


class PerceptualHashCollisionDetector:
    """
    Detects near-duplicate image collisions and document reuse attacks across accounts
    using 64-bit perceptual difference hashing (dHash/aHash) and Hamming distance indexing.
    """

    def __init__(
        self,
        max_collision_hamming_distance: int = 10,
        exact_match_threshold: int = 2,
    ):
        self.max_collision_hamming_distance = max_collision_hamming_distance
        self.exact_match_threshold = exact_match_threshold
        # entity_id -> list of {"image_id": str, "phash": int, "timestamp": float}
        self.entity_records: dict[str, list[dict[str, Any]]] = {}
        # list of {"entity_id": str, "image_id": str, "phash": int, "timestamp": float}
        self.global_index: list[dict[str, Any]] = []

    @staticmethod
    def hamming_distance(hash1: int | str, hash2: int | str) -> int:
        """
        Computes the number of bit positions in which two 64-bit hashes differ.
        Accepts integers or 16-character hexadecimal strings.
        """
        int1 = int(hash1, 16) if isinstance(hash1, str) else int(hash1)
        int2 = int(hash2, 16) if isinstance(hash2, str) else int(hash2)
        xor_result = int1 ^ int2
        return xor_result.bit_count()

    @staticmethod
    def compute_similarity(
        hash1: int | str, hash2: int | str, bit_length: int = 64
    ) -> float:
        """
        Computes normalized perceptual similarity in range [0.0, 1.0].
        """
        dist = PerceptualHashCollisionDetector.hamming_distance(hash1, hash2)
        return round(max(0.0, min(1.0, 1.0 - (dist / float(bit_length)))), 4)

    def register_and_scan(
        self,
        entity_id: str,
        image_id: str,
        phash: int | str,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """
        Registers an image perceptual hash and scans the index for cross-entity duplicate collisions.
        """
        now = timestamp if timestamp is not None else time.time()
        hash_val = int(phash, 16) if isinstance(phash, str) else int(phash)

        collisions = []
        same_entity_duplicate = False

        for entry in self.global_index:
            dist = self.hamming_distance(hash_val, entry["phash"])
            if dist <= self.max_collision_hamming_distance:
                is_cross_entity = entry["entity_id"] != entity_id
                similarity = round(1.0 - (dist / 64.0), 4)

                collision_record = {
                    "matched_entity_id": entry["entity_id"],
                    "matched_image_id": entry["image_id"],
                    "hamming_distance": dist,
                    "similarity": similarity,
                    "is_cross_entity": is_cross_entity,
                    "matched_timestamp": entry["timestamp"],
                }
                collisions.append(collision_record)

                if not is_cross_entity:
                    same_entity_duplicate = True

        collisions.sort(key=lambda c: c["hamming_distance"])
        cross_entity_collisions = [c for c in collisions if c["is_cross_entity"]]

        duplicate_detected = len(cross_entity_collisions) > 0
        min_cross_dist = (
            min([c["hamming_distance"] for c in cross_entity_collisions])
            if cross_entity_collisions
            else 64
        )

        if min_cross_dist <= self.exact_match_threshold:
            severity = "CRITICAL_FRAUD"
            risk_score = 0.95
            flag = f"IDENTICAL_DOCUMENT_REUSE_DETECTED ({len(cross_entity_collisions)} cross-entity matches, dist={min_cross_dist})"
        elif duplicate_detected:
            severity = "HIGH_RISK"
            sim_pct = round((1.0 - (min_cross_dist / 64.0)) * 100, 1)
            risk_score = min(0.85, 0.50 + ((10 - min_cross_dist) * 0.035))
            flag = f"NEAR_DUPLICATE_IMAGE_COLLISION ({sim_pct}% perceptual similarity, dist={min_cross_dist})"
        elif same_entity_duplicate:
            severity = "SUSPICIOUS"
            risk_score = 0.30
            flag = "SELF_RETRY_DUPLICATE_UPLOAD"
        else:
            severity = "LOW_RISK"
            risk_score = 0.0
            flag = "UNIQUE_DOCUMENT"

        new_entry = {
            "entity_id": entity_id,
            "image_id": image_id,
            "phash": hash_val,
            "timestamp": now,
        }
        self.global_index.append(new_entry)
        if entity_id not in self.entity_records:
            self.entity_records[entity_id] = []
        self.entity_records[entity_id].append(new_entry)

        return {
            "entity_id": entity_id,
            "image_id": image_id,
            "phash_hex": hex(hash_val),
            "duplicate_detected": duplicate_detected,
            "collision_count": len(cross_entity_collisions),
            "nearest_collision_distance": (
                min_cross_dist if duplicate_detected else None
            ),
            "severity_tier": severity,
            "duplicate_risk_score": round(risk_score, 4),
            "collision_flag": flag,
            "top_collisions": cross_entity_collisions[:5],
        }


class RiskPopulationDriftMonitor:
    """
    Monitors statistical distribution drift and concept shift between baseline (reference)
    and production (current) populations of fraud risk scores.

    Provides:
    - Population Stability Index (PSI) calculation across binned score distributions.
    - Wasserstein Distance (1D Earth Mover's Distance) measuring work to transform distributions.
    - Drift alert tiers: STABLE (PSI < 0.10), MODERATE_DRIFT (0.10 <= PSI < 0.25),
      and SIGNIFICANT_DRIFT (PSI >= 0.25).
    - Population summary diagnostics (mean, standard deviation, median, drift delta).
    """

    def __init__(self, default_bins: int = 10, epsilon: float = 1e-4):
        if default_bins < 2:
            raise ValueError("default_bins must be at least 2")
        self.default_bins = default_bins
        self.epsilon = epsilon

    @staticmethod
    def _calculate_stats(scores: list[float]) -> dict[str, float]:
        if not scores:
            return {"count": 0, "mean": 0.0, "std": 0.0, "median": 0.0}
        n = len(scores)
        mean_val = sum(scores) / n
        variance = sum((x - mean_val) ** 2 for x in scores) / n if n > 1 else 0.0
        sorted_s = sorted(scores)
        if n % 2 == 1:
            median_val = sorted_s[n // 2]
        else:
            median_val = (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2.0
        return {
            "count": n,
            "mean": round(mean_val, 4),
            "std": round(math.sqrt(variance), 4),
            "median": round(median_val, 4),
        }

    @staticmethod
    def compute_wasserstein_distance(
        u_scores: list[float], v_scores: list[float]
    ) -> float:
        """
        Computes 1D Wasserstein-1 (Earth Mover's) Distance between empirical sample distributions u and v:
        W_1(u, v) = integral |F_u(x) - F_v(x)| dx
        """
        if not u_scores or not v_scores:
            raise ValueError("Input score samples must not be empty")

        u_sorted = sorted(u_scores)
        v_sorted = sorted(v_scores)
        all_vals = sorted(set(u_sorted + v_sorted))
        if len(all_vals) <= 1:
            return 0.0

        n_u = len(u_sorted)
        n_v = len(v_sorted)

        total_work = 0.0
        for i in range(len(all_vals) - 1):
            x = all_vals[i]
            x_next = all_vals[i + 1]
            delta = x_next - x
            # empirical CDF at x
            f_u = bisect.bisect_right(u_sorted, x) / n_u
            f_v = bisect.bisect_right(v_sorted, x) / n_v
            total_work += abs(f_u - f_v) * delta

        return round(total_work, 4)

    def compute_psi(
        self,
        reference_scores: list[float],
        current_scores: list[float],
        num_bins: int | None = None,
    ) -> tuple[float, list[dict[str, Any]]]:
        """
        Calculates Population Stability Index (PSI) between reference and current populations.
        PSI = sum ( (Q_i - P_i) * ln(Q_i / P_i) )
        """
        if not reference_scores or not current_scores:
            raise ValueError("Both reference and current populations must be non-empty")

        bins_count = num_bins or self.default_bins
        if bins_count < 2:
            raise ValueError("Number of bins must be at least 2")

        combined = reference_scores + current_scores
        min_val = min(combined)
        max_val = max(combined)

        if math.isclose(min_val, max_val):
            return 0.0, []

        step = (max_val - min_val) / bins_count
        bin_edges = [min_val + i * step for i in range(bins_count + 1)]
        bin_edges[-1] = max_val

        n_ref = len(reference_scores)
        n_curr = len(current_scores)

        ref_counts = [0] * bins_count
        curr_counts = [0] * bins_count

        for s in reference_scores:
            idx = int((s - min_val) / step)
            if idx >= bins_count:
                idx = bins_count - 1
            elif idx < 0:
                idx = 0
            ref_counts[idx] += 1

        for s in current_scores:
            idx = int((s - min_val) / step)
            if idx >= bins_count:
                idx = bins_count - 1
            elif idx < 0:
                idx = 0
            curr_counts[idx] += 1

        bin_details: list[dict[str, Any]] = []
        total_psi = 0.0

        for i in range(bins_count):
            lower_edge = bin_edges[i]
            upper_edge = bin_edges[i + 1]

            p_raw = ref_counts[i] / n_ref
            q_raw = curr_counts[i] / n_curr

            p_smooth = (p_raw + self.epsilon) / (1.0 + bins_count * self.epsilon)
            q_smooth = (q_raw + self.epsilon) / (1.0 + bins_count * self.epsilon)

            bin_psi = (q_smooth - p_smooth) * math.log(q_smooth / p_smooth)
            total_psi += bin_psi

            range_label = (
                f"[{round(lower_edge, 3)}, {round(upper_edge, 3)})"
                if i < bins_count - 1
                else f"[{round(lower_edge, 3)}, {round(upper_edge, 3)}]"
            )

            bin_details.append(
                {
                    "bin_index": i,
                    "range": range_label,
                    "reference_count": ref_counts[i],
                    "current_count": curr_counts[i],
                    "reference_pct": round(p_raw, 4),
                    "current_pct": round(q_raw, 4),
                    "bin_psi": round(bin_psi, 6),
                }
            )

        return round(total_psi, 4), bin_details

    def evaluate_drift(
        self,
        reference_scores: list[float],
        current_scores: list[float],
        num_bins: int | None = None,
    ) -> dict[str, Any]:
        """
        Executes complete population drift analysis comparing baseline vs current scores.
        """
        psi_val, bin_breakdown = self.compute_psi(
            reference_scores, current_scores, num_bins=num_bins
        )
        wasserstein = self.compute_wasserstein_distance(
            reference_scores, current_scores
        )
        ref_stats = self._calculate_stats(reference_scores)
        curr_stats = self._calculate_stats(current_scores)

        mean_shift = round(curr_stats["mean"] - ref_stats["mean"], 4)

        if psi_val < 0.10:
            drift_level = "STABLE"
            requires_retraining = False
            action = "NO_ACTION_REQUIRED"
        elif psi_val < 0.25:
            drift_level = "MODERATE_DRIFT"
            requires_retraining = False
            action = "MONITOR_CLOSELY_AND_REVIEW_THRESHOLDS"
        else:
            drift_level = "SIGNIFICANT_DRIFT"
            requires_retraining = True
            action = "RETRAIN_MODEL_AND_RECALIBRATE_CUTOFFS"

        return {
            "psi": psi_val,
            "wasserstein_distance": wasserstein,
            "drift_level": drift_level,
            "requires_retraining": requires_retraining,
            "recommended_action": action,
            "mean_shift": mean_shift,
            "reference_stats": ref_stats,
            "current_stats": curr_stats,
            "bin_breakdown": bin_breakdown,
        }


class SyntheticIdentityScorer:
    """
    Evaluates applicant and claim identities for synthetic identity fraud (SIF) indicators.

    Synthesizes signals from:
    - Burner/disposable email domain recognition
    - Shannon entropy & lexical randomness of email handle / username
    - Name-to-email-handle semantic alignment
    - Telephony carrier risk profiling (VOIP / virtual vs verified mobile)
    - Profile tenure and creation recency
    """

    KNOWN_DISPOSABLE_DOMAINS: ClassVar[set[str]] = {
        "mailinator.com",
        "guerrillamail.com",
        "tempmail.com",
        "10minutemail.com",
        "throwawaymail.com",
        "sharklasers.com",
        "yopmail.com",
        "trashmail.com",
        "dispostable.com",
        "fakemailgenerator.com",
        "mytemp.email",
        "temp-mail.org",
        "burnermail.io",
        "inboxkitten.com",
        "getairmail.com",
    }

    CARRIER_RISK_MAP: ClassVar[dict[str, float]] = {
        "VOIP": 0.75,
        "VIRTUAL": 0.70,
        "PREPAID": 0.40,
        "LANDLINE": 0.20,
        "MOBILE": 0.05,
        "POSTPAID": 0.05,
        "UNKNOWN": 0.35,
    }

    def __init__(
        self,
        domain_weight: float = 0.35,
        alignment_weight: float = 0.25,
        entropy_weight: float = 0.20,
        carrier_weight: float = 0.15,
        tenure_weight: float = 0.05,
    ):
        weights = {
            "domain": domain_weight,
            "alignment": alignment_weight,
            "entropy": entropy_weight,
            "carrier": carrier_weight,
            "tenure": tenure_weight,
        }
        total = sum(weights.values())
        self.weights = {k: v / total for k, v in weights.items()}

    @staticmethod
    def calculate_shannon_entropy(text: str) -> float:
        """
        Calculates Shannon entropy (in bits) for the character distribution in a string.
        H(X) = - sum(p_i * log2(p_i))
        """
        if not text:
            return 0.0
        n = len(text)
        counts: dict[str, int] = {}
        for ch in text.lower():
            counts[ch] = counts.get(ch, 0) + 1

        entropy = 0.0
        for count in counts.values():
            p = count / n
            entropy -= p * math.log2(p)
        return round(entropy, 4)

    @staticmethod
    def evaluate_handle_randomness(handle: str) -> float:
        """
        Assesses if an email handle resembles machine-generated random alphanumeric strings.
        Combines Shannon entropy, digit ratio, and vowel deficit.
        Returns a score in [0.0, 1.0].
        """
        clean_handle = re.sub(r"[._-]", "", handle.lower())
        length = len(clean_handle)
        if length < 3:
            return 0.20

        entropy = SyntheticIdentityScorer.calculate_shannon_entropy(clean_handle)
        max_possible_entropy = math.log2(length) if length > 1 else 1.0
        entropy_ratio = (
            min(1.0, entropy / max_possible_entropy)
            if max_possible_entropy > 0
            else 0.0
        )

        digits_count = sum(1 for c in clean_handle if c.isdigit())
        digit_ratio = digits_count / length

        vowels = set("aeiou")
        vowel_count = sum(1 for c in clean_handle if c in vowels)
        vowel_ratio = vowel_count / length

        randomness = 0.0
        if entropy_ratio > 0.85 and length >= 6:
            randomness += 0.40
        elif entropy_ratio > 0.70:
            randomness += 0.20

        if digit_ratio > 0.40:
            randomness += 0.35
        elif digit_ratio > 0.20:
            randomness += 0.15

        if vowel_ratio < 0.15 and length >= 6:
            randomness += 0.30

        return round(min(1.0, randomness), 4)

    @staticmethod
    def compute_name_handle_alignment(name: str, handle: str) -> float:
        """
        Evaluates lexical alignment between declared full name and email handle.
        Returns alignment score in [0.0, 1.0] where 1.0 is high alignment (e.g. aditya.malkar == Aditya Malkar)
        and 0.0 is zero correlation / mismatch.
        """
        if not name or not handle:
            return 0.5

        clean_name = re.sub(r"[^a-zA-Z\s]", "", name.lower()).strip()
        tokens = [t for t in clean_name.split() if len(t) >= 2]
        if not tokens:
            return 0.5

        clean_handle = re.sub(r"[^a-zA-Z0-9]", "", handle.lower())
        if not clean_handle:
            return 0.5

        matched_tokens = 0
        for token in tokens:
            if token in clean_handle:
                matched_tokens += 1

        if matched_tokens == len(tokens):
            return 1.0

        if len(tokens) >= 2:
            initials_combo = tokens[0][0] + tokens[-1]
            if initials_combo in clean_handle:
                return 0.85
            reverse_combo = tokens[-1] + tokens[0][0]
            if reverse_combo in clean_handle:
                return 0.80

        if matched_tokens > 0:
            return round(matched_tokens / len(tokens), 2)

        return 0.0

    def evaluate_identity(
        self,
        name: str,
        email: str,
        phone_carrier: str = "MOBILE",
        account_age_days: int | None = None,
    ) -> dict[str, Any]:
        """
        Runs comprehensive synthetic identity risk evaluation.
        """
        email_clean = email.strip().lower()
        if "@" in email_clean:
            handle, domain = email_clean.split("@", 1)
        else:
            handle = email_clean
            domain = ""

        flags: list[str] = []

        # 1. Domain Risk
        is_disposable = domain in self.KNOWN_DISPOSABLE_DOMAINS
        if is_disposable:
            flags.append(f"DISPOSABLE_BURNER_EMAIL_DOMAIN ({domain})")
            domain_risk = 1.0
        else:
            domain_risk = 0.0

        # 2. Handle Randomness Risk
        handle_randomness = self.evaluate_handle_randomness(handle)
        entropy = self.calculate_shannon_entropy(handle)
        if handle_randomness >= 0.65:
            flags.append("HIGH_ENTROPY_RANDOM_EMAIL_HANDLE")

        # 3. Name Alignment Risk
        alignment = self.compute_name_handle_alignment(name, handle)
        alignment_risk = round(1.0 - alignment, 4)
        if alignment_risk >= 0.80 and name.strip():
            flags.append("NAME_EMAIL_IDENTITY_MISMATCH")

        # 4. Carrier Risk
        carrier_normalized = phone_carrier.strip().upper()
        carrier_risk = self.CARRIER_RISK_MAP.get(carrier_normalized, 0.35)
        if carrier_normalized in ("VOIP", "VIRTUAL"):
            flags.append(f"HIGH_RISK_TELEPHONY_CARRIER ({carrier_normalized})")

        # 5. Tenure Risk
        if account_age_days is not None:
            if account_age_days < 2:
                tenure_risk = 0.70
                flags.append("NEWLY_CREATED_ACCOUNT_UNDER_48H")
            elif account_age_days < 14:
                tenure_risk = 0.30
            else:
                tenure_risk = 0.0
        else:
            tenure_risk = 0.15

        composite_score = (
            self.weights["domain"] * domain_risk
            + self.weights["alignment"] * alignment_risk
            + self.weights["entropy"] * handle_randomness
            + self.weights["carrier"] * carrier_risk
            + self.weights["tenure"] * tenure_risk
        )

        if is_disposable:
            composite_score = max(0.85, composite_score)

        composite_score = round(min(1.0, composite_score), 4)

        if composite_score < 0.25:
            risk_tier = "LOW_RISK"
            decision = "APPROVE"
        elif composite_score < 0.55:
            risk_tier = "ELEVATED_RISK"
            decision = "MANUAL_REVIEW"
        elif composite_score < 0.80:
            risk_tier = "HIGH_RISK"
            decision = "STEP_UP_VERIFICATION"
        else:
            risk_tier = "CRITICAL_SYNTHETIC_FRAUD"
            decision = "REJECT"

        return {
            "synthetic_risk_score": composite_score,
            "risk_tier": risk_tier,
            "decision": decision,
            "flags": flags,
            "component_risks": {
                "domain_risk": round(domain_risk, 4),
                "handle_randomness_risk": handle_randomness,
                "handle_entropy_bits": entropy,
                "name_alignment_risk": alignment_risk,
                "carrier_risk": round(carrier_risk, 4),
                "tenure_risk": round(tenure_risk, 4),
            },
            "identity_metadata": {
                "name": name,
                "email_handle": handle,
                "email_domain": domain,
                "is_disposable_domain": is_disposable,
                "phone_carrier": carrier_normalized,
                "account_age_days": account_age_days,
            },
        }


class AdaptiveCutoffOptimizer:
    """
    Optimizes risk score classification thresholds (cutoffs) against operational constraints
    such as False Positive Rate (FPR) budgets, minimum precision targets, financial cost matrices,
    or maximal F1-score.
    """

    def __init__(self, step_size: float = 0.01):
        if not (0.001 <= step_size <= 0.1):
            raise ValueError("step_size must be between 0.001 and 0.1")
        self.step_size = step_size

    @staticmethod
    def compute_metrics_at_threshold(
        scores: list[float],
        labels: list[bool | int],
        threshold: float,
        cost_fn: float = 500.0,
        cost_fp: float = 20.0,
    ) -> dict[str, Any]:
        """
        Computes TP, FP, TN, FN, Precision, Recall, FPR, F1, Accuracy, MCC, and Expected Cost at a given threshold.
        """
        if len(scores) != len(labels):
            raise ValueError("scores and labels must have the same length")
        if not scores:
            raise ValueError("Scores and labels must not be empty")

        tp = 0
        fp = 0
        tn = 0
        fn = 0

        for s, y in zip(scores, labels, strict=False):
            pred_fraud = s >= threshold
            actual_fraud = bool(y)
            if pred_fraud and actual_fraud:
                tp += 1
            elif pred_fraud and not actual_fraud:
                fp += 1
            elif not pred_fraud and actual_fraud:
                fn += 1
            else:
                tn += 1

        total = tp + fp + tn + fn
        positives = tp + fn
        negatives = tn + fp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / positives if positives > 0 else 0.0
        fpr = fp / negatives if negatives > 0 else 0.0
        accuracy = (tp + tn) / total if total > 0 else 0.0

        if precision + recall > 0:
            f1 = (2 * precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        mcc_denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
        mcc = ((tp * tn) - (fp * fn)) / mcc_denom if mcc_denom > 0 else 0.0

        total_cost = (fn * cost_fn) + (fp * cost_fp)

        return {
            "threshold": round(threshold, 4),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "fpr": round(fpr, 4),
            "f1_score": round(f1, 4),
            "accuracy": round(accuracy, 4),
            "mcc": round(mcc, 4),
            "expected_financial_cost": round(total_cost, 2),
        }

    def evaluate_threshold_curve(
        self,
        scores: list[float],
        labels: list[bool | int],
        cost_fn: float = 500.0,
        cost_fp: float = 20.0,
    ) -> list[dict[str, Any]]:
        """
        Sweeps threshold from 0.0 to 1.0 with self.step_size and returns metrics across the continuum.
        """
        results: list[dict[str, Any]] = []
        steps = round(1.0 / self.step_size)
        for i in range(steps + 1):
            t = round(i * self.step_size, 4)
            metrics = self.compute_metrics_at_threshold(
                scores, labels, t, cost_fn=cost_fn, cost_fp=cost_fp
            )
            results.append(metrics)
        return results

    def optimize_cutoff(
        self,
        scores: list[float],
        labels: list[bool | int],
        strategy: str = "MAX_F1",
        max_fpr: float | None = None,
        min_precision: float | None = None,
        cost_fn: float = 500.0,
        cost_fp: float = 20.0,
    ) -> dict[str, Any]:
        """
        Finds the optimal cutoff theta* subject to constraints or optimization objective.

        Strategies:
        - "MAX_F1": Maximizes harmonic mean of precision and recall.
        - "FPR_BUDGET": Maximizes recall subject to FPR <= max_fpr (defaults to 0.02).
        - "PRECISION_TARGET": Maximizes recall subject to Precision >= min_precision (defaults to 0.90).
        - "MIN_COST": Minimizes expected financial operational losses (fn * cost_fn + fp * cost_fp).
        """
        curve = self.evaluate_threshold_curve(
            scores, labels, cost_fn=cost_fn, cost_fp=cost_fp
        )

        baseline_metric = self.compute_metrics_at_threshold(
            scores, labels, 0.50, cost_fn=cost_fn, cost_fp=cost_fp
        )

        optimal_entry: dict[str, Any] | None = None

        if strategy == "FPR_BUDGET":
            budget = max_fpr if max_fpr is not None else 0.02
            eligible = [m for m in curve if m["fpr"] <= budget]
            if eligible:
                optimal_entry = max(
                    eligible, key=lambda m: (m["recall"], m["f1_score"])
                )
            else:
                optimal_entry = min(curve, key=lambda m: m["fpr"])

        elif strategy == "PRECISION_TARGET":
            target = min_precision if min_precision is not None else 0.90
            eligible = [m for m in curve if m["precision"] >= target]
            if eligible:
                optimal_entry = max(
                    eligible, key=lambda m: (m["recall"], m["f1_score"])
                )
            else:
                optimal_entry = max(curve, key=lambda m: m["precision"])

        elif strategy == "MIN_COST":
            optimal_entry = min(curve, key=lambda m: m["expected_financial_cost"])

        else:  # MAX_F1
            optimal_entry = max(curve, key=lambda m: (m["f1_score"], m["precision"]))

        opt_theta = optimal_entry["threshold"]
        f1_delta = round(optimal_entry["f1_score"] - baseline_metric["f1_score"], 4)
        cost_delta = round(
            optimal_entry["expected_financial_cost"]
            - baseline_metric["expected_financial_cost"],
            2,
        )

        return {
            "optimal_threshold": opt_theta,
            "strategy": strategy,
            "metrics_at_optimal": optimal_entry,
            "baseline_threshold_0_5": baseline_metric,
            "improvement": {
                "f1_delta": f1_delta,
                "financial_savings": round(-cost_delta, 2),
            },
            "recommendation": (
                f"Calibrate operational decision cutoff to {opt_theta:.2f} under {strategy} policy."
            ),
        }
