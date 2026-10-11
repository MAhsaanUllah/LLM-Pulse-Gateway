import React from 'react';

export default function ScoreboardHUD({ stats = {} }) {
  const {
    activeModel = "Ollama Llama 3.2",
    cacheHitRate = "78.4%",
    avgLatency = "142 ms",
    totalTokens = "124,590",
    costSaved = "$14.28"
  } = stats;

  return (
    <div style={{
      background: 'rgba(10, 10, 15, 0.8)',
      border: '3px solid #ffaa00',
      padding: '12px 18px',
      color: '#fff',
      fontFamily: '"Courier New", Courier, monospace',
      boxShadow: '0 4px 16px rgba(255, 170, 0, 0.25)',
      width: '240px',
      fontSize: '13px',
      lineHeight: '1.6'
    }}>
      <div style={{ 
        color: '#ffaa00', 
        fontWeight: 'bold', 
        borderBottom: '2px dashed #ffaa00', 
        paddingBottom: '4px',
        marginBottom: '8px',
        textAlign: 'center'
      }}>
        == GATEWAY SCOREBOARD ==
      </div>

      <div><span style={{ color: '#aaaaaa' }}>Model:</span> <span style={{ color: '#55ffff' }}>{activeModel}</span></div>
      <div><span style={{ color: '#aaaaaa' }}>Cache Hit:</span> <span style={{ color: '#55ff55' }}>{cacheHitRate}</span></div>
      <div><span style={{ color: '#aaaaaa' }}>Latency:</span> <span style={{ color: '#ffff55' }}>{avgLatency}</span></div>
      <div><span style={{ color: '#aaaaaa' }}>Tokens:</span> <span style={{ color: '#ff55ff' }}>{totalTokens}</span></div>
      <div><span style={{ color: '#aaaaaa' }}>Cost Saved:</span> <span style={{ color: '#55ff55' }}>{costSaved}</span></div>
    </div>
  );
}
