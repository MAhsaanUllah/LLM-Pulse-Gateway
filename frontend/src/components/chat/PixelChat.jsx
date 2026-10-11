import React, { useState } from 'react';

export default function PixelChat({ onSendMessage, isPending }) {
  const [input, setInput] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isPending) return;
    onSendMessage(input);
    setInput('');
  };

  return (
    <div style={{
      background: 'rgba(20, 20, 25, 0.85)',
      border: '4px solid #4a4a5a',
      borderRadius: '8px',
      padding: '16px',
      color: '#ffffff',
      fontFamily: '"Courier New", Courier, monospace',
      boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
      maxWidth: '600px',
      width: '100%'
    }}>
      <div style={{ marginBottom: '12px', fontSize: '14px', letterSpacing: '1px', color: '#55ff55' }}>
        &gt; MINECRAFT GATEWAY COMMAND TERMINAL
      </div>
      
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask or dispatch an LLM query..."
          disabled={isPending}
          style={{
            flex: 1,
            background: '#111218',
            border: '2px solid #555566',
            padding: '10px 14px',
            color: '#fff',
            fontFamily: 'inherit',
            fontSize: '14px',
            outline: 'none',
          }}
        />
        <button
          type="submit"
          disabled={isPending}
          style={{
            background: isPending ? '#555555' : '#2ecc71',
            color: '#000',
            fontWeight: 'bold',
            border: '2px solid #27ae60',
            padding: '0 20px',
            cursor: isPending ? 'not-allowed' : 'pointer',
            fontFamily: 'inherit',
            textTransform: 'uppercase',
          }}
        >
          {isPending ? 'PULSING...' : 'TRANSMIT'}
        </button>
      </form>
    </div>
  );
}
