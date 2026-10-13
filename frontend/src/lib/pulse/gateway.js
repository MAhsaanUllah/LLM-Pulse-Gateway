// Single source for gateway endpoints so the UI never hardcodes URLs in components.
export const API_BASE = 'http://localhost:8000';
export const USAGE_URL = `${API_BASE}/api/gateway/usage`;
export const MODELS_URL = `${API_BASE}/api/gateway/models`;
export const STREAM_URL = `${API_BASE}/api/gateway/chat/stream`;
export const DOCUMENTS_URL = `${API_BASE}/api/gateway/documents`;
export const SIGNALS_WS_URL = `ws://localhost:8000/ws/signals`;

const TOKEN_STORAGE_KEY = 'llm-pulse-gateway-token';

export function getGatewayToken() {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function saveGatewayToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Private mode / storage disabled: the token stays in memory for this tab only.
  }
}

function authHeaders() {
  const token = getGatewayToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// A browser WebSocket cannot set a header, so the socket carries it in the query string.
export function signalsWsUrl() {
  const token = getGatewayToken();
  return token ? `${SIGNALS_WS_URL}?token=${encodeURIComponent(token)}` : SIGNALS_WS_URL;
}

// The gateway's two refusals mean very different things to a visitor, so say which,
// in words that stand alone as a chat bubble.
function gatewayError(label, status) {
  if (status === 401) return 'The gateway needs its access token. Open API keys & settings, paste the token, and send again.';
  if (status === 429) return 'Too many requests for this gateway. Wait a minute and send again.';
  return `${label} HTTP ${status}`;
}

// Server-Sent Events over fetch: EventSource cannot POST a body, so frames are parsed by hand.
export async function streamChat(prompt, tier, byok, history, onEvent) {
  const payload = { prompt, tier };
  if (history && history.length > 0) payload.history = history;
  const keys = Object.fromEntries(Object.entries(byok || {}).filter(([, value]) => value));
  if (Object.keys(keys).length > 0) payload.byok = keys;

  const res = await fetch(STREAM_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(gatewayError('Gateway', res.status));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf('\n\n');
    while (split >= 0) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const name = /^event:\s*(.+)$/m.exec(frame);
      const data = /^data:\s*(.+)$/m.exec(frame);
      if (name && data) onEvent(name[1].trim(), JSON.parse(data[1]));
      split = buffer.indexOf('\n\n');
    }
  }
}

export async function fetchUsage() {
  const res = await fetch(USAGE_URL, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error(gatewayError('Usage', res.status));
  }
  return res.json();
}

export async function fetchModels() {
  const res = await fetch(MODELS_URL, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error(gatewayError('Models', res.status));
  }
  return res.json();
}

export async function storeDocument(text, source) {
  const res = await fetch(DOCUMENTS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ text, source: source || 'pasted' }),
  });
  if (!res.ok) {
    throw new Error(gatewayError('Knowledge base', res.status));
  }
  return res.json();
}

export async function clearKnowledge() {
  const res = await fetch(`${DOCUMENTS_URL}/clear`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(gatewayError('Knowledge base', res.status));
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
