# LLM Pulse Gateway

A local-first LLM routing gateway: one endpoint in, one answer out, with a semantic
cache, a local small language model, and a cloud fallback chain that only spends the
key it was explicitly given. A pixel-canvas visualiser shows each hop live.

Everything runs on your machine by default. With no API keys and no Ollama, the
gateway still answers — it labels the reply `status: "simulated"` rather than
pretending a model replied.

---

## What problem it actually solves

| Situation | What happens | What you pay |
|---|---|---|
| Prompt already asked (semantically) | served from the vector cache | 0 model tokens |
| Simple / short prompt | local Ollama model | nothing (your GPU) |
| Complex prompt or `premium` tier | cloud tier | whoever's key is used |
| Caller supplied `byok` | cloud tier bills **the caller**, not you | their quota |
| Nothing reachable | answer labelled `simulated` | nothing |

The ledger (`GET /api/gateway/usage`) is what makes those claims checkable instead of
aspirational — see [Measured behaviour](#measured-behaviour).

---

## Architecture

```
                        ┌──────────────────────── WebSocket /ws/signals
                        │                              (7 event types → pixel canvas)
   POST /api/gateway/chat
        │
        ▼
 ┌──────────────┐  hit   ┌───────────────────┐
 │ Warden Tower │───────▶│ Memory Vault      │  semantic cache: Ollama nomic-embed-text
 │  (router)    │        │ (vector cache)    │  cosine similarity ≥ 0.90
 └──────┬───────┘        └─────────┬─────────┘
        │ miss                     │ stored answer (0 tokens, 0 cost)
        ▼                          │
 ┌──────────────┐                  │
 │ SmartRouter  │  heuristics: prompt length, keywords, tier
 │ (route+cost) │──────────────────┐
 └──────┬───────┘                  │
        │ local                    │ cloud
        ▼                          ▼
 ┌──────────────┐        ┌────────────────────────────────────┐
 │ Model        │        │ Provider cascade                   │
 │ Fortress     │        │ 1. Ollama /api/chat (local, capped)│
 │              │        │ 2. Gemini  (direct HTTP)           │
 │              │        │ 3. DeepSeek (direct HTTP)          │
 │              │        │ 4. LiteLLM: OpenAI → Anthropic →   │
 │              │        │    Groq → xAI → OpenRouter         │
 │              │        │ 5. labelled stand-in ("simulated") │
 └──────┬───────┘        └──────────────────┬─────────────────┘
        │                                   │
        └────────────┬──────────────────────┘
                     ▼
          ┌────────────────────┐     ┌──────────────────────┐
          │ Evaluation engine  │────▶│ Usage ledger (SQLite)│
          │ non_empty          │     │ append-only rows     │
          │ real_model_answered│     └──────────────────────┘
          └────────────────────┘
```

Storage: **Qdrant** for the vector index when reachable; otherwise an in-process
in-memory index with a logged warning — **that cache is lost on restart**.

---

## Request lifecycle

`backend/app/api/gateway.py` runs five steps, broadcasting a `SignalPacket` between each:

1. `CACHE_MISS` / `CACHE_HIT` — semantic lookup
2. `ROUTING_SIGNAL` — chosen destination, model, estimated cost, reason, and the
   complexity breakdown (score, word count, heuristic hits) behind that reason
3. `MODEL_EXECUTION` — cascade attempt
4. `EVALUATION` — pass/fail on the two observable checks
5. `COMPLETION` — latency, model, tokens, status, `truncated`

Every step is also returned inline in the response `signals` array, so a client can
replay a request's path without subscribing to the socket.

---

## Response provenance

`StructuredPulseResponse` never hides where an answer came from:

```json
{
  "response": "...",
  "destination": "local_slm",
  "model": "ollama/gemma4:e2b",
  "provider_used": "local_slm",
  "status": "success",
  "cache_hit": false,
  "tokens_used": 281,
  "latency_ms": 12369.28,
  "cost_usd": 0.0,
  "truncated": true,
  "signals": [ ... ]
}
```

`status` is one of `success`, `cached`, `fallback`, `simulated`, and `attempted`
inside `metadata` records every tier the cascade tried and why each one did not
answer (`skipped: no Gemini key (BYOK or .env)`, `HTTP 401`, `TimeoutException`, ...).

**`cost_usd` is the router's own estimate**, not an invoice: it comes from the route
decision and is `0.0` for local, cached, and simulated answers. Tokens are the real
counts reported by each provider.

---

## Bring your own key (BYOK)

Cloud calls are billed to the key that unlocked them.

```bash
curl -X POST http://localhost:8000/api/gateway/chat \
  -H "Content-Type: application/json" \
  -d '{
        "prompt": "Summarize this quarter's metrics",
        "tier": "premium",
        "byok": { "gemini_api_key": "...", "openai_api_key": "..." }
      }'
```

Rules, enforced in `app/core/credentials.py` and `app/core/providers.py`:

- Keys travel in the **request body**, not the `Authorization` header — no CORS
  preflight and no key in access logs.
- **Resolution order:** request `byok` → operator `.env` → process environment.
- Supported per-request fields: `gemini_api_key`, `deepseek_api_key`,
  `openai_api_key`, `anthropic_api_key`, `groq_api_key`, `xai_api_key`,
  `openrouter_api_key`.
- `metadata.key_source` reports `byok` or `operator` for the tier that answered.
- A key never comes back out. It is absent from the response, from every WS signal,
  from cache entries, and from ledger rows. Providers paste the offending key into
  their own error bodies, so anything that reaches a log is passed through
  `_redact()` first.
- The UI stores keys in `localStorage` only, behind masked inputs, with a Clear
  button. They stay on that machine and are readable by anyone with that browser
  profile — that is stated in the panel, not glossed over.

---

## Usage ledger

`data/usage.sqlite` (gitignored, standard library `sqlite3`, no server, no
dependency). Append-only `usage_events`, one row per request served:

`ts, route, model, status, cache_hit, tokens_used, latency_ms, estimated_cost_usd, key_source`

`GET /api/gateway/usage` aggregates **only what was measured**:

```json
{
  "requests": 4,
  "tokens_used": 580,
  "cache_hits": 1,
  "avg_latency_ms": 21267.98,
  "estimated_cost_usd": 0.0,
  "by_route": {
    "local_slm":    { "requests": 3, "tokens_used": 580, "estimated_cost_usd": 0.0 },
    "memory_vault": { "requests": 1, "tokens_used": 0,   "estimated_cost_usd": 0.0 }
  }
}
```

No prompt text and no key material is ever written. Delete the file to reset.

---

## Answer shape, token budget and truncation

Ollama allocates a KV cache sized by `num_ctx` and generates until the model stops,
which is how a "quick" local answer turns into a 1500-token markdown essay. The gateway
asks for the shape it wants with one system instruction (`ANSWER_STYLE` in
`backend/app/api/gateway.py`): plain prose, no markdown or em dashes, roughly 120 words.
Budgets:

| Setting | Value | Why |
|---|---|---|
| `OLLAMA_NUM_CTX` | 4096 | prompt + answer window; Ollama otherwise reserves the model's full 131k |
| `OLLAMA_NUM_PREDICT` | 256 | bounds generated tokens per answer (~110 words of prose) |
| `think` | `false` (payload) | reasoning models otherwise burn the whole budget on hidden chain-of-thought |
| `OLLAMA_KEEP_ALIVE` | `30m` | a cold reload costs 12–50 s |
| `INFERENCE_TIMEOUT_SECONDS` | 90 | must exceed cold-load + first token |

So a local answer is bounded by 4096 tokens of context with at most 256 generated: a
long pasted file plus a long essay will not fit, and the style instruction exists to
keep the answer inside the 256 instead of cutting it off.

When a reply hits the budget, Ollama reports `done_reason: "length"`, the response
carries **`truncated: true`**, and the answer is **not written to the cache** — a
cut-off reply must never be replayed as if it were complete. A `simulated` stand-in
is not cached either: it is generated from the prompt by code, not answered by a model.

---

## Setup

Requirements: Python 3.11+, Node 18+, and optionally Docker and Ollama.

```bash
pip install -r requirements.txt
cp .env.example .env                      # fill in nothing to stay local

# Optional infrastructure (vector persistence; cache works without it)
docker-compose up -d qdrant

# Local model
ollama serve &                            # or the desktop app
ollama pull gemma2:2b                     # any chat model
ollama pull nomic-embed-text              # embeddings for the semantic cache

# Backend  -> http://localhost:8000  (docs at /docs)
python -m uvicorn backend.main:app --reload --port 8000 --host 127.0.0.1

# Frontend -> port from frontend/package.json
cd frontend && npm install && npm run dev
```

Cloud tiers are opt-in per key: set `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`,
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY` or
`OPENROUTER_API_KEY` in `.env`, or pass `byok` per request. `host_provider_status()`
exposes which providers the host can already reach — as booleans, never key material
(`GET /api/gateway/models`).

## Tests

```bash
python -m pytest
```

The suite is hermetic by construction (`tests/conftest.py`): every cloud credential
variable is unset, the LiteLLM tier is forced unavailable, and the ledger is pointed
at a temporary file, so no test can spend money or annotate the operator's real
records. 45 tests, no network calls.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/gateway/chat` | route, answer, cache, and return provenance |
| `GET` | `/api/gateway/usage` | ledger aggregates |
| `GET` | `/api/gateway/models` | local models pulled + per-provider host key status |
| `WS` | `/ws/signals` | live routing events for the canvas |
| `GET` | `/health` | liveness |

## Measured behaviour

Same prompt (`"Explain semantic caching, vector databases, and LLM routing in detail
with examples."`), model `gemma4:e2b`, warm process:

| Path | Generated tokens | Wall clock |
|---|---|---|
| Ollama direct, uncapped | 1513 (`done_reason: stop`) | 28.0 s |
| Through the gateway, capped at 256 | 281 total incl. prompt, `truncated: true` | 12.4 s |
| Second identical prompt, cache hit | 0 | 2.1 s |
| Capped **and** style-instructed (current) | 189 total incl. prompt, `truncated: false` | 12.5 s |

The last row is today's behaviour, measured on `"how to understand any new language"`:
108 words of plain prose that finishes inside the budget, so the cap no longer cuts the
answer off — the instruction makes the answer small enough to fit.

The capped request additionally pays routing and embedding overhead inside that
12.4 s, so the comparison is conservative. A cold first request in a fresh process
cost 55.9 s and a short one-shot answer cost 14.7 s — model load dominates the first
call, which is why `keep_alive` is raised to 30m.

## Known limits

Stated rather than hidden:

- **No authentication on the gateway itself** and no rate limiting. Anyone who can
  reach `:8000` can route through it and spend whatever key the host has configured.
  Bind to `127.0.0.1` (as above) until that is fixed.
- **Local answers are short by design**: 4096 tokens of context total (prompt included)
  and at most 256 generated, which is about 110 words of prose. Paste a large file and
  ask about it and it will not fit — that route needs a cloud key.
- **Single-turn.** A request carries one `prompt`; there is no conversation memory.
- **No streaming.** The answer arrives as one block after inference finishes.
- **Cost is an estimate** (router-side), tokens are real (provider-reported).
- **In-memory cache does not survive restarts** unless Qdrant is running.
- `estimated_cost_usd` for local and simulated routes is `0.0` because nothing was
  billed, not because a price was computed.

## Layout

```
backend/
  config.py                  pydantic-settings; all knobs come from .env
  main.py                    app, CORS, routers, /health
  app/
    api/gateway.py           the 5-step request pipeline + endpoints
    api/websocket.py         SignalPacket broadcast (/ws/signals)
    core/router.py           SmartRouter heuristics + cost estimate
    core/providers.py        cascade, BYOK resolution, redaction, provenance
    core/cache.py            semantic cache: Qdrant with in-memory fallback
    core/credentials.py      BYOKCredentials
    core/usage.py            SQLite ledger
    features/parser.py       request/response models
    features/evals.py        observable answer checks
frontend/
  src/pages/index.jsx        chat, metrics, BYOK panel, usage ledger
  src/components/pulse/      Canvas 2D pixel world driven by WS signals
  src/lib/pulse/gateway.js   endpoint + formatting single source
tests/                       hermetic suite (see conftest.py)
scripts/blender/             sprite/asset generators for the canvas
```
