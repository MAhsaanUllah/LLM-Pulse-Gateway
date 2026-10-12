// Single source for gateway endpoints so the UI never hardcodes URLs in components.
export const API_BASE = 'http://localhost:8000';
export const CHAT_URL = `${API_BASE}/api/gateway/chat`;
export const USAGE_URL = `${API_BASE}/api/gateway/usage`;
export const MODELS_URL = `${API_BASE}/api/gateway/models`;
export const SIGNALS_WS_URL = `ws://localhost:8000/ws/signals`;

export async function postChat(prompt, tier, byok) {
  const payload = { prompt, tier };
  const keys = Object.fromEntries(Object.entries(byok || {}).filter(([, value]) => value));
  if (Object.keys(keys).length > 0) payload.byok = keys;

  const res = await fetch(CHAT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Gateway HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchUsage() {
  const res = await fetch(USAGE_URL);
  if (!res.ok) {
    throw new Error(`Usage HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchModels() {
  const res = await fetch(MODELS_URL);
  if (!res.ok) {
    throw new Error(`Models HTTP ${res.status}`);
  }
  return res.json();
}

export function formatLatency(ms) {
  if (ms == null) return '—';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
}

export function formatCost(usd) {
  if (usd == null) return '$0.0000';
  return usd > 0 ? `$${usd.toFixed(4)}` : '$0.0000';
}
