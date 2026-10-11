import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import PixelChat from '../components/chat/PixelChat';
import ScoreboardHUD from '../components/hud/ScoreboardHUD';

// Dynamically import 3D Voxel canvas (SSR disabled for WebGL / Three.js)
const VoxelCanvas = dynamic(() => import('../components/minecraft/VoxelCanvas'), {
  ssr: false,
});

export default function Home() {
  const [telemetry, setTelemetry] = useState({
    activeDestination: null,
    isProcessing: false,
  });
  const [stats, setStats] = useState({
    activeModel: 'Llama 3.2 (Local)',
    cacheHitRate: '82.1%',
    avgLatency: '115 ms',
    totalTokens: '152,800',
    costSaved: '$18.40',
  });
  const [isPending, setIsPending] = useState(false);

  useEffect(() => {
    // Optional WebSocket stream listener to backend gateway
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
    } catch {
      // Backend offline, fallback gracefully
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
      console.warn('Backend unavailable, simulating routing signal locally:', err);
      // Heuristic visual fallback for preview
      const isComplex = prompt.length > 50 || prompt.includes('code') || prompt.includes('sql');
      setTelemetry({
        activeDestination: isComplex ? 'cloud_fortress' : 'local_slm',
        isProcessing: false,
      });
    } finally {
      setIsPending(false);
    }
  };

  return (
    <main className="relative w-screen h-screen overflow-hidden bg-slate-950 font-mono">
      {/* 3D Voxel Scene */}
      <VoxelCanvas telemetry={telemetry} />

      {/* Holographic Scoreboard HUD */}
      <div className="absolute top-6 right-6 z-20 pointer-events-auto">
        <ScoreboardHUD stats={stats} />
      </div>

      {/* Minecraft Command Chat */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 w-[92%] max-w-2xl pointer-events-auto">
        <PixelChat onSendMessage={handleSendMessage} isPending={isPending} />
      </div>
    </main>
  );
}
