import React, { useEffect, useRef, useState } from 'react';
import Head from 'next/head';
import PulseWorld from '../components/pulse/PulseWorld';
import { postChat, formatLatency, formatCost, SIGNALS_WS_URL } from '../lib/pulse/gateway';
import { Zap, Sparkles, Send, Loader2 } from 'lucide-react';

const IDLE_STATUS = 'System idle & vector cache ready';

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
  return <p className="text-sm leading-relaxed text-slate-800 font-sans whitespace-pre-wrap">{shown}</p>;
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

export default function Home() {
  const engineRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [tier, setTier] = useState('standard');
  const [prompt, setPrompt] = useState('');
  const [isPending, setIsPending] = useState(false);
  const [statusText, setStatusText] = useState(IDLE_STATUS);
  const [fps, setFps] = useState(60);
  const [metrics, setMetrics] = useState({ model: '—', latency: '—', cost: '$0.0000', tokens: '—' });
  const [banner, setBanner] = useState({ text: 'Awaiting first request', tone: 'idle' });
  const [notice, setNotice] = useState(null);
  const [response, setResponse] = useState(
    "Hello! I'm your LLM Pulse Gateway. Submit a prompt and I'll route it through the semantic cache, the local SLM, or the cloud fortress — you'll watch the packet travel live."
  );

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    const text = prompt.trim();
    if (!text || isPending) return;

    setIsPending(true);
    setNotice(null);
    setBanner({ text: 'Routing in progress…', tone: 'pending' });
    setMetrics({ model: 'routing…', latency: '…', cost: '$0.0000', tokens: '…' });
    engineRef.current?.beginFlow();

    try {
      const data = await postChat(text, tier);
      engineRef.current?.onResponse(data);
      setResponse(data.response || '(empty response)');
      setMetrics({
        model: data.model || '—',
        latency: formatLatency(data.latency_ms),
        cost: formatCost(data.cost_usd),
        tokens: data.tokens_used ? `${data.tokens_used} tokens` : '0 tokens',
      });

      if (data.status === 'cached') {
        setBanner({ text: 'Served from semantic cache — 0 tokens billed', tone: 'success' });
        setNotice('This response was retrieved from vector memory without calling a model.');
      } else if (data.status === 'simulated') {
        setBanner({ text: 'SIMULATED — no model answered', tone: 'warn' });
        setNotice('Start Ollama or add GEMINI_API_KEY / DEEPSEEK_API_KEY in backend/.env to get real inference. The cascade trace is in the response metadata.');
      } else if (data.status === 'fallback') {
        setBanner({ text: `Answered by fallback tier (${data.provider_used})`, tone: 'warn' });
      } else {
        setBanner({ text: 'Response completed successfully', tone: 'success' });
      }
    } catch (err) {
      engineRef.current?.handleSignal({ event: 'ERROR', metadata: { error: String(err) } });
      setResponse(`[ERROR] Gateway unreachable: ${err.message}. Is the backend running on :8000?`);
      setBanner({ text: 'Gateway unreachable', tone: 'error' });
      setMetrics({ model: '—', latency: '—', cost: '$0.0000', tokens: '—' });
    } finally {
      setIsPending(false);
    }
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

      <header className="w-full bg-white/95 backdrop-blur-md border-b border-slate-200 sticky top-0 z-50 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6 antialiased">
        {/* Living world */}
        <section className="sticky top-[72px] z-30 rounded-xl overflow-hidden border border-slate-200 shadow-sm bg-white select-none group transition">
          <div className="absolute top-3 left-3 sm:top-3.5 sm:left-3.5 z-20 flex items-center gap-2.5 bg-white/95 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-200/90 shadow-sm">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-800">Gateway Cluster Engine</span>
            <span className="text-[10px] bg-slate-100 text-slate-600 border border-slate-200 px-1.5 py-0.5 rounded font-mono font-medium">{fps} FPS</span>
          </div>
          <div className="relative w-full h-[280px] sm:h-[320px] bg-[#9ee2fb] overflow-hidden">
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
              <span>Submit a prompt to dispatch a packet through the gateway</span>
            </div>
          </div>
        </section>

        {/* Prompt composer */}
        <section className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-4 sm:p-5 transition hover:border-slate-300 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100">
          <form onSubmit={handleSubmit}>
            <textarea
              className="w-full resize-none border-0 p-1 text-slate-800 placeholder-slate-400 text-sm sm:text-base focus:ring-0 bg-transparent leading-relaxed"
              rows={2}
              placeholder="Ask anything… e.g. “Explain semantic caching” — send it twice to trigger a cache hit"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
              <div className="inline-flex items-center rounded-lg bg-slate-100/90 p-1 border border-slate-200/70 gap-1">
                <button
                  type="button"
                  onClick={() => setTier('standard')}
                  aria-pressed={tier === 'standard'}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${tier === 'standard' ? 'bg-white text-blue-600 border border-blue-200/80 shadow-sm ring-1 ring-blue-100' : 'text-slate-600 border border-transparent hover:text-slate-900 hover:bg-white/70'}`}
                >
                  <Zap className="w-3.5 h-3.5" />
                  Standard (SLM)
                </button>
                <button
                  type="button"
                  onClick={() => setTier('premium')}
                  aria-pressed={tier === 'premium'}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-md transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 ${tier === 'premium' ? 'bg-white text-purple-600 border border-purple-200/80 shadow-sm ring-1 ring-purple-100' : 'text-slate-600 border border-transparent hover:text-slate-900 hover:bg-white/70'}`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Premium
                </button>
              </div>
              <button
                type="submit"
                disabled={isPending}
                className="inline-flex items-center justify-center gap-2 min-w-[108px] px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold text-xs sm:text-sm shadow-sm hover:shadow-md active:scale-95 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-1"
              >
                {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                <span>{isPending ? 'Routing…' : 'Send'}</span>
              </button>
            </div>
          </form>
        </section>

        {/* Response & diagnostics */}
        <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 sm:p-6 transition hover:shadow-md">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div className="lg:col-span-7 flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-200 text-blue-600 flex items-center justify-center shadow-sm">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect height="10" rx="2" strokeWidth="2" width="18" x="3" y="11" />
                      <circle cx="8.5" cy="16" fill="currentColor" r="1.5" />
                      <circle cx="15.5" cy="16" fill="currentColor" r="1.5" />
                      <path d="M12 7v4M8 3h8" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-slate-900 leading-tight">Response Payload</h2>
                    <p className="text-xs text-slate-500">Generated via orchestrator workflow</p>
                  </div>
                </div>
              </div>
              <div className="rounded-xl border border-slate-200/80 p-4 bg-slate-50/60 min-h-[96px] flex items-start shadow-sm">
                <TypewriterText text={response} />
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
            </div>
            <div className="lg:col-span-5">
              <div className="rounded-xl bg-slate-50/50 border border-slate-200/90 shadow-sm p-4 sm:p-5 space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-200/70">
                  <span className="text-xs font-mono uppercase tracking-wider text-slate-500 font-semibold">Execution Metrics</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/80 font-medium">Live telemetry</span>
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
              </div>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}
