import React, { useState } from 'react';

export default function PixelChat({ onSendMessage, isPending, messages = [] }) {
  const [input, setInput] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isPending) return;
    onSendMessage(input);
    setInput('');
  };

  return (
    <div className="w-full max-w-2xl bg-black/85 backdrop-blur-md border-4 border-slate-700 rounded-lg p-4 shadow-2xl text-white font-mono">
      <div className="flex items-center justify-between mb-3 text-xs tracking-wider">
        <span className="text-emerald-400 font-bold">&gt; MINECRAFT GATEWAY COMMAND TERMINAL</span>
        <span className="text-slate-400 text-[10px]">STATUS: {isPending ? 'TRANSMITTING...' : 'ONLINE'}</span>
      </div>

      {/* Minecraft-style chat bubbles */}
      {messages.length > 0 && (
        <div className="flex flex-col gap-2 mb-3 max-h-40 overflow-y-auto pr-1">
          {messages.slice(-6).map((m, i) => (
            <div
              key={i}
              className={`max-w-[85%] px-3 py-2 text-xs leading-relaxed border-2 ${
                m.role === 'user'
                  ? 'self-end bg-emerald-500/90 text-slate-950 border-emerald-300 rounded-2xl rounded-br-sm'
                  : 'self-start bg-slate-800 text-slate-100 border-slate-600 rounded-2xl rounded-bl-sm'
              }`}
            >
              {m.text}
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question or transmit an LLM instruction..."
          disabled={isPending}
          className="flex-1 bg-slate-950 border-2 border-slate-700 px-4 py-2.5 text-sm text-white placeholder-slate-500 rounded-2xl outline-none focus:border-cyan-400 transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isPending}
          className={`px-6 py-2.5 font-bold text-xs uppercase tracking-wider rounded-2xl border-2 transition-all ${
            isPending
              ? 'bg-slate-700 text-slate-400 border-slate-600 cursor-not-allowed'
              : 'bg-emerald-500 text-slate-950 border-emerald-400 hover:bg-emerald-400 active:scale-95 cursor-pointer'
          }`}
        >
          {isPending ? 'PULSING' : 'TRANSMIT'}
        </button>
      </form>
    </div>
  );
}
