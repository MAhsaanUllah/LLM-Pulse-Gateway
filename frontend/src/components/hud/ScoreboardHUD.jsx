import React from 'react';

export default function ScoreboardHUD({ stats = {} }) {
  const {
    activeModel = 'Ollama Llama 3.2',
    cacheHitRate = '78.4%',
    avgLatency = '142 ms',
    totalTokens = '124,590',
    costSaved = '$14.28',
  } = stats;

  return (
    <div className="w-64 bg-slate-950/85 backdrop-blur-md border-2 border-amber-500 rounded p-3 text-white font-mono text-xs shadow-lg shadow-amber-500/10">
      <div className="text-amber-400 font-bold border-b border-dashed border-amber-500/50 pb-1.5 mb-2.5 text-center tracking-wider">
        == GATEWAY SCOREBOARD ==
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <span className="text-slate-400">Target Model:</span>
          <span className="text-cyan-400 font-medium truncate max-w-[120px]">{activeModel}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-slate-400">Cache Hit Rate:</span>
          <span className="text-emerald-400 font-medium">{cacheHitRate}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-slate-400">Avg Latency:</span>
          <span className="text-yellow-300 font-medium">{avgLatency}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-slate-400">Total Tokens:</span>
          <span className="text-fuchsia-400 font-medium">{totalTokens}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-slate-400">Cost Saved:</span>
          <span className="text-emerald-400 font-bold">{costSaved}</span>
        </div>
      </div>
    </div>
  );
}
