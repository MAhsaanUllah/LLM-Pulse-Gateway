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

Storage: **Qdrant** for the vector index when reachable; otherwise the same cosine
index runs in-process and writes itself to `CACHE_FILE_PATH`
(`data/semantic_cache.json`) on every save, so cached answers survive a restart
without Docker.

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
replay a request's path without subscribing to the socket. `POST /api/gateway/chat/stream`
runs the same lifecycle and delivers it as Server-Sent Events instead of one block.

---

## Gates: access token and rate limit

Both are open by default, because a local demo should not need a token to start. Set
them in `.env` before the port means anything.

| Setting | Effect |
|---|---|
| `GATEWAY_TOKEN` | every route then demands `Authorization: Bearer <token>`; `/ws/signals` carries it as `?token=<token>` because a browser socket cannot set a header |
| `RATE_LIMIT_PER_MINUTE` | per-client sliding window; over it returns `429` with a `retry-after` header. `0` disables |

Order matters and is deliberate: an unauthenticated request is refused with `401`
before the limiter counts it, so guessing a token cannot consume a caller's window.
The UI says which refusal happened ("The gateway needs its access token…" vs "Too many
requests…") and keeps the token in `localStorage` next to the BYOK keys.

Bind to `127.0.0.1` until you have set a token. Without one, anyone who can reach the
port spends the keys in your `.env`.

---

## Conversation memory

`GatewayRequest.history` carries prior turns (`{role: "user" \| "assistant", content}`),
so a follow-up like "and in one word?" is answerable. The last `MAX_HISTORY_TURNS` (12)
turns are forwarded between the system instruction and the new prompt.

While a conversation is in progress the semantic cache is **bypassed in both
directions** — it stores answers to standalone prompts, and replaying one for a
context-dependent follow-up would be wrong. A turn in progress is therefore never
written to it either.

---

## Streaming

`POST /api/gateway/chat/stream` answers with `text/event-stream` frames:

```
event: signal   # CACHE_MISS / ROUTING_SIGNAL / MODEL_EXECUTION / EVALUATION / COMPLETION
event: delta    # {"text": "..."} per piece, as the model writes it
event: done     # the whole StructuredPulseResponse, same fields as the block route
event: error    # {"detail": "..."} if the gateway stops mid-answer
```

The local tier streams from Ollama's native `stream: true`, so the first piece arrives
while the rest is still being generated. A cached answer is one `delta` plus `done`.
Cloud tiers are currently delivered as one piece — see [Known limits](#known-limits).

The ledger and the cache see the *finished* answer: one row per request, one entry per
complete reply, and a stream cut off by the token budget is flagged and never cached.

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
  "key_source": null,
  "truncated": true,
  "signals": [ ... ]
}
```

`status` is one of `success`, `cached`, `fallback`, `simulated`, and `attempted`
inside `metadata` records every tier the cascade tried and why each one did not
answer (`skipped: no Gemini key (BYOK or .env)`, `HTTP 401`, `TimeoutException`, ...).

**`key_source` says whose credential the tier that answered used** — `"byok"` when the
caller's request body carried the key, `"operator"` when the host's `.env`/environment
key did, and `null` when no cloud credential was involved (local Ollama, cache hit,
stand-in). The UI labels an answer "Your key" or "Host key" from exactly this field.

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

## Cache lifetime and clearing

Each entry stores the `stored_at` it was written at. `CACHE_TTL_SECONDS` (default 86400)
turns a lookup on an older entry into a miss, so the model is re-asked rather than the
answer being replayed forever; `0` means entries never expire. A stale entry is still
keyed by its prompt, so the next answer to that prompt overwrites it.

To wipe the cache without deleting files by hand:

```bash
curl -X POST http://localhost:8000/api/gateway/cache/clear
# { "status": "cleared", "cache_backend": "qdrant:semantic_cache" }
# or, on the fallback index: { "status": "cleared", "cache_backend": "in-memory(7 entries)" }
```

It answers with which backend was cleared, and is behind the same token gate as the
rest of the API.

---

## Setup

Requirements: Python 3.11+, Node 18+, and optionally Docker and Ollama.

```bash
pip install -r requirements.txt
cp .env.example .env                      # fill in nothing to stay local

# Optional infrastructure (vector persistence; cache works without it).
# Needs the Docker engine running, not just the CLI installed.
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

### The whole stack from compose

The same backend also ships as a container, so the full topology — gateway, Qdrant,
TLS proxy, metrics scraper — comes up as one unit. The operator's native `:8000`
process is untouched; the containerized copy listens on loopback only:

```bash
docker compose up -d            # qdrant + gateway(:8010) + caddy(:8443) + prometheus(:9090)
GW=http://127.0.0.1:8010 ./scripts/demo.sh
```

Inside the container Ollama is reached at `host.docker.internal:11434`, because the
model belongs to the host GPU; dockerizing the model itself would give up the GPU for
no gain. Caddy terminates TLS with a self-signed internal certificate, so:

```bash
curl -sk https://localhost:8443/health        # through TLS, with security headers
curl -s  http://127.0.0.1:8010/health         # direct, for comparison
curl -s  http://127.0.0.1:9090/api/v1/targets # Prometheus shows the gateway target UP
```

Measured on the compose stack: the first prompt through `:8010` answered `local_slm`
in 2.6 s with 201 tokens, the repeat hit the Qdrant cache in 87 ms with 0 tokens,
`/api/gateway/metrics` reported `gateway_requests_total`/`gateway_tokens_used_total`/
`gateway_cache_hits_total` straight from the ledger, and Prometheus showed the
`gateway` target `up` on `/api/gateway/metrics`. The Caddy site is `localhost:8443`
because `tls internal` needs a hostname to issue the certificate for; loopback-only
publishing is unchanged.

Cloud tiers are opt-in per key: set `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`,
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY` or
`OPENROUTER_API_KEY` in `.env`, or pass `byok` per request. `host_provider_status()`
exposes which providers the host can already reach — as booleans, never key material
(`GET /api/gateway/models`).

`GATEWAY_TOKEN` and `RATE_LIMIT_PER_MINUTE` are both unset in a fresh `.env`, which
leaves the gateway open on `127.0.0.1`; see [Gates](#gates-access-token-and-rate-limit)
before exposing it further.

## Tests

```bash
python -m pytest
```

The suite is hermetic by construction (`tests/conftest.py`): every cloud credential
variable is unset, the LiteLLM tier is forced unavailable, the ledger and the fallback
cache file are pointed at a temporary directory, and the gates are opened so no test
needs a token. 77 tests, no network calls.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/gateway/chat` | route, answer, cache, and return provenance |
| `POST` | `/api/gateway/chat/stream` | the same lifecycle as SSE (`signal` / `delta` / `done` / `error`) |
| `GET` | `/api/gateway/usage` | ledger aggregates |
| `GET` | `/api/gateway/models` | local models pulled + per-provider host key status |
| `GET` | `/api/gateway/metrics` | the ledger as Prometheus gauges (scraped by the compose stack) |
| `POST` | `/api/gateway/cache/clear` | drop every cached answer |
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

Streaming, same machine, model already warm (`gemma4:e2b`):

| Prompt | Pieces | First piece | Whole answer | Tokens |
|---|---|---|---|---|
| "What is a knowledge graph?" | 163 | 3.7 s | 6.4 s | 232 |
| "What is prompt injection?" | 132 | 7.4 s | 9.5 s | 200 |

The reader sees the answer while it is still being generated, which is the whole point:
the block route made them wait the full 6–10 s for one blob. A cold process is the
opposite story — the first token waited 41.8 s because loading the model into VRAM
comes before it, and `keep_alive=30m` is what keeps that out of the way.

Cache lifetime, measured with `CACHE_TTL_SECONDS=4`:

| Step | Result |
|---|---|
| first ask | `success`, 218 tokens, 12.5 s |
| same prompt immediately | `cached`, 0 tokens, 2.2 s |
| same prompt 5 s later | `success` again — the entry expired and the model was re-asked |
| after `POST /api/gateway/cache/clear` | `success`, 232 tokens |

Restart durability: three prompts in `data/semantic_cache.json`, process killed, started
again, first repeat answered `cached` with 0 tokens (6.4 s, because the embedder model
itself had to reload).

With Qdrant actually running (`docker compose up -d qdrant`), the same promise is held by
the server instead of the file: a prompt was stored as one 768-dim point, then the
container was restarted, then the whole Docker engine was stopped and brought back, and
the point was still there both times. A backend restart on top of that answered the same
prompt `cached` with 0 tokens in 2.4 s, and `POST /api/gateway/cache/clear` reported
`qdrant:semantic_cache` and left the collection gone until the next stored answer.
Whichever backend is live is the one the response tells you about.

Gates, measured on a second process with `GATEWAY_TOKEN` and `RATE_LIMIT_PER_MINUTE=3`:
no header `401`, wrong scheme `401`, exact bearer `200`, fourth call in the minute
`429` with `retry-after: 59.0`.

Follow-up with `history`, local tier: "And in one word?" over a previous answer about
embedding models returned `Representation` in 1.58 s — the earlier turns reached the
model, and the exchange was not served from, or written to, the cache.

## Known limits

Stated rather than hidden:

- **One shared token, not accounts.** `GATEWAY_TOKEN` is a single bearer secret: it says
  "this caller is allowed", not who they are. There are no users, sessions, or per-key
  quotas, and the rate-limit window is per client address in process memory, so it
  resets on restart and every caller looks like one client behind a proxy.
- **Streaming is the local tier.** Cloud tiers answer as one `delta` — their APIs need
  per-provider `astream` calls, which is worth doing when a cloud route becomes the
  usual one, not while local answers the simple prompts.
- **Conversation memory is per request.** The server stores no session: the client sends
  `history` with each call and the last 12 turns are forwarded. Close the tab and the
  conversation is gone.
- **Expiry is a read rule.** An entry past `CACHE_TTL_SECONDS` is treated as a miss and
  overwritten by the next answer; nothing is deleted from Qdrant on a timer.
- **The fallback cache file is rewritten whole on every save.** Fine for a few thousand
  entries, wrong for more — run Qdrant when it matters.
- **The two backends do not merge.** The index is chosen once per process, from whether
  Qdrant answers on `QDRANT_HOST:QDRANT_PORT` at the first cache use. Answers stored in
  the file while Docker was off stay invisible to Qdrant, and vice versa, so a stopped
  Docker Desktop reads as a wave of cache misses rather than an error. Restart the
  backend after starting Qdrant; the running process keeps whichever index it picked.
- **Local answers are short by design**: 4096 tokens of context total (prompt included)
  and at most 256 generated, which is about 110 words of prose. Paste a large file and
  ask about it and it will not fit — that route needs a cloud key. A multi-turn
  conversation pays for its own history inside that same window.
- **Cost is an estimate** (router-side), tokens are real (provider-reported).
  `estimated_cost_usd` for local and simulated routes is `0.0` because nothing was
  billed, not because a price was computed.
- The UI's **"Your key" chip only appears when the caller's own key answered**, which
  needs a key pasted under API keys & settings. Without one, an answer is honest about
  being routed locally or on the host key.

## Layout

```
backend/
  config.py                  pydantic-settings; all knobs come from .env
  main.py                    app, CORS, routers, /health
  app/
    api/gateway.py           the 5-step request pipeline, block + streaming routes
    api/websocket.py         SignalPacket broadcast (/ws/signals)
    core/guard.py            bearer token + per-client rate window
    core/router.py           SmartRouter heuristics + cost estimate
    core/providers.py        cascade, BYOK resolution, redaction, provenance
    core/cache.py            semantic cache: Qdrant, or a file-backed local index
    core/credentials.py      BYOKCredentials
    core/usage.py            SQLite ledger
    features/parser.py       request/response models
    features/evals.py        observable answer checks
frontend/
  src/pages/index.jsx        chat (streaming), metrics, BYOK + access-token panel, ledger
  src/components/pulse/      Canvas 2D pixel world driven by WS signals
  src/lib/pulse/gateway.js   endpoints, SSE parsing, and formatting single source
tests/                       hermetic suite (see conftest.py)
scripts/demo.sh              the five-minute proof: miss, hit, cloud route, ledger
scripts/blender/             sprite/asset generators for the canvas
Dockerfile                   the backend as a container (compose: gateway)
docker-compose.yml           qdrant, gateway(:8010), caddy TLS(:8443), prometheus(:9090)
Caddyfile                    TLS termination + security headers for the compose stack
prometheus.yml               scrape config pointed at /api/gateway/metrics
```
