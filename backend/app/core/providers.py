import json
import logging
from typing import Dict, Any, List, Optional
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


# Cloud providers reachable through LiteLLM. The provider matching the routed
# model is tried first; the rest follow in this order as fallbacks.
CLOUD_PROVIDERS = [
    {"name": "openai", "prefix": "openai/", "model_setting": "DEFAULT_OPENAI_MODEL",
     "key_setting": "OPENAI_API_KEY", "key_field": "openai_api_key"},
    {"name": "anthropic", "prefix": "anthropic/", "model_setting": "DEFAULT_ANTHROPIC_MODEL",
     "key_setting": "ANTHROPIC_API_KEY", "key_field": "anthropic_api_key"},
    {"name": "groq", "prefix": "groq/", "model_setting": "DEFAULT_GROQ_MODEL",
     "key_setting": "GROQ_API_KEY", "key_field": "groq_api_key"},
    {"name": "xai", "prefix": "xai/", "model_setting": "DEFAULT_XAI_MODEL",
     "key_setting": "XAI_API_KEY", "key_field": "xai_api_key"},
    {"name": "openrouter", "prefix": "openrouter/", "model_setting": "DEFAULT_OPENROUTER_MODEL",
     "key_setting": "OPENROUTER_API_KEY", "key_field": "openrouter_api_key"},
]


