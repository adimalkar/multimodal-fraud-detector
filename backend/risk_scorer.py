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
