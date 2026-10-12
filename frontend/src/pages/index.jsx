import React, { useEffect, useRef, useState } from 'react';
import Head from 'next/head';
import PulseWorld from '../components/pulse/PulseWorld';
import { postChat, fetchUsage, formatLatency, formatCost, SIGNALS_WS_URL } from '../lib/pulse/gateway';
import { Zap, Sparkles, Send, Loader2, Key, Trash2, RefreshCw } from 'lucide-react';

const BYOK_STORAGE_KEY = 'llm-pulse-byok';
const EMPTY_BYOK = { gemini_api_key: '', deepseek_api_key: '' };

const IDLE_STATUS = 'Idle — vector cache ready';

const GREETING =
  "Welcome! Ask a question and I'll route it through the semantic cache, local SLM, or cloud fortress — you'll watch the packet travel live.";

const SUGGESTIONS = [
  'Explain semantic caching',
  'What is a vector database?',
  'Write a SQL query for user analytics',
  'Write a haiku about the Warden Tower',
];

function TypewriterText({ text }) {
  const [shown, setShown] = useState('');
  useEffect(() => {
    if (!text) {
      setShown('');
      return undefined;
    }
    let i = 0;
    setShown('');
    const id = setInterval(() => {
      i += 2;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, 12);
    return () => clearInterval(id);
  }, [text]);
  return <span>{shown}</span>;
}

function MetricRow({ label, value, accent }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-200/50">
      <span className="text-xs text-slate-600 font-medium">{label}</span>
      <span className={`text-xs font-mono font-semibold ${accent || 'text-slate-900'} bg-white px-2 py-0.5 rounded border border-slate-200/70 min-w-[72px] text-center tabular-nums`}>
        {value}
      </span>
    </div>
  );
}

