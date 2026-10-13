import React, { useEffect, useRef, useState } from 'react';
import Head from 'next/head';
import PulseWorld from '../components/pulse/PulseWorld';
import { streamChat, fetchUsage, fetchModels, formatLatency, formatCost, signalsWsUrl, getGatewayToken, saveGatewayToken } from '../lib/pulse/gateway';
import { Zap, Sparkles, Send, Loader2, Key, Trash2, RefreshCw, Settings, X, Activity } from 'lucide-react';

const BYOK_STORAGE_KEY = 'llm-pulse-byok';
const EMPTY_BYOK = {
  gemini_api_key: '',
  openai_api_key: '',
  anthropic_api_key: '',
  xai_api_key: '',
  deepseek_api_key: '',
  groq_api_key: '',
  openrouter_api_key: '',
};

// The cloud providers a visitor can bring their own key for.
const PROVIDER_FIELDS = [
  { key: 'gemini_api_key', label: 'Google Gemini' },
  { key: 'openai_api_key', label: 'OpenAI' },
  { key: 'anthropic_api_key', label: 'Anthropic (Claude)' },
  { key: 'xai_api_key', label: 'xAI (Grok)' },
  { key: 'deepseek_api_key', label: 'DeepSeek' },
  { key: 'groq_api_key', label: 'Groq' },
  { key: 'openrouter_api_key', label: 'OpenRouter' },
];

const IDLE_STATUS = 'Idle: vector cache ready';

const GREETING =
  "Ask anything. I'll route it through the cache, a local model, or the cloud, live.";

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

