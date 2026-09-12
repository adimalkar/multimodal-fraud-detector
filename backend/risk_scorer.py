from typing import Dict, Any

class MultimodalRiskScorer:
    """
    Core scoring engine for the Multimodal Fraud Detection system.
    Aggregates signals from text (NLP), image/video, and metadata to 
    compute a unified risk probability score using a weighted heuristic approach.
    """
    
    def __init__(self, text_weight: float = 0.4, visual_weight: float = 0.4, metadata_weight: float = 0.2):
        self.weights = {
            'text': text_weight,
            'visual': visual_weight,
            'metadata': metadata_weight
        }
        
        # Ensure weights normalize to 1.0
        total = sum(self.weights.values())
        self.weights = {k: v / total for k, v in self.weights.items()}
        
    def calculate_risk(
        self, 
        text_score: float, 
        visual_score: float, 
        metadata_flags: int,
        synergy_boost_enabled: bool = True
    ) -> Dict[str, Any]:
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
            (text_score * self.weights['text']) + 
            (visual_score * self.weights['visual']) + 
            (normalized_metadata * self.weights['metadata'])
        )
        
        # Apply compounding synergy if multiple modalities independently detect high risk (> 0.65)
        synergy_applied = False
        if synergy_boost_enabled and (text_score >= 0.65 and visual_score >= 0.65):
            synergy_applied = True
            base_score = min(1.0, base_score * 1.15)
            
        final_score = min(1.0, max(0.0, base_score))
        tier = self._determine_tier(final_score)
        
        return {
            "risk_score": round(final_score, 4),
            "severity_tier": tier,
            "recommended_action": self._determine_action(tier),
            "cross_modal_synergy_applied": synergy_applied,
            "breakdown": {
                "text_contribution": round(text_score * self.weights['text'], 4),
                "visual_contribution": round(visual_score * self.weights['visual'], 4),
                "metadata_contribution": round(normalized_metadata * self.weights['metadata'], 4)
            }
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
            "LOW_RISK": "APPROVE_AUTOMATICALLY"
        }
        return actions.get(tier, "MANUAL_REVIEW")