// Small status chip shown under an assistant reply (cache hit / simulated / fallback).
function StatusChip({ status, provider }) {
  if (!status || status === 'success') return null;
  const map = {
    cached: { text: 'Answered from cache · 0 tokens', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    simulated: { text: 'Simulated — no model answered', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
    fallback: { text: `Fallback · ${provider || 'tier'}`, cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  };
  const s = map[status];
  if (!s) return null;
  return <span className={`inline-block mt-2 text-[10px] font-medium px-2 py-0.5 rounded border ${s.cls}`}>{s.text}</span>;
}

export default function Home() {
  const engineRef = useRef(null);
  const messagesEndRef = useRef(null);
  const msgIdRef = useRef(0);
  const [connected, setConnected] = useState(false);
  const [tier, setTier] = useState('standard');
  const [prompt, setPrompt] = useState('');
  const [isPending, setIsPending] = useState(false);
  const [statusText, setStatusText] = useState(IDLE_STATUS);
  const [fps, setFps] = useState(60);
  const [metrics, setMetrics] = useState({ model: '—', latency: '—', cost: '$0.0000', tokens: '—' });
  const [banner, setBanner] = useState({ text: 'Ready for your first request', tone: 'idle' });
  const [notice, setNotice] = useState(null);
  const [byok, setByok] = useState(EMPTY_BYOK);
  const [byokSaved, setByokSaved] = useState(false);
  const [usage, setUsage] = useState(null);
  const [usageError, setUsageError] = useState(null);
  const [messages, setMessages] = useState([{ id: 0, role: 'assistant', text: GREETING }]);

  const refreshUsage = async () => {
    try {
      setUsage(await fetchUsage());
      setUsageError(null);
    } catch (err) {
      setUsageError(`Couldn't read the usage ledger: ${err.message}`);
    }
  };

  // Keys live only in this browser; nothing is sent until a prompt is.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(BYOK_STORAGE_KEY);
      if (stored) setByok({ ...EMPTY_BYOK, ...JSON.parse(stored) });
    } catch {
      setByok(EMPTY_BYOK);
    }
    refreshUsage();
  }, []);

  const saveByok = () => {
    try {
      window.localStorage.setItem(BYOK_STORAGE_KEY, JSON.stringify(byok));
      setByokSaved(true);
    } catch {
      setByokSaved(false);
    }
  };

  const clearByok = () => {
    setByok(EMPTY_BYOK);
    try {
      window.localStorage.removeItem(BYOK_STORAGE_KEY);
    } catch {
      // Private mode / storage disabled: nothing to forget, keys stay in memory only.
    }
    setByokSaved(false);
  };

  const pushMessage = (msg) => {
    msgIdRef.current += 1;
    setMessages((prev) => [...prev, { id: msgIdRef.current, ...msg }]);
  };

  // Live signal stream → drives the world animation.
  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(SIGNALS_WS_URL);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => setConnected(false);
      ws.onerror = () => setConnected(false);
      ws.onmessage = (event) => {
        try {
          const packet = JSON.parse(event.data);
          engineRef.current?.handleSignal(packet);
        } catch (err) {
          console.error('Failed to parse WebSocket packet', err);
        }
      };
    } catch {
      setConnected(false);
    }
    return () => {
      if (ws) ws.close();
    };
  }, []);

  // Keep the newest chat message in view.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isPending]);

  const send = async (raw) => {
    const text = (raw || '').trim();
    if (!text || isPending) return;

    setPrompt('');
    pushMessage({ role: 'user', text });
    setIsPending(true);
    setNotice(null);
    setBanner({ text: 'Routing your request…', tone: 'pending' });
    setMetrics({ model: 'routing…', latency: '…', cost: '$0.0000', tokens: '…' });
    engineRef.current?.beginFlow();

    try {
      const data = await postChat(text, tier, byok);
      engineRef.current?.onResponse(data);
      refreshUsage();
      pushMessage({
        role: 'assistant',
        text: data.response || '(empty response)',
        status: data.status,
        provider: data.provider_used,
      });
      setMetrics({
        model: data.model || '—',
        latency: formatLatency(data.latency_ms),
        cost: formatCost(data.cost_usd),
        tokens: data.tokens_used ? `${data.tokens_used} tokens` : '0 tokens',
      });

      if (data.status === 'cached') {
        setBanner({ text: 'Answered from the semantic cache — 0 tokens billed', tone: 'success' });
        setNotice('This answer came from vector memory — no model was called.');
      } else if (data.status === 'simulated') {
        setBanner({ text: 'Simulated — no model answered', tone: 'warn' });
        setNotice('No tier answered. Start Ollama, or paste your own Gemini/DeepSeek key under “Bring your own key” — the host\'s .env keys work too. The cascade trace is in the response metadata.');
      } else if (data.status === 'fallback') {
        setBanner({ text: `Answered by the fallback tier (${data.provider_used})`, tone: 'warn' });
      } else {
        setBanner({ text: 'Request completed', tone: 'success' });
      }
    } catch (err) {
      engineRef.current?.handleSignal({ event: 'ERROR', metadata: { error: String(err) } });
      pushMessage({
        role: 'assistant',
        text: `Couldn't reach the gateway (${err.message}). Is the backend running on port 8000?`,
        tone: 'error',
      });
      setBanner({ text: "Couldn't reach the gateway", tone: 'error' });
      setMetrics({ model: '—', latency: '—', cost: '$0.0000', tokens: '—' });
    } finally {
      setIsPending(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    send(prompt);
  };

  const clearChat = () => {
    if (isPending) return;
    msgIdRef.current = 0;
    setMessages([{ id: 0, role: 'assistant', text: GREETING }]);
    setPrompt('');
    setMetrics({ model: '—', latency: '—', cost: '$0.0000', tokens: '—' });
    setBanner({ text: 'Ready for your first request', tone: 'idle' });
    setNotice(null);
    setStatusText(IDLE_STATUS);
    engineRef.current?.resetToIdle?.();
  };

  const bannerStyles = {
    idle: 'bg-slate-50 border-slate-200 text-slate-600',
    pending: 'bg-blue-50 border-blue-200 text-blue-700',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    warn: 'bg-amber-50 border-amber-200 text-amber-800',
    error: 'bg-red-50 border-red-200 text-red-700',
  };

  return (
    <>
      <Head>
        <title>LLM Pulse Gateway — 2D Living Simulation</title>
      </Head>

      <div className="min-h-screen bg-[#f8fafd]">
        <header className="w-full bg-white/95 backdrop-blur-md border-b border-slate-200 sticky top-0 z-50 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
          <div className="max-w-[1500px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-sm text-white">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg sm:text-xl font-bold tracking-tight text-slate-900">LLM Pulse Gateway</h1>
                <span className="text-[11px] px-2 py-0.5 font-mono font-semibold rounded-md bg-blue-50 text-blue-600 border border-blue-200/80">v2.4</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className={`flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-medium ${connected ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
                <span className="relative flex h-2 w-2">
                  {connected && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />}
                  <span className={`relative inline-flex rounded-full h-2 w-2 ${connected ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                </span>
                <span>{connected ? 'Connected' : 'Backend offline'}</span>
              </div>
            </div>
          </div>
        </header>

        <main className="max-w-[1500px] mx-auto px-4 sm:px-6 py-5 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_400px] gap-5 items-start antialiased">
          {/* ── LEFT: living world + diagnostics ─────────────────────── */}
          <div className="space-y-5 min-w-0">
            <section className="rounded-xl overflow-hidden border border-slate-200 shadow-sm bg-white select-none">
              <div className="absolute top-3 left-3 sm:top-3.5 sm:left-3.5 z-20 flex items-center gap-2.5 bg-white/95 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-200/90 shadow-sm">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
                <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-800">Gateway Cluster Engine</span>
                <span className="text-[10px] bg-slate-100 text-slate-600 border border-slate-200 px-1.5 py-0.5 rounded font-mono font-medium">{fps} FPS</span>
              </div>
              <div className="relative w-full h-[260px] sm:h-[320px] bg-[#9ee2fb] overflow-hidden">
                <PulseWorld engineRef={engineRef} onStatus={setStatusText} onFps={setFps} />
              </div>
              <div className="bg-white border-t border-slate-200/80 px-4 py-2.5 flex flex-wrap items-center justify-between text-xs text-slate-600 gap-2">
                <div className="flex items-center flex-wrap gap-4 sm:gap-6">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-500 ring-2 ring-blue-100" />
                    <span className="font-medium text-slate-800 text-xs">Warden Tower <span className="text-slate-400 font-normal">(Router / Orchestrator)</span></span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-emerald-100" />
                    <span className="font-medium text-slate-800 text-xs">Memory Vault <span className="text-slate-400 font-normal">(Semantic Cache)</span></span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-500 ring-2 ring-cyan-100" />
                    <span className="font-medium text-slate-800 text-xs">Model Fortress <span className="text-slate-400 font-normal">(Local SLM / Cloud Fortress)</span></span>
                  </div>
                </div>
                <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-slate-300" />
                  <span>Send a prompt to dispatch a packet through the gateway</span>
                </div>
              </div>
            </section>

            {/* Execution metrics */}
            <section className="rounded-xl bg-white border border-slate-200 shadow-sm p-4 sm:p-5 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-200/70">
                <span className="text-xs font-mono uppercase tracking-wider text-slate-500 font-semibold">Execution Metrics</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/80 font-medium">Live</span>
              </div>
              <MetricRow label="Model Route" value={metrics.model} />
              <MetricRow label="Latency" value={metrics.latency} accent="text-blue-600" />
              <MetricRow label="Estimated Cost" value={metrics.cost} accent="text-emerald-600" />
              <MetricRow label="Tokens Used" value={metrics.tokens} />
              <div className={`mt-3 flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold shadow-sm ${bannerStyles[banner.tone]}`}>
                <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path clipRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" fillRule="evenodd" />
                </svg>
                <span>{banner.text}</span>
              </div>
              {notice && (
                <div className="inline-flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50/80 border border-amber-200 text-xs text-amber-800">
                  <svg className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                    <path clipRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" fillRule="evenodd" />
                  </svg>
                  <span className="font-medium">{notice}</span>
                </div>
              )}
              <div className="pt-1 flex items-center gap-2 text-xs text-slate-500 font-medium">
                <svg className={`w-4 h-4 text-blue-500 shrink-0 ${isPending ? 'animate-spin' : 'opacity-0'}`} fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" fill="currentColor" />
                </svg>
                <span>{statusText}</span>
              </div>
            </section>

            {/* Bring your own key */}
            <section className="rounded-xl bg-white border border-slate-200 shadow-sm p-4 sm:p-5 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-200/70">
                <span className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-slate-500 font-semibold">
                  <Key className="w-3.5 h-3.5 text-slate-400" />
                  Bring your own key
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-50 text-slate-500 border border-slate-200 font-medium">
                  {byok.gemini_api_key || byok.deepseek_api_key ? 'your key' : 'host key'}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <label className="block">
                  <span className="text-[11px] font-medium text-slate-500">Gemini API key</span>
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={byok.gemini_api_key}
                    onChange={(e) => setByok((prev) => ({ ...prev, gemini_api_key: e.target.value }))}
                    placeholder="Optional — blank uses the host key"
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs font-mono text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] font-medium text-slate-500">DeepSeek API key</span>
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={byok.deepseek_api_key}
                    onChange={(e) => setByok((prev) => ({ ...prev, deepseek_api_key: e.target.value }))}
                    placeholder="Optional — blank uses the host key"
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs font-mono text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                  />
                </label>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={saveByok}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition active:scale-95"
                >
                  Save key
                </button>
                <button
                  type="button"
                  onClick={clearByok}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-red-600 hover:border-red-200 text-xs font-semibold bg-white transition active:scale-95"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Clear
                </button>
                {byokSaved && <span className="text-[11px] font-medium text-emerald-700">Saved in this browser</span>}
              </div>
              <p className="text-[11px] leading-relaxed text-slate-500">
                Cloud requests are billed to whichever key is used. The gateway forwards your key for a
                single request — it never writes it to disk, logs it, or returns it. Browser storage is
                readable on this machine, so avoid it on a shared PC.
              </p>
            </section>

            {/* Usage ledger */}
            <section className="rounded-xl bg-white border border-slate-200 shadow-sm p-4 sm:p-5 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-200/70">
                <span className="text-xs font-mono uppercase tracking-wider text-slate-500 font-semibold">Usage Ledger</span>
                <button
                  type="button"
                  onClick={refreshUsage}
                  className="inline-flex items-center gap-1.5 text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200 hover:text-blue-600 hover:border-blue-200 font-medium transition"
                >
                  <RefreshCw className="w-3 h-3" />
                  Refresh
                </button>
              </div>
              {usageError ? (
                <p className="text-xs font-medium text-red-600">{usageError}</p>
              ) : !usage || usage.requests === 0 ? (
                <p className="text-xs text-slate-500">No requests recorded yet.</p>
              ) : (
                <>
                  <MetricRow label="Requests" value={usage.requests} />
                  <MetricRow label="Tokens billed" value={usage.tokens_used} accent="text-emerald-600" />
                  <MetricRow label="Served from cache" value={usage.cache_hits} accent="text-blue-600" />
                  <MetricRow label="Avg latency" value={formatLatency(usage.avg_latency_ms)} />
                  <MetricRow label="Estimated cost" value={formatCost(usage.estimated_cost_usd)} />
                  <div className="pt-1.5 flex flex-wrap gap-1.5">
                    {Object.entries(usage.by_route).map(([route, row]) => (
                      <span
                        key={route}
                        className="text-[10px] font-mono px-2 py-1 rounded border border-slate-200 bg-slate-50 text-slate-600"
                      >
                        {route}: {row.requests} req · {row.tokens_used} tok
                      </span>
                    ))}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Cost is the router’s estimate; tokens are reported by each provider.
                  </p>
                </>
              )}
            </section>
          </div>

          {/* ── RIGHT: chat sidebar ──────────────────────────────────── */}
          <aside className="flex flex-col rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden lg:sticky lg:top-[84px] lg:h-[calc(100vh-108px)]">
            <div className="flex-none px-4 py-3 border-b border-slate-200 flex items-center justify-between">
              <span className="text-sm font-bold text-slate-900">Gateway Chat</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={clearChat}
                  disabled={isPending || messages.length <= 1}
                  title="Clear the conversation"
                  className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500 hover:text-red-600 disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  <Trash2 className="w-3 h-3" />
                  Clear
                </button>
                <span className={`flex items-center gap-1.5 text-[10px] font-mono font-medium px-2 py-0.5 rounded-full border ${connected ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  {connected ? 'Live' : 'Offline'}
                </span>
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3 max-h-[440px] lg:max-h-none bg-slate-50/50">
              {messages.map((m, i) => {
                const isLast = i === messages.length - 1;
                if (m.role === 'user') {
                  return (
                    <div key={m.id} className="flex justify-end">
                      <div className="max-w-[85%] bg-blue-600 text-white border border-blue-500 rounded-2xl rounded-br-sm px-3.5 py-2 text-sm leading-relaxed shadow-sm whitespace-pre-wrap">
                        {m.text}
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={m.id} className="flex justify-start">
                    <div className={`max-w-[88%] border rounded-2xl rounded-bl-sm px-3.5 py-2 text-sm leading-relaxed shadow-sm whitespace-pre-wrap ${m.tone === 'error' ? 'bg-red-50 text-red-700 border-red-200' : 'bg-white text-slate-800 border-slate-200'}`}>
                      {isLast && !m.tone ? <TypewriterText text={m.text} /> : m.text}
                      {m.status && <StatusChip status={m.status} provider={m.provider} />}
                    </div>
                  </div>
                );
              })}
              {messages.length <= 1 && !isPending && (
                <div className="pt-1">
                  <p className="text-[11px] font-medium text-slate-400 mb-2">Try an example</p>
                  <div className="flex flex-col gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => send(s)}
                        className="text-left text-xs text-slate-600 bg-white border border-slate-200 rounded-lg px-3 py-2 hover:border-blue-300 hover:text-blue-700 hover:bg-blue-50/60 transition"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {isPending && (
                <div className="flex justify-start">
                  <div className="inline-flex items-center gap-2 bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2 text-xs text-slate-500 shadow-sm">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Routing through the gateway…
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form onSubmit={handleSubmit} className="flex-none border-t border-slate-200 bg-white p-3">
              <textarea
                rows={2}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                placeholder="Ask anything… send the same prompt twice to see a cache hit"
                className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <div className="inline-flex items-center rounded-lg bg-slate-100/90 p-0.5 border border-slate-200/70 gap-0.5">
                  <button
                    type="button"
                    onClick={() => setTier('standard')}
                    aria-pressed={tier === 'standard'}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${tier === 'standard' ? 'bg-white text-blue-600 border border-blue-200/80 shadow-sm' : 'text-slate-600 border border-transparent hover:text-slate-900'}`}
                  >
                    <Zap className="w-3 h-3" />
                    Standard
                  </button>
                  <button
                    type="button"
                    onClick={() => setTier('premium')}
                    aria-pressed={tier === 'premium'}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 ${tier === 'premium' ? 'bg-white text-purple-600 border border-purple-200/80 shadow-sm' : 'text-slate-600 border border-transparent hover:text-slate-900'}`}
                  >
                    <Sparkles className="w-3 h-3" />
                    Premium
                  </button>
                </div>
                <button
                  type="submit"
                  disabled={isPending}
                  className="inline-flex items-center justify-center gap-1.5 min-w-[88px] px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-xs shadow-sm hover:shadow-md active:scale-95 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                >
                  {isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                  <span>{isPending ? 'Routing…' : 'Send'}</span>
                </button>
              </div>
            </form>
          </aside>
        </main>
      </div>
    </>
  );
}
