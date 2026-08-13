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
        
    def calculate_risk(self, text_score: float, visual_score: float, metadata_flags: int) -> Dict[str, Any]:
        """
        Calculate the aggregate fraud risk score.
        
        Args:
            text_score (float): Probability of fraud based on text analysis (0.0 to 1.0)
            visual_score (float): Probability of fraud based on visual/deepfake analysis (0.0 to 1.0)
            metadata_flags (int): Number of suspicious metadata flags (e.g., mismatched geolocation)
            
        Returns:
            Dict: Comprehensive risk assessment containing the final score and severity tier
        """
        # Cap metadata impact at 1.0 (assuming 5 flags is max severity)
        normalized_metadata = min(metadata_flags / 5.0, 1.0)
        
        final_score = (
            (text_score * self.weights['text']) + 
            (visual_score * self.weights['visual']) + 
            (normalized_metadata * self.weights['metadata'])
        )
        
        return {
            "risk_score": round(final_score, 4),
            "severity_tier": self._determine_tier(final_score),
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