// ── Tiny Markdown renderer for assistant replies ────────────────────────────
// Handles what models actually emit: #/##/### headings, **bold**, `code`,
// *italic*, - / * / 1. lists, --- rules and ``` code fences. No dependency.
function renderInline(text) {
  const parts = [];
  const regex = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*]+\*)/g;
  let last = 0;
  let key = 0;
  let m;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith('**') || tok.startsWith('__')) {
      parts.push(<strong key={`b${key++}`} className="font-semibold text-slate-900">{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith('`')) {
      parts.push(<code key={`c${key++}`} className="px-1 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[0.85em]">{tok.slice(1, -1)}</code>);
    } else {
      parts.push(<em key={`i${key++}`}>{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function Markdown({ text }) {
  const lines = (text || '').replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let list = null;
  let code = null;
  let key = 0;

  const flushCode = () => {
    blocks.push(
      <pre key={`p${key++}`} className="my-1 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
        <code>{code.join('\n')}</code>
      </pre>
    );
    code = null;
  };

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? 'ol' : 'ul';
    blocks.push(
      <Tag
        key={`l${key++}`}
        className={`space-y-1 pl-5 ${list.ordered ? 'list-decimal' : 'list-disc'} marker:text-slate-400`}
      >
        {list.items.map((it, idx) => (
          <li key={idx}>{renderInline(it)}</li>
        ))}
      </Tag>
    );
    list = null;
  };

  lines.forEach((raw) => {
    const t = raw.trim();

    if (code !== null) {
      if (t.startsWith('```')) flushCode();
      else code.push(raw);
      return;
    }
    if (t.startsWith('```')) {
      flushList();
      code = [];
      return;
    }
    if (t === '') {
      flushList();
      return;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) {
      flushList();
      blocks.push(<hr key={`h${key++}`} className="my-2 border-slate-200" />);
      return;
    }

    let m;
    if ((m = /^(#{1,6})\s+(.*)$/.exec(t))) {
      flushList();
      const level = m[1].length;
      blocks.push(
        <p key={`hd${key++}`} className={`${level <= 2 ? 'mt-3 text-[0.95rem] font-bold' : 'mt-2 text-sm font-semibold'} text-slate-900 first:mt-0`}>
          {renderInline(m[2])}
        </p>
      );
      return;
    }
    if ((m = /^[-*+]\s+(.*)$/.exec(t))) {
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(m[1]);
      return;
    }
    if ((m = /^\d+\.\s+(.*)$/.exec(t))) {
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(m[1]);
      return;
    }

    flushList();
    blocks.push(<p key={`t${key++}`} className="mt-1.5 first:mt-0">{renderInline(t)}</p>);
  });

  if (code !== null) flushCode();
  flushList();

  return <div className="space-y-1 text-sm leading-relaxed text-slate-800">{blocks}</div>;
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

// Chips under an assistant reply: how it was answered, whose key paid, whether it ran out of budget.
function StatusChip({ status, provider, keySource, truncated }) {
  const map = {
    cached: { text: 'Answered from cache · 0 tokens', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    simulated: { text: 'Simulated: no model answered', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
    fallback: { text: `Fallback · ${provider || 'tier'}`, cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  };
  const chips = [];
  if (map[status]) chips.push(map[status]);
  if (truncated) {
    chips.push({ text: 'Cut off by the token budget', cls: 'bg-amber-50 text-amber-700 border-amber-200' });
  }
  if (keySource === 'byok') {
    chips.push({ text: 'Your key', cls: 'bg-blue-50 text-blue-700 border-blue-200' });
  } else if (keySource === 'operator') {
    chips.push({ text: 'Host key', cls: 'bg-slate-100 text-slate-600 border-slate-200' });
  }
  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {chips.map((c) => (
        <span key={c.text} className={`text-[10px] font-medium px-2 py-0.5 rounded border ${c.cls}`}>{c.text}</span>
      ))}
    </div>
  );
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
  const [gatewayToken, setGatewayToken] = useState(() => getGatewayToken());
  const [tokenDraft, setTokenDraft] = useState(() => getGatewayToken());
  const [showSettings, setShowSettings] = useState(false);
  const [localModels, setLocalModels] = useState(null);
  const [detecting, setDetecting] = useState(false);
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

  const detectLocal = async () => {
    setDetecting(true);
    try {
      setLocalModels(await fetchModels());
    } catch (err) {
      setLocalModels({ ollama_available: false, base_url: '', models: [], error: err.message });
    } finally {
      setDetecting(false);
    }
  };

  // Probe the local daemon whenever the settings dialog is opened.
  useEffect(() => {
    if (showSettings) detectLocal();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSettings]);

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

  // The token gates every call, so saving it reconnects the socket and re-reads the ledger.
  const saveToken = () => {
    const trimmed = tokenDraft.trim();
    saveGatewayToken(trimmed);
    setGatewayToken(trimmed);
    refreshUsage();
  };

  // The id is taken here, not inside the updater: dev mode runs the updater twice, and
  // two pushes in one batch would otherwise read the same counter and collide on a key.
  const pushMessage = (msg) => {
    msgIdRef.current += 1;
    const id = msgIdRef.current;
    setMessages((prev) => [...prev, { id, ...msg }]);
    return id;
  };

  // Live signal stream → drives the world animation. Reopens when the token changes.
  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(signalsWsUrl());
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gatewayToken]);

  // Keep the newest chat message in view.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isPending]);

  const send = async (raw) => {
    const text = (raw || '').trim();
    if (!text || isPending) return;

    setPrompt('');
    // Everything the visitor can still see above this line is the conversation the
    // model needs to understand a follow-up. The greeting and our own failures are
    // not answers, so they stay out.
    const history = messages
      .filter((m) => m.id !== 0 && m.tone !== 'error' && (m.text || '').trim())
      .map((m) => ({ role: m.role, content: m.text }));
    pushMessage({ role: 'user', text });
    setIsPending(true);
    setNotice(null);
    setBanner({ text: 'Routing your request…', tone: 'pending' });
    setMetrics({ model: 'routing…', latency: '…', cost: '$0.0000', tokens: '…' });
    engineRef.current?.beginFlow();

    let final = null;
    let failure = null;
    try {
      const replyId = pushMessage({ role: 'assistant', text: '' });
      let streamed = '';
      await streamChat(text, tier, byok, history, (name, data) => {
        if (name === 'delta') {
          streamed += data.text;
          setBanner({ text: 'Answering…', tone: 'pending' });
          setMessages((prev) => prev.map((m) => (m.id === replyId ? { ...m, text: streamed } : m)));
        } else if (name === 'done') {
          final = data;
        } else if (name === 'error') {
          failure = data.detail || 'the gateway stopped mid-stream';
        }
      });

      if (failure) throw new Error(failure);
      if (!final) throw new Error('the stream ended without an answer');

      const data = final;
      engineRef.current?.onResponse(data);
      refreshUsage();
      setMessages((prev) => prev.map((m) => (m.id === replyId ? {
        ...m,
        text: data.response || streamed || '(empty response)',
        status: data.status,
        provider: data.provider_used,
        keySource: data.key_source,
        truncated: data.truncated,
      } : m)));
      setMetrics({
        model: data.model || '—',
        latency: formatLatency(data.latency_ms),
        cost: formatCost(data.cost_usd),
        tokens: data.tokens_used ? `${data.tokens_used} tokens` : '0 tokens',
      });

      if (data.status === 'cached') {
        setBanner({ text: 'Answered from the semantic cache: 0 tokens billed', tone: 'success' });
        setNotice('This answer came from vector memory; no model was called.');
      } else if (data.status === 'simulated') {
        setBanner({ text: 'Simulated: no model answered', tone: 'warn' });
        setNotice('No tier answered. Start Ollama, or paste your own Gemini/DeepSeek key under “Bring your own key”; the host\'s .env keys work too. The cascade trace is in the response metadata.');
      } else if (data.status === 'fallback') {
        setBanner({ text: `Answered by the fallback tier (${data.provider_used})`, tone: 'warn' });
      } else {
        setBanner({ text: 'Request completed', tone: 'success' });
      }
    } catch (err) {
      engineRef.current?.handleSignal({ event: 'ERROR', metadata: { error: String(err) } });
      // fetch rejects with TypeError when nothing answered; any other error is the
      // gateway itself refusing, which is a different fix and must not say "is it down".
      const unreachable = err instanceof TypeError;
      pushMessage({
        role: 'assistant',
        text: unreachable
          ? "Couldn't reach the gateway on port 8000. Start it with `python -m uvicorn backend.main:app --port 8000`."
          : err.message,
        tone: 'error',
      });
      setBanner({ text: unreachable ? "Couldn't reach the gateway" : 'The gateway refused this request', tone: 'error' });
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
        <title>LLM Pulse Gateway - 2D Living Simulation</title>
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
              <button
                type="button"
                onClick={() => setShowSettings(true)}
                title="API keys & settings"
                className="inline-flex items-center justify-center w-9 h-9 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-900 hover:border-slate-300 bg-white transition"
              >
                <Settings className="w-4 h-4" />
              </button>
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

            {/* Diagnostics — this request + session ledger, side by side */}
            <section className="rounded-xl bg-white border border-slate-200 shadow-sm p-4 sm:p-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-200/70">
                <span className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-slate-500 font-semibold">
                  <Activity className="w-3.5 h-3.5 text-slate-400" />
                  Diagnostics
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/80 font-medium">Live</span>
                  <button
                    type="button"
                    onClick={refreshUsage}
                    className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200 hover:text-blue-600 hover:border-blue-200 font-medium transition"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Refresh
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5 pt-3">
                {/* Column 1 — the request in flight */}
                <div>
                  <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1">This request</p>
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
                    <div className="mt-2 flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50/80 border border-amber-200 text-xs text-amber-800">
                      <svg className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path clipRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" fillRule="evenodd" />
                      </svg>
                      <span className="font-medium">{notice}</span>
                    </div>
                  )}
                  <div className="mt-2 flex items-center gap-2 text-xs text-slate-500 font-medium">
                    <svg className={`w-4 h-4 text-blue-500 shrink-0 ${isPending ? 'animate-spin' : 'opacity-0'}`} fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" fill="currentColor" />
                    </svg>
                    <span>{statusText}</span>
                  </div>
                </div>

                {/* Column 2 — the session ledger */}
                <div className="sm:border-l sm:border-slate-200/70 sm:pl-6">
                  <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1">Session ledger</p>
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
                      <div className="pt-2 flex flex-wrap gap-1.5">
                        {Object.entries(usage.by_route).map(([route, row]) => (
                          <span
                            key={route}
                            className="text-[10px] font-mono px-2 py-1 rounded border border-slate-200 bg-slate-50 text-slate-600"
                          >
                            {route}: {row.requests} req · {row.tokens_used} tok
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>

              <p className="mt-4 pt-3 border-t border-slate-200/60 text-[11px] text-slate-400">
                Cost is the router’s estimate; tokens are reported by each provider.
              </p>
            </section>
          </div>

          {/* ── RIGHT: chat sidebar ──────────────────────────────────── */}
          <aside className="flex flex-col rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden lg:sticky lg:top-[84px] lg:h-[calc(100vh-108px)]">
            <div className="flex-none px-4 py-3 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-slate-900">Gateway Chat</span>
                <button
                  type="button"
                  onClick={clearChat}
                  disabled={isPending || messages.length <= 1}
                  title="Clear the conversation"
                  className="inline-flex items-center justify-center w-6 h-6 rounded-md text-slate-400 hover:text-red-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <span className={`flex items-center gap-1.5 text-[10px] font-mono font-medium px-2 py-0.5 rounded-full border ${connected ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
                <span className={`inline-block w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                {connected ? 'Live' : 'Offline'}
              </span>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3 max-h-[440px] lg:max-h-none bg-slate-50/50">
              {messages.map((m) => {
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
                    <div className={`max-w-[92%] border rounded-2xl rounded-bl-sm px-3.5 py-2.5 shadow-sm ${m.tone === 'error' ? 'bg-red-50 text-red-700 border-red-200 text-sm leading-relaxed whitespace-pre-wrap' : 'bg-white border-slate-200'}`}>
                      {m.id === 0 ? <TypewriterText text={m.text} /> : <Markdown text={m.text} />}
                      <StatusChip status={m.status} provider={m.provider} keySource={m.keySource} truncated={m.truncated} />
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

        {showSettings && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
              onClick={() => setShowSettings(false)}
            />
            <div className="relative z-10 w-full max-w-md rounded-xl border border-slate-200 bg-white shadow-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                  <Key className="w-4 h-4 text-slate-400" />
                  API keys
                </h2>
                <button
                  type="button"
                  onClick={() => setShowSettings(false)}
                  title="Close"
                  className="inline-flex items-center justify-center w-7 h-7 rounded-lg text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                <span className="text-[11px] font-semibold text-slate-600">Gateway access token</span>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Only if the operator set GATEWAY_TOKEN. Blank works against a local gateway.
                </p>
                <div className="mt-2 flex gap-2">
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={tokenDraft}
                    onChange={(e) => setTokenDraft(e.target.value)}
                    placeholder="Not set"
                    className="flex-1 min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-mono text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                  />
                  <button
                    type="button"
                    onClick={saveToken}
                    className="shrink-0 text-[11px] font-semibold px-3 py-2 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 hover:border-blue-300 hover:bg-blue-100 transition"
                  >
                    Use token
                  </button>
                </div>
              </div>

              <p className="text-xs text-slate-500">
                Optional. Paste your own key for any provider; leave blank to use the host key.
              </p>

              <div className="max-h-60 overflow-y-auto pr-1 space-y-2.5 no-scrollbar">
                {PROVIDER_FIELDS.map((p) => (
                  <label key={p.key} className="block">
                    <span className="flex items-center gap-2">
                      <span className="text-[11px] font-medium text-slate-500">{p.label}</span>
                      {(localModels?.providers || []).some((s) => s.provider === p.key.replace('_api_key', '') && s.host_key_configured) && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-emerald-200 bg-emerald-50 text-emerald-700">host key ready</span>
                      )}
                    </span>
                    <input
                      type="password"
                      autoComplete="off"
                      spellCheck={false}
                      value={byok[p.key]}
                      onChange={(e) => setByok((prev) => ({ ...prev, [p.key]: e.target.value }))}
                      placeholder="Optional: blank uses the host key"
                      className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs font-mono text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                    />
                  </label>
                ))}
              </div>

              {/* Local model detection */}
              <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-600">Local models (Ollama)</span>
                  <button
                    type="button"
                    onClick={detectLocal}
                    disabled={detecting}
                    className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-white text-slate-600 border border-slate-200 hover:text-blue-600 hover:border-blue-200 font-medium transition disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3 h-3 ${detecting ? 'animate-spin' : ''}`} />
                    {detecting ? 'Detecting…' : 'Detect'}
                  </button>
                </div>
                {localModels && (
                  localModels.ollama_available ? (
                    localModels.models.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {localModels.models.map((m) => (
                          <span key={m.name} className="text-[10px] font-mono px-2 py-0.5 rounded border border-emerald-200 bg-emerald-50 text-emerald-700">
                            {m.name}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-2 text-[11px] text-slate-500">Ollama is running, but no models are pulled yet.</p>
                    )
                  ) : (
                    <p className="mt-2 text-[11px] text-slate-500">
                      Ollama not detected{localModels.base_url ? ` at ${localModels.base_url}` : ''}.
                    </p>
                  )
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={saveByok}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold transition active:scale-95"
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
                single request; it never writes it to disk, logs it, or returns it. Browser storage is
                readable on this machine, so avoid it on a shared PC.
              </p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
