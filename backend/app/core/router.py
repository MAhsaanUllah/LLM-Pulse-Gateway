import re
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from config import settings

logger = logging.getLogger(__name__)


# Keywords indicating high reasoning, coding, analysis, or architectural complexity
COMPLEX_INDICATORS = [
    r"\b(code|algorithm|architect|architecture|refactor|debug|compile|regex|stack trace|concurrency|async)\b",
    r"\b(reasoning|proof|math|mathematical|mathematics|calculus|differential|matrix|theorem|hypothesis)\b",
    r"\b(security|vulnerability|exploit|penetration|cryptography|cryptographic|encryption|asymmetric|hash|jwt)\b",
    r"\b(database schema|sql query|nosql|migration|optimization|sharding)\b",
    r"\b(analyze|analysis|critique|synthesize|compare and contrast|multi-step|evaluate)\b",
    r"```[a-zA-Z0-9_-]*\n[\s\S]*?\n```",  # Contains code blocks
]

# Simple greetings and basic conversational keywords
SIMPLE_INDICATORS = [
    r"^(hi|hello|hey|greetings|howdy)\b",
    r"^(what is|define|who is|where is|summarize|translate)\b",
    r"^(tell me a joke|write a poem|spell check)\b",
]


@dataclass
class ComplexityMetrics:
    token_count: int
    char_count: int
    complex_keyword_hits: int
    code_block_count: int
    question_count: int
    complexity_score: float  # Normalized 0.0 (trivial) to 1.0 (extreme complexity)
    is_hard_query: bool
    reasons: List[str] = field(default_factory=list)


class SmartRouter:
    """
    Cost-Aware Smart Router.
    Calculates prompt complexity metrics (length, structure, domain semantics, code snippets)
    to route simple/easy queries to local SLMs (zero marginal cost) and complex/hard queries
    to Cloud Fortress (OpenAI GPT-4o / Anthropic Claude 3.5 Sonnet).
    """

    def __init__(
        self,
        token_threshold: int = 80,
        complexity_score_threshold: float = 0.40,
        default_local_model: Optional[str] = None,
        default_cloud_model: Optional[str] = None,
        premium_cloud_model: str = "claude-3-5-sonnet-20241022",
    ):
        self.token_threshold = token_threshold
        self.complexity_score_threshold = complexity_score_threshold
        self.default_local_model = default_local_model or f"ollama/{settings.OLLAMA_MODEL}"
        self.default_cloud_model = default_cloud_model or settings.DEFAULT_GEMINI_MODEL
        self.premium_cloud_model = premium_cloud_model

        # Pre-compile regexes
        self._complex_patterns = [re.compile(p, re.IGNORECASE) for p in COMPLEX_INDICATORS]
        self._simple_patterns = [re.compile(p, re.IGNORECASE) for p in SIMPLE_INDICATORS]

    def compute_complexity(self, prompt: str) -> ComplexityMetrics:
        """
        Computes multi-dimensional complexity score:
        - Token/Word density
        - Keyword heuristics (reasoning, math, architecture, coding)
        - Syntactic structures (code fences, questions)
        """
        words = prompt.strip().split()
        token_count = len(words)
        char_count = len(prompt)

        # Detect code blocks
        code_blocks = len(re.findall(r"```[\s\S]*?```", prompt))

        # Check complex indicator matches
        complex_hits = 0
        reasons: List[str] = []

        for pattern in self._complex_patterns:
            matches = pattern.findall(prompt)
            if matches:
                complex_hits += len(matches)

        # Check simple pattern hits
        simple_hits = 0
        for pattern in self._simple_patterns:
            if pattern.search(prompt.strip()):
                simple_hits += 1

        question_count = prompt.count("?")

        # Calculate normalized score (0.0 - 1.0)
        # 1. Length factor (weight: 0.30)
        length_factor = min(1.0, token_count / 100.0)

        # 2. Semantic indicator factor (weight: 0.50)
        semantic_factor = min(1.0, complex_hits * 0.35)

        # 3. Structure factor: code blocks and dense formatting (weight: 0.20)
        structure_factor = min(1.0, (code_blocks * 0.6) + (min(3, question_count) * 0.15))

        base_score = (length_factor * 0.30) + (semantic_factor * 0.50) + (structure_factor * 0.20)

        # Simple pattern dampening
        if simple_hits > 0 and token_count < 20 and code_blocks == 0 and complex_hits == 0:
            base_score = max(0.05, base_score * 0.4)
            reasons.append("Matched common conversational/direct query pattern")

        if token_count >= self.token_threshold:
            reasons.append(f"Prompt length ({token_count} words) exceeds threshold ({self.token_threshold})")

        if complex_hits > 0:
            reasons.append(f"Detected {complex_hits} high-complexity domain indicator(s)")

        if code_blocks > 0:
            reasons.append(f"Contains {code_blocks} embedded code block(s)")

        complexity_score = round(min(1.0, max(0.0, base_score)), 3)
        # Any query with 2+ domain indicators, or meeting score/length threshold, is a hard query
        is_hard = complexity_score >= self.complexity_score_threshold or token_count >= self.token_threshold or complex_hits >= 2 or code_blocks > 0

        return ComplexityMetrics(
            token_count=token_count,
            char_count=char_count,
            complex_keyword_hits=complex_hits,
            code_block_count=code_blocks,
            question_count=question_count,
            complexity_score=complexity_score,
            is_hard_query=is_hard,
            reasons=reasons,
        )

    def evaluate_route(self, prompt: str, user_tier: str = "standard") -> Dict[str, Any]:
        """
        Determines optimal destination provider, model, and cost budget based on complexity metrics.
        - Easy / low-complexity -> Local SLM (Ollama, $0 cost)
        - Hard / high-complexity -> Cloud Fortress (OpenAI / Claude)
        """
        metrics = self.compute_complexity(prompt)

        # Premium tier override for power users
        if user_tier == "premium" and metrics.is_hard_query:
            target_destination = "cloud_fortress"
            target_model = self.premium_cloud_model
            estimated_cost = 0.0060
            decision_reason = "Premium tier requesting complex inference -> Claude 3.5 Sonnet Fortress"
        elif metrics.is_hard_query:
            target_destination = "cloud_fortress"
            target_model = self.default_cloud_model
            estimated_cost = 0.0015
            decision_reason = f"Hard query (complexity={metrics.complexity_score}) -> Cloud Fortress ({self.default_cloud_model})"
        else:
            target_destination = "local_slm"
            target_model = self.default_local_model
            estimated_cost = 0.0
            decision_reason = f"Easy query (complexity={metrics.complexity_score}) -> Local SLM ({self.default_local_model})"

        return {
            "destination": target_destination,
            "model": target_model,
            "reason": decision_reason,
            "estimated_cost": estimated_cost,
            "complexity_metrics": {
                "score": metrics.complexity_score,
                "is_hard": metrics.is_hard_query,
                "token_count": metrics.token_count,
                "reasons": metrics.reasons,
            },
        }


smart_router = SmartRouter()
