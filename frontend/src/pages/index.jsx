import React, { useState, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import PixelChat from '../components/chat/PixelChat';
import ScoreboardHUD from '../components/hud/ScoreboardHUD';

// Dynamically import 3D Voxel canvas (SSR disabled for WebGL / Three.js)
const VoxelCanvas = dynamic(() => import('../components/minecraft/VoxelCanvas'), {
  ssr: false,
});

// Packet events that keep the Warden Tower in its "processing" state.
const PROCESSING_EVENTS = ['CACHE_MISS', 'ROUTING_SIGNAL', 'MODEL_EXECUTION', 'EVALUATION'];
// Packet events that identify which model station / host should light up.
const DESTINATION_EVENTS = ['ROUTING_SIGNAL', 'MODEL_EXECUTION', 'COMPLETION'];

export default function Home() {
  const [telemetry, setTelemetry] = useState({
    activeDestination: null,
    isProcessing: false,
    vaultHit: false,
    signal: null,
  });
  const [stats, setStats] = useState({
    activeModel: 'Llama 3.2 (Local)',
    cacheHitRate: '0.0%',
    avgLatency: '— ms',
    totalTokens: '152,800',
    costSaved: '$18.40',
  });
  const [messages, setMessages] = useState([]);
  const [isPending, setIsPending] = useState(false);

  const signalIdRef = useRef(0);
  const requestCountRef = useRef(0);
  const cacheHitCountRef = useRef(0);
  const latencySumRef = useRef(0);

  useEffect(() => {
    // Live telemetry stream listener to the backend gateway
    let ws;
    try {
      ws = new WebSocket('ws://localhost:8000/ws/signals');
      ws.onmessage = (event) => {
        try {
          const packet = JSON.parse(event.data);
          signalIdRef.current += 1;
          setTelemetry((prev) => ({
            activeDestination: DESTINATION_EVENTS.includes(packet.event)
              ? packet.destination
              : prev.activeDestination,
            isProcessing: PROCESSING_EVENTS.includes(packet.event),
            vaultHit: packet.event === 'CACHE_HIT',
            signal: {
              id: signalIdRef.current,
              event: packet.event,
              source: packet.source,
              destination: packet.destination,
            },
          }));
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
    setMessages((prev) => [...prev, { role: 'user', text: prompt }]);
    setTelemetry((prev) => ({ ...prev, activeDestination: 'warden_tower', isProcessing: true }));

    try {
      const res = await fetch('http://localhost:8000/api/gateway/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, tier: 'standard' }),
      });
      const data = await res.json();

      requestCountRef.current += 1;
      if (data.cache_hit) cacheHitCountRef.current += 1;
      latencySumRef.current += data.latency_ms || 0;

      setMessages((prev) => [...prev, { role: 'system', text: data.response }]);
      setStats((prev) => ({
        ...prev,
        activeModel: data.model || prev.activeModel,
        avgLatency: `${Math.round(latencySumRef.current / requestCountRef.current)} ms`,
        cacheHitRate: `${((cacheHitCountRef.current / requestCountRef.current) * 100).toFixed(1)}%`,
      }));
      setTelemetry((prev) => ({ ...prev, activeDestination: data.destination, isProcessing: false }));
    } catch (err) {
      console.warn('Backend unavailable, simulating routing signal locally:', err);
      // Heuristic visual fallback for preview
      const isComplex = prompt.length > 50 || prompt.includes('code') || prompt.includes('sql');
      setMessages((prev) => [
        ...prev,
        { role: 'system', text: '[ERROR] Gateway unreachable. Previewing local routing.' },
      ]);
      setTelemetry((prev) => ({
        ...prev,
        activeDestination: isComplex ? 'cloud_fortress' : 'local_slm',
        isProcessing: false,
      }));
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
        <PixelChat onSendMessage={handleSendMessage} isPending={isPending} messages={messages} />
      </div>
    </main>
  );
}
