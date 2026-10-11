import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import PixelChat from '../components/chat/PixelChat';
import ScoreboardHUD from '../components/hud/ScoreboardHUD';

// Dynamically import 3D Voxel canvas (SSR disabled for Three.js)
const VoxelCanvas = dynamic(() => import('../components/minecraft/VoxelCanvas'), {
  ssr: false,
});

export default function Home() {
  const [telemetry, setTelemetry] = useState({
    activeDestination: null,
    isProcessing: false,
  });
  const [stats, setStats] = useState({
    activeModel: "Llama 3.2 (Local)",
    cacheHitRate: "82.1%",
    avgLatency: "115 ms",
    totalTokens: "152,800",
    costSaved: "$18.40",
  });
  const [isPending, setIsPending] = useState(false);

  useEffect(() => {
    // Optional: Connect to backend WebSocket at ws://localhost:8000/ws/signals
    let ws;
    try {
      ws = new WebSocket('ws://localhost:8000/ws/signals');
      ws.onmessage = (event) => {
        try {
          const packet = JSON.parse(event.data);
          setTelemetry({
            activeDestination: packet.destination,
            isProcessing: packet.event === 'ROUTING_SIGNAL',
          });
        } catch (err) {
          console.error('Failed to parse WebSocket packet', err);
        }
      };
    } catch (e) {
      console.warn('Backend WebSocket offline, running in mock telemetry mode');
    }

    return () => {
      if (ws) ws.close();
    };
  }, []);

  const handleSendMessage = async (prompt) => {
    setIsPending(true);
    setTelemetry({ activeDestination: 'warden_tower', isProcessing: true });

    try {
      const res = await fetch('http://localhost:8000/api/gateway/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, tier: 'standard' }),
      });
      const data = await res.json();

      setTelemetry({
        activeDestination: data.destination,
        isProcessing: false,
      });

      setStats((prev) => ({
        ...prev,
        activeModel: data.model || prev.activeModel,
        avgLatency: `${data.latency_ms || 120} ms`,
      }));
    } catch (err) {
      console.error(err);
      // Fallback visual mock update
      setTelemetry({ activeDestination: 'local_slm', isProcessing: false });
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden', background: '#0a0d14' }}>
      {/* 3D Voxel Scene */}
      <VoxelCanvas telemetry={telemetry} />

      {/* Holographic Scoreboard HUD */}
      <div style={{ position: 'absolute', top: '24px', right: '24px', zIndex: 10 }}>
        <ScoreboardHUD stats={stats} />
      </div>

      {/* Minecraft Command Chat */}
      <div style={{ position: 'absolute', bottom: '24px', left: '50%', transform: 'translateX(-50%)', zIndex: 10, width: '90%', maxWidth: '600px' }}>
        <PixelChat onSendMessage={handleSendMessage} isPending={isPending} />
      </div>
    </div>
  );
}
