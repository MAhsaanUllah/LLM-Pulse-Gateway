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

echo "== 1/5 first ask: the local model answers, tokens are spent =="
curl -s -X POST "$GW/api/gateway/chat" -H "$H" -d "{\"prompt\":\"$P\",\"tier\":\"standard\"}"
echo; echo "== 2/5 same prompt again: semantic cache hit, 0 tokens =="
curl -s -X POST "$GW/api/gateway/chat" -H "$H" -d "{\"prompt\":\"$P\",\"tier\":\"standard\"}"
echo; echo "== 3/5 a document goes in and the next answer comes out of it: rag_used, still local =="
curl -s -X POST "$GW/api/gateway/documents" -H "$H" \
  -d '{"text":"Pulse handbook chapter 9: the emergency generator is named TRITON-4 and must be tested every first Monday.","source":"handbook-ch9"}'
echo
# A grounded answer is cached under the raw prompt, so a re-run of this script would
# otherwise replay the previous answer and report rag_used false. Clear it first.
curl -s -X POST "$GW/api/gateway/cache/clear" -H "$H" > /dev/null
curl -s -X POST "$GW/api/gateway/chat" -H "$H" \
  -d '{"prompt":"what is the emergency generator named in chapter 9 of the handbook?","tier":"standard"}'
echo; echo "== 4/5 hard prompt, premium tier: cloud if a key exists, labelled stand-in otherwise =="
curl -s -X POST "$GW/api/gateway/chat" -H "$H" -d '{"prompt":"Refactor this flawed authentication architecture: analyze the security vulnerabilities in a JWT session design, then propose a database schema for multi-tenant isolation.","tier":"premium"}'
echo; echo "== 5/5 the ledger's account of everything above =="
curl -s "$GW/api/gateway/usage"
echo
