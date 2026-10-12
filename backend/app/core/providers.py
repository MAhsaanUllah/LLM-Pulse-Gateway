import os
import sys
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import httpx

from config import settings
from app.core.credentials import BYOKCredentials

logger = logging.getLogger(__name__)

# Optional LiteLLM import
try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    litellm = None  # type: ignore
    LITELLM_AVAILABLE = False


# Bare model names LiteLLM cannot route without a provider prefix.
LITELLM_PROVIDER_PREFIXES = {
    "gpt-": "openai/",
    "text-": "openai/",
    "o1": "openai/",
    "o3": "openai/",
    "claude": "anthropic/",
    "gemini": "gemini/",
}


@dataclass
class CompletionResult:
    content: str
    model_used: str
    provider: str
    status: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    fallback_triggered: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProviderManager:
    """
    Production-Grade LLM Provider Orchestrator for LLM Pulse Gateway.
    
    Supports:
    1. Local SLM (Ollama) on localhost:11434
    2. Google Gemini (Native HTTPX + LiteLLM support with GEMINI_API_KEY / GOOGLE_API_KEY)
    3. DeepSeek (native HTTPX with DEEPSEEK_API_KEY)
    4. Cloud Fortress (OpenAI GPT-4o, Anthropic Claude 3.5 Sonnet via LiteLLM)
    5. Resilient Fallback: If Ollama is offline or uninstalled, automatically shifts
       traffic to a cloud tier or the simulated engine without crashing with 500 errors.
    """

    def __init__(
        self,
        ollama_base_url: Optional[str] = None,
        primary_slm_model: Optional[str] = None,
        default_gemini_model: Optional[str] = None,
        cloud_fallback_model: str = "gpt-4o-mini",
        claude_fallback_model: str = "claude-3-5-sonnet-20241022",
    ):
        self.ollama_base_url = ollama_base_url or settings.OLLAMA_BASE_URL
        self.primary_slm_model = primary_slm_model or f"ollama/{settings.OLLAMA_MODEL}"
        self.default_gemini_model = default_gemini_model or settings.DEFAULT_GEMINI_MODEL
        self.cloud_fallback_model = cloud_fallback_model
        self.claude_fallback_model = claude_fallback_model

    @staticmethod
    def _redact(text: str, secret: Optional[str]) -> str:
        """Providers echo the offending key back in their error bodies, so nothing
        that reaches the log may still contain it."""
        if secret:
            text = text.replace(secret, "***redacted-key***")
        return text[:200]

    def get_gemini_key(self, byok: Optional[BYOKCredentials] = None) -> Optional[str]:
        """The caller's own key pays for the call, so it wins over the operator's key."""
        if byok and byok.gemini_api_key:
            return byok.gemini_api_key
        return (
            settings.GEMINI_API_KEY
            or settings.GOOGLE_API_KEY
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )

    async def _call_gemini_direct(
        self,
        messages: List[Dict[str, str]],
        model_name: str,
        byok: Optional[BYOKCredentials] = None,
    ) -> Optional[Dict[str, Any]]:
        """Direct zero-dependency Google Gemini REST API caller via HTTPX."""
        api_key = self.get_gemini_key(byok)
        if not api_key:
            return None

        # Clean model name (strip "gemini/" or "google/" prefix if present)
        clean_model = model_name.replace("gemini/", "").replace("google/", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent"

        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1024,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=settings.INFERENCE_TIMEOUT_SECONDS) as client:
                res = await client.post(url, json=payload, headers={"x-goog-api-key": api_key})
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        text = "".join(p.get("text", "") for p in parts)
                        usage = data.get("usageMetadata", {})
                        return {
                            "content": text,
                            "tokens": usage.get("totalTokenCount", 0),
                            "model": f"gemini/{clean_model}",
                        }
                else:
                    logger.warning(
                        "[Gemini Direct] API returned %s: %s",
                        res.status_code,
                        self._redact(res.text, api_key),
                    )
                    return {"error": f"HTTP {res.status_code}"}
        except Exception as exc:
            logger.warning("[Gemini Direct] Request failed: %s", exc)
            return {"error": type(exc).__name__}

        return None

    def get_deepseek_key(self, byok: Optional[BYOKCredentials] = None) -> Optional[str]:
        if byok and byok.deepseek_api_key:
            return byok.deepseek_api_key
        return settings.DEEPSEEK_API_KEY or os.environ.get("DEEPSEEK_API_KEY")

    async def _call_deepseek_direct(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        byok: Optional[BYOKCredentials] = None,
    ) -> Optional[Dict[str, Any]]:
        """Direct zero-dependency DeepSeek caller (OpenAI-compatible schema, own key)."""
        api_key = self.get_deepseek_key(byok)
        if not api_key:
            return None

        clean_model = (model_name or settings.DEFAULT_DEEPSEEK_MODEL).replace("deepseek/", "")
        url = f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"

        payload = {
            "model": clean_model,
            "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
            "temperature": 0.7,
            "max_tokens": 1024,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.INFERENCE_TIMEOUT_SECONDS) as client:
                res = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    content = choices[0].get("message", {}).get("content", "") if choices else ""
                    if not content.strip():
                        logger.warning(
                            "[DeepSeek Direct] '%s' answered with empty content — treating as a miss",
                            clean_model,
                        )
                        return None
                    usage = data.get("usage", {})
                    return {
                        "content": content,
                        "tokens": usage.get("total_tokens", 0),
                        "model": f"deepseek/{clean_model}",
                    }
                logger.warning(
                    "[DeepSeek Direct] API returned %s: %s",
                    res.status_code,
                    self._redact(res.text, api_key),
                )
                return {"error": f"HTTP {res.status_code}"}
        except Exception as exc:
            logger.warning("[DeepSeek Direct] Request failed: %s", exc)
            return {"error": type(exc).__name__}

        return None

    async def _call_ollama_direct(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Direct Ollama HTTP caller on localhost:11434."""
        clean_model = (model_name or settings.OLLAMA_MODEL).replace("ollama/", "")
        url = f"{self.ollama_base_url.rstrip('/')}/api/chat"

        payload = {
            "model": clean_model,
            "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
            "stream": False,
            # Reasoning models burn the whole budget on hidden chain-of-thought before
            # answering, which is unusable on a CPU-only host (~6 tok/s).
            "think": False,
            "options": {"num_ctx": settings.OLLAMA_NUM_CTX},
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.INFERENCE_TIMEOUT_SECONDS) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("message", {}).get("content", "")
                    if not content.strip():
                        logger.warning(
                            "[Ollama Direct] '%s' answered with empty content — treating as a miss",
                            clean_model,
                        )
                        return None
                    prompt_eval = data.get("prompt_eval_count", 0)
                    eval_count = data.get("eval_count", 0)
                    return {
                        "content": content,
                        "tokens": prompt_eval + eval_count,
                        "model": f"ollama/{clean_model}",
                    }
                logger.warning(
                    "[Ollama Direct] %s rejected model '%s' (HTTP %s): %s",
                    url, clean_model, res.status_code, res.text[:200],
                )
        except httpx.TimeoutException as exc:
            logger.warning(
                "[Ollama Direct] No answer for '%s' within %ss — the model may still be "
                "loading into memory (%s)", clean_model, settings.INFERENCE_TIMEOUT_SECONDS, exc
            )
        except httpx.HTTPError as exc:
            logger.warning("[Ollama Direct] Service unreachable on %s (%s)", self.ollama_base_url, exc)

        return None

    @staticmethod
    def _as_litellm_model(name: str) -> str:
        """LiteLLM routes by provider prefix, so bare model names are rejected."""
        if "/" in name:
            return name
        lowered = name.lower()
        for fragment, prefix in LITELLM_PROVIDER_PREFIXES.items():
            if lowered.startswith(fragment):
                return f"{prefix}{name}"
        return name

    def _litellm_candidates(self, requested_model: str) -> List[str]:
        """Requested model first (so premium actually reaches Claude), then the fallbacks."""
        candidates = [requested_model, self.cloud_fallback_model, self.claude_fallback_model]
        ordered: List[str] = []
        for candidate in candidates:
            normalised = self._as_litellm_model(candidate)
            if normalised.startswith("ollama/") or normalised in ordered:
                continue
            ordered.append(normalised)
        return ordered

    async def execute_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        allow_fallback: bool = True,
        byok: Optional[BYOKCredentials] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Executes completion with resilient cascading fallback:
        1. Target model (e.g. Local SLM via Ollama)
        2. Google Gemini (caller's BYOK key, else GEMINI_API_KEY)
        3. DeepSeek (caller's BYOK key, else DEEPSEEK_API_KEY)
        4. Cloud Fortress (OpenAI / Claude via LiteLLM)
        5. Intelligent Stand-In Simulation (Zero Crash Guarantee)
        """
        user_prompt = messages[-1].get("content", "") if messages else ""
        is_local_target = model.startswith("ollama") or "llama" in model.lower()
        attempted: List[Dict[str, str]] = []

        # -------------------------------------------------------------
        # 1. ATTEMPT LOCAL SLM (OLLAMA) IF REQUESTED
        # -------------------------------------------------------------
        if is_local_target:
            logger.info(f"[ProviderManager] Attempting Local SLM: {model}")
            ollama_result = await self._call_ollama_direct(messages, model)
            if ollama_result:
                return {
                    "content": ollama_result["content"],
                    "model_used": ollama_result["model"],
                    "provider": "local_slm",
                    "status": "success",
                    "fallback_triggered": False,
                    "tokens_used": ollama_result["tokens"],
                    "metadata": {"source": "ollama_native", "attempted": attempted},
                }
            attempted.append({"tier": "local_slm", "outcome": f"no answer from {self.ollama_base_url}"})
            logger.warning(
                f"[ProviderManager] Local Ollama did not answer on {self.ollama_base_url}. "
                "Triggering automated fallback to Gemini / Cloud Fortress..."
            )

        # -------------------------------------------------------------
        # 2. ATTEMPT GEMINI (FAST & COST-EFFECTIVE CLOUD ALTERNATIVE)
        # -------------------------------------------------------------
        gemini_key = self.get_gemini_key(byok)
        if gemini_key:
            logger.info("[ProviderManager] Dispatching to Google Gemini...")
            gemini_result = await self._call_gemini_direct(messages, self.default_gemini_model, byok)
            if gemini_result and gemini_result.get("content"):
                return {
                    "content": gemini_result["content"],
                    "model_used": gemini_result["model"],
                    "provider": "cloud_fortress",
                    "status": "fallback" if is_local_target else "success",
                    "fallback_triggered": is_local_target,
                    "tokens_used": gemini_result["tokens"],
                    "metadata": {
                        "source": "gemini_direct",
                        "key_source": "byok" if byok and byok.gemini_api_key else "operator",
                        "attempted": attempted,
                        "fallback_reason": "Local SLM unavailable, served via Google Gemini"
                        if is_local_target
                        else "Direct Gemini",
                    },
                }
            attempted.append({
                "tier": "gemini",
                "outcome": f"{self.default_gemini_model}: "
                + (gemini_result["error"] if gemini_result else "no answer"),
            })
        else:
            attempted.append({"tier": "gemini", "outcome": "skipped: no Gemini key (BYOK or .env)"})

        # -------------------------------------------------------------
        # 3. ATTEMPT DEEPSEEK (DIRECT, NO LITELLM KEY AMBIGUITY)
        # -------------------------------------------------------------
        deepseek_key = self.get_deepseek_key(byok)
        if deepseek_key:
            logger.info("[ProviderManager] Dispatching to DeepSeek...")
            deepseek_result = await self._call_deepseek_direct(messages, byok=byok)
            if deepseek_result and deepseek_result.get("content"):
                return {
                    "content": deepseek_result["content"],
                    "model_used": deepseek_result["model"],
                    "provider": "cloud_fortress",
                    "status": "fallback" if is_local_target else "success",
                    "fallback_triggered": is_local_target,
                    "tokens_used": deepseek_result["tokens"],
                    "metadata": {
                        "source": "deepseek_direct",
                        "key_source": "byok" if byok and byok.deepseek_api_key else "operator",
                        "attempted": attempted,
                        "fallback_reason": "Local SLM unavailable, served via DeepSeek"
                        if is_local_target
                        else "Direct DeepSeek",
                    },
                }
            attempted.append({
                "tier": "deepseek",
                "outcome": f"{settings.DEFAULT_DEEPSEEK_MODEL}: "
                + (deepseek_result["error"] if deepseek_result else "no answer"),
            })
        else:
            attempted.append({"tier": "deepseek", "outcome": "skipped: no DeepSeek key (BYOK or .env)"})

        # -------------------------------------------------------------
        # 4. ATTEMPT LITELLM CLOUD FORTRESS (OPENAI / ANTHROPIC)
        # -------------------------------------------------------------
        if LITELLM_AVAILABLE and litellm is not None:
            for cloud_candidate in self._litellm_candidates(model):
                try:
                    logger.info(f"[ProviderManager] Attempting LiteLLM: {cloud_candidate}")
                    res = await litellm.acompletion(
                        model=cloud_candidate,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs,
                    )
                    content = res.choices[0].message.content
                    usage = getattr(res, "usage", None)
                    return {
                        "content": content,
                        "model_used": cloud_candidate,
                        "provider": "cloud_fortress",
                        "status": "fallback" if is_local_target else "success",
                        "fallback_triggered": is_local_target,
                        "tokens_used": usage.total_tokens if usage else 0,
                        "metadata": {
                            "source": "litellm_cloud",
                            "attempted": attempted,
                            "tokens_estimated": usage is None,
                        },
                    }
                except Exception as exc:
                    logger.warning(f"[ProviderManager] Cloud fallback '{cloud_candidate}' failed: {exc}")
                    attempted.append({"tier": "litellm", "outcome": f"{cloud_candidate}: {type(exc).__name__}"})
        else:
            attempted.append({"tier": "litellm", "outcome": "skipped: litellm not installed"})

        # -------------------------------------------------------------
        # 4. ZERO-CRASH RESILIENT SIMULATION ENGINE
        # -------------------------------------------------------------
        logger.info("[ProviderManager] Engaging resilient gateway simulation engine.")
        cascade = "; ".join(f"{a['tier']} -> {a['outcome']}" for a in attempted) or "no tier was reachable"
        simulated_response = (
            f"⚠️ [LLM Pulse Gateway — SIMULATED: no model answered]\n\n"
            f"Your prompt: {user_prompt}\n\n"
            f"Cascade: {cascade}\n\n"
            f"Start Ollama (`ollama serve`) or set GEMINI_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY in `.env`."
        )

        return {
            "content": simulated_response,
            "model_used": f"{model} (stand-in)",
            "provider": "none",
            "status": "simulated",
            "fallback_triggered": True,
            "tokens_used": 0,
            "metadata": {
                "source": "stand_in",
                "attempted": attempted,
                "recommended_action": "start_ollama_or_set_api_key",
            },
        }


provider_manager = ProviderManager()
