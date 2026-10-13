#!/usr/bin/env bash
# The five-minute story, against either gateway:
#   GW=http://127.0.0.1:8000 ./scripts/demo.sh     (native backend)
#   GW=http://127.0.0.1:8010 ./scripts/demo.sh     (containerized stack)
# Step 3 answers from a cloud tier only when a key is configured (DEEPSEEK_API_KEY
# is the cheapest); otherwise it comes back as the labelled "simulated" stand-in,
# which is itself the point: the answer says what it is.
set -euo pipefail
GW="${GW:-http://127.0.0.1:8010}"

P='What is a vector database and why do LLM gateways use one?'
H='Content-Type: application/json'

echo "== 1/4 first ask: the local model answers, tokens are spent =="
curl -s -X POST "$GW/api/gateway/chat" -H "$H" -d "{\"prompt\":\"$P\",\"tier\":\"standard\"}"
echo; echo "== 2/4 same prompt again: semantic cache hit, 0 tokens =="
curl -s -X POST "$GW/api/gateway/chat" -H "$H" -d "{\"prompt\":\"$P\",\"tier\":\"standard\"}"
echo; echo "== 3/4 hard prompt, premium tier: cloud if a key exists, labelled stand-in otherwise =="
curl -s -X POST "$GW/api/gateway/chat" -H "$H" -d '{"prompt":"Refactor this flawed authentication architecture: analyze the security vulnerabilities in a JWT session design, then propose a database schema for multi-tenant isolation.","tier":"premium"}'
echo; echo "== 4/4 the ledger's account of everything above =="
curl -s "$GW/api/gateway/usage"
echo