class ProviderManager:
    """
    LLM provider orchestrator: cascades one request through every tier that can
    actually answer it, in order of cost.

    1. Local SLM through Ollama (zero marginal cost)
    2. Google Gemini (native HTTPX)
    3. DeepSeek (native HTTPX)
    4. Cloud providers through LiteLLM (OpenAI / Anthropic / Groq / xAI / OpenRouter)
    5. A labelled stand-in, so the gateway answers with provenance instead of a 500

    Tiers 2-4 use the caller's own key when the request carries one, else the
    operator's key from `.env`; a tier with no key is skipped, not failed.
    """

    def __init__(
        self,
        ollama_base_url: Optional[str] = None,
        default_gemini_model: Optional[str] = None,
    ):
        self.ollama_base_url = ollama_base_url or settings.OLLAMA_BASE_URL
        self.default_gemini_model = default_gemini_model or settings.DEFAULT_GEMINI_MODEL

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
        return settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY

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
        return settings.DEEPSEEK_API_KEY

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
            "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "num_predict": settings.OLLAMA_NUM_PREDICT},
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
                        "truncated": data.get("done_reason") == "length",
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

    def _resolve_provider_key(self, entry: Dict[str, str], byok: Optional[BYOKCredentials]):
        """BYOK wins over the operator's key: returns (key, 'byok'|'operator'|None)."""
        if byok is not None:
            own = getattr(byok, entry["key_field"], None)
            if own:
                return own, "byok"
        host = getattr(settings, entry["key_setting"], None)
        if host:
            return host, "operator"
        return None, None

    @staticmethod
    def _provider_for_model(model: str) -> Optional[str]:
        m = (model or "").lower()
        if m.startswith(("gpt", "o1", "o3", "text-")):
            return "openai"
        if "claude" in m:
            return "anthropic"
        if "grok" in m:
            return "xai"
        if m.startswith("groq/"):
            return "groq"
        if m.startswith("openrouter/"):
            return "openrouter"
        return None

    def _cloud_candidates(self, requested_model: str, byok: Optional[BYOKCredentials]) -> List[Dict[str, Any]]:
        """Cloud providers that actually have a key, with the routed model's provider first."""
        preferred = self._provider_for_model(requested_model)
        ordered = sorted(CLOUD_PROVIDERS, key=lambda e: 0 if e["name"] == preferred else 1)
        candidates: List[Dict[str, Any]] = []
        for entry in ordered:
            key, source = self._resolve_provider_key(entry, byok)
            if not key:
                continue
            model = getattr(settings, entry["model_setting"], entry["prefix"])
            candidates.append({
                "name": entry["name"],
                "model": f"{entry['prefix']}{model}",
                "api_key": key,
                "key_source": source,
            })
        return candidates

    def host_provider_status(self) -> List[Dict[str, Any]]:
        """Which providers the operator's own environment can already reach."""
        statuses = [
            {
                "provider": entry["name"],
                "env_var": entry["key_setting"],
                "host_key_configured": bool(self._resolve_provider_key(entry, None)[0]),
            }
            for entry in CLOUD_PROVIDERS
        ]
        statuses.append({
            "provider": "gemini",
            "env_var": "GEMINI_API_KEY",
            "host_key_configured": bool(self.get_gemini_key()),
        })
        statuses.append({
            "provider": "deepseek",
            "env_var": "DEEPSEEK_API_KEY",
            "host_key_configured": bool(self.get_deepseek_key()),
        })
        return statuses

    async def list_local_models(self) -> Dict[str, Any]:
        """Ask the local Ollama daemon which models it has pulled."""
        url = f"{self.ollama_base_url.rstrip('/')}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    models = [
                        {"name": m.get("name"), "size": m.get("size")}
                        for m in data.get("models", [])
                        if m.get("name")
                    ]
                    return {"available": True, "base_url": self.ollama_base_url, "models": models}
        except Exception as exc:
            logger.info("[ProviderManager] Local model detection failed on %s: %s", url, exc)
        return {"available": False, "base_url": self.ollama_base_url, "models": []}

    async def _stream_ollama(
        self,
        messages: List[Dict[str, str]],
        model_name: str,
        summary: Dict[str, Any],
    ):
        """Yield answer pieces from the local daemon and record the totals in `summary`.

        Ollama answers NDJSON: one object per token run, the last one carrying
        `done_reason` and the real token counts.
        """
        clean_model = model_name.replace("ollama/", "")
        url = f"{self.ollama_base_url.rstrip('/')}/api/chat"
        payload = {
            "model": clean_model,
            "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
            "stream": True,
            "think": False,
            "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "num_predict": settings.OLLAMA_NUM_PREDICT},
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }
        pieces: List[str] = []
        done: Dict[str, Any] = {}
        summary["answered"] = False
        try:
            async with httpx.AsyncClient(timeout=settings.INFERENCE_TIMEOUT_SECONDS) as client:
                async with client.stream("POST", url, json=payload) as res:
                    if res.status_code != 200:
                        body = (await res.aread()).decode(errors="replace")
                        logger.warning(
                            "[Ollama Stream] %s rejected model '%s' (HTTP %s): %s",
                            url, clean_model, res.status_code, body[:200],
                        )
                        return
                    async for line in res.aiter_lines():
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        piece = (event.get("message") or {}).get("content") or ""
                        if piece:
                            pieces.append(piece)
                            yield piece
                        if event.get("done"):
                            done = event
        except httpx.HTTPError as exc:
            logger.warning("[Ollama Stream] Service failed on %s (%s)", self.ollama_base_url, exc)
            return

        content = "".join(pieces)
        if not content.strip():
            logger.warning("[Ollama Stream] '%s' streamed no content — treating as a miss", clean_model)
            return
        summary.update({
            "content": content,
            "model": f"ollama/{clean_model}",
            "tokens": int(done.get("prompt_eval_count", 0)) + int(done.get("eval_count", 0)),
            "truncated": done.get("done_reason") == "length",
            "answered": True,
        })

    async def stream_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        byok: Optional[BYOKCredentials] = None,
        local_only: bool = False,
    ):
        """Yield `{'kind': 'delta', 'text': ...}` pieces, then one
        `{'kind': 'final', ...}` record shaped like execute_completion's.

        Only the local daemon streams token by token; every other tier answers as one
        block, so its caller sees a single delta.
        ponytail: per-provider cloud streaming needs astream calls — worth adding when
        a cloud tier becomes the usual route, not while local answers the simple ones.
        """
        streamed: List[str] = []
        if model.startswith("ollama"):
            summary: Dict[str, Any] = {}
            async for piece in self._stream_ollama(messages, model, summary):
                streamed.append(piece)
                yield {"kind": "delta", "text": piece}
            if summary.get("answered"):
                yield {
                    "kind": "final",
                    "content": summary["content"],
                    "model_used": summary["model"],
                    "provider": "local_slm",
                    "status": "success",
                    "fallback_triggered": False,
                    "tokens_used": summary["tokens"],
                    "truncated": summary["truncated"],
                    "metadata": {"source": "ollama_native_stream", "attempted": []},
                }
                return
            if streamed:
                # The daemon started answering and stopped mid-stream. Re-asking would
                # replay text the caller already has, so report what actually arrived.
                yield {
                    "kind": "final",
                    "content": "".join(streamed),
                    "model_used": f"ollama/{model.replace('ollama/', '')}",
                    "provider": "local_slm",
                    "status": "success",
                    "fallback_triggered": False,
                    "tokens_used": 0,
                    "truncated": True,
                    "metadata": {"source": "ollama_native_stream_incomplete", "attempted": []},
                }
                return

        result = await self.execute_completion(model=model, messages=messages, byok=byok, local_only=local_only)
        yield {"kind": "delta", "text": result["content"]}
        yield {"kind": "final", **result}

    def _simulate(
        self,
        model: str,
        user_prompt: str,
        attempted: List[Dict[str, str]],
        fallback_triggered: bool,
    ) -> Dict[str, Any]:
        """The labelled stand-in: provenance instead of a 500 when no tier answers."""
        logger.info("[ProviderManager] Engaging resilient gateway simulation engine.")
        cascade = "; ".join(f"{a['tier']} -> {a['outcome']}" for a in attempted) or "no tier was reachable"
        # The prompt can be a pasted file or retrieved document chunks: echo the opening
        # lines so the caller recognises the request, never the whole thing.
        echoed = user_prompt if len(user_prompt) <= 240 else f"{user_prompt[:240].rstrip()}…"
        simulated_response = (
            f"⚠️ [LLM Pulse Gateway — SIMULATED: no model answered]\n\n"
            f"Your prompt: {echoed}\n\n"
            f"Cascade: {cascade}\n\n"
            f"Start Ollama (`ollama serve`), send `byok` with the request, or set a host key in `.env`: "
            f"GEMINI_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, "
            f"XAI_API_KEY or OPENROUTER_API_KEY."
        )
        return {
            "content": simulated_response,
            "model_used": f"{model} (stand-in)",
            "provider": "none",
            "status": "simulated",
            "fallback_triggered": fallback_triggered,
            "tokens_used": 0,
            "metadata": {
                "source": "stand_in",
                "attempted": attempted,
                "recommended_action": "start_ollama_or_set_api_key",
            },
        }

    async def execute_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        byok: Optional[BYOKCredentials] = None,
        local_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Runs the cascade in the class docstring and returns the first tier that
        answers, always with provenance: which model served it, whether it was a
        fallback, and what every skipped tier was skipped for.
        """
        user_prompt = messages[-1].get("content", "") if messages else ""
        is_local_target = model.startswith("ollama")
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
                    "truncated": ollama_result["truncated"],
                    "metadata": {"source": "ollama_native", "attempted": attempted},
                }
            attempted.append({"tier": "local_slm", "outcome": f"no answer from {self.ollama_base_url}"})
            logger.warning(
                f"[ProviderManager] Local Ollama did not answer on {self.ollama_base_url}. "
                "Triggering automated fallback to Gemini / Cloud Fortress..."
            )

        if local_only:
            # Retrieved document chunks ride in these messages. The privacy gate
            # forbids handing them to a cloud provider as a "fallback", so the
            # labelled stand-in answers instead.
            attempted.append({"tier": "cloud", "outcome": "skipped: privacy gate keeps document context local"})
            return self._simulate(model, user_prompt, attempted, is_local_target)

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
        # 4. ATTEMPT CLOUD PROVIDERS VIA LITELLM (OPENAI / ANTHROPIC /
        #    GROQ / xAI GROK / OPENROUTER) USING BYOK OR HOST KEYS
        # -------------------------------------------------------------
        if LITELLM_AVAILABLE and litellm is not None:
            for candidate in self._cloud_candidates(model, byok):
                try:
                    logger.info("[ProviderManager] Attempting %s via LiteLLM: %s", candidate["name"], candidate["model"])
                    res = await litellm.acompletion(
                        model=candidate["model"],
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1024,
                        api_key=candidate["api_key"],
                    )
                    content = res.choices[0].message.content
                    usage = getattr(res, "usage", None)
                    return {
                        "content": content,
                        "model_used": candidate["model"],
                        "provider": candidate["name"],
                        "status": "fallback" if is_local_target else "success",
                        "fallback_triggered": is_local_target,
                        "tokens_used": usage.total_tokens if usage else 0,
                        "metadata": {
                            "source": "litellm_cloud",
                            "provider": candidate["name"],
                            "key_source": candidate["key_source"],
                            "attempted": attempted,
                            "tokens_estimated": usage is None,
                        },
                    }
                except Exception as exc:
                    # LiteLLM puts the api_key it was handed into its exception text.
                    logger.warning(
                        "[ProviderManager] Cloud provider '%s' failed: %s",
                        candidate["name"], self._redact(str(exc), candidate["api_key"]),
                    )
                    attempted.append({"tier": candidate["name"], "outcome": type(exc).__name__})
        else:
            attempted.append({"tier": "litellm", "outcome": "skipped: litellm not installed"})

        # -------------------------------------------------------------
        # 5. ZERO-CRASH RESILIENT SIMULATION ENGINE
        # -------------------------------------------------------------
        return self._simulate(model, user_prompt, attempted, is_local_target)


provider_manager = ProviderManager()
