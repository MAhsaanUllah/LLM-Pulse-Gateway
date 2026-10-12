from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class EvaluationEngine:
    """
    Screens an answer for the failures this gateway can actually observe.

    RAGAS-style faithfulness needs retrieved context chunks to compare against, and
    this gateway has none, so no such score is reported.
    """

    async def evaluate(self, response: str, provider_status: str) -> Dict[str, Any]:
        non_empty = bool(response.strip())
        real_model_answered = provider_status != "simulated"
        result = {
            "passed": non_empty and real_model_answered,
            "checks": {
                "non_empty": non_empty,
                "real_model_answered": real_model_answered,
            },
        }
        logger.info(f"Evaluation verdict: {result}")
        return result


eval_engine = EvaluationEngine()
