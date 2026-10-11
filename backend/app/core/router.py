from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class SmartRouter:
    """Routes requests between Local SLM (Ollama) and Cloud Fortress (OpenAI/Anthropic) based on cost and complexity heuristics."""

    def __init__(self, complexity_token_threshold: int = 150):
        self.complexity_token_threshold = complexity_token_threshold

    def evaluate_route(self, prompt: str, user_tier: str = "standard") -> Dict[str, Any]:
        """Determines optimal destination provider and estimated cost/latency budget."""
        token_estimate = len(prompt.split())

        # Simple heuristic: lower complexity queries route to local SLM
        if token_estimate < self.complexity_token_threshold and user_tier != "premium":
            return {
                "destination": "local_slm",
                "model": "ollama/llama3.2:3b",
                "reason": "Low complexity, local inference preferred for zero-cost routing",
                "estimated_cost": 0.0,
            }
        else:
            return {
                "destination": "cloud_fortress",
                "model": "gpt-4o-mini",
                "reason": "High complexity query or premium tier, routing to cloud fortress",
                "estimated_cost": 0.0015,
            }


smart_router = SmartRouter()
