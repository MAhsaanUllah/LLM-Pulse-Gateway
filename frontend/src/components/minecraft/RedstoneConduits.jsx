import React, { useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { TOWER_POSITIONS } from './SignalMessenger';

// Anchor nodes matching the spread layout
const NODES = TOWER_POSITIONS;

const EVENT_COLORS = {
  CACHE_HIT: '#55ff55',
  CACHE_MISS: '#ffaa00',
  ROUTING_SIGNAL: '#ff0044',
  MODEL_EXECUTION: '#00e5ff',
  EVALUATION: '#ffff55',
  COMPLETION: '#ff55ff',
  ERROR: '#ff2222',
};

const POOL_SIZE = 20;
const TRAVEL_SECONDS = 1.4;

const nodeAt = (name) => NODES[name] || NODES.warden_tower;

export default function RedstoneConduits({ pulseActive = false, signal = null }) {
  const lineVaultRef = useRef();
  const lineSlmRef = useRef();
  const lineCloudRef = useRef();
  const particleRefs = useRef([]);
  const particles = useRef([]);

  // Spawn travelling pulse particle when telemetry event occurs
  useEffect(() => {
    if (!signal || !signal.event) return;
    particles.current.push({
      from: nodeAt(signal.source),
      to: nodeAt(signal.destination),
      color: EVENT_COLORS[signal.event] || '#ff0044',
      t: 0,
    });
    if (particles.current.length > POOL_SIZE) {
      particles.current.splice(0, particles.current.length - POOL_SIZE);
    }
  }, [signal]);

  useFrame((state, delta) => {
    const pulse = 0.4 + Math.sin(state.clock.elapsedTime * 6) * 0.4;

    if (lineVaultRef.current) lineVaultRef.current.material.opacity = pulseActive ? pulse + 0.2 : 0.35;
    if (lineSlmRef.current) lineSlmRef.current.material.opacity = pulseActive ? pulse + 0.2 : 0.35;
    if (lineCloudRef.current) lineCloudRef.current.material.opacity = pulseActive ? pulse + 0.2 : 0.35;

    const active = particles.current;
    for (let i = active.length - 1; i >= 0; i--) {
      active[i].t += delta / TRAVEL_SECONDS;
      if (active[i].t >= 1) active.splice(i, 1);
    }

    particleRefs.current.forEach((mesh, index) => {
      if (!mesh) return;
      const p = active[index];
      if (!p) {
        mesh.visible = false;
        return;
      }
      mesh.visible = true;
      const [fx, fy, fz] = p.from;
      const [tx, ty, tz] = p.to;
      const arc = Math.sin(Math.PI * p.t) * 1.5;
      mesh.position.set(
        fx + (tx - fx) * p.t,
        fy + (ty - fy) * p.t + arc,
        fz + (tz - fz) * p.t
      );
      mesh.material.color.set(p.color);
      mesh.material.opacity = p.t < 0.8 ? 1 : 1 - (p.t - 0.8) / 0.2;
      mesh.scale.setScalar(0.9 + Math.sin(p.t * Math.PI) * 0.7);
    });
  });

  return (
    <group>
      {/* 1. Conduit Pathway to Memory Vault (Warden [0,0] -> Memory Vault [-10, 0]) */}
      <mesh ref={lineVaultRef} position={[-5, 0.04, 0]}>
        <boxGeometry args={[10, 0.05, 0.35]} />
        <meshBasicMaterial color="#00ffcc" transparent opacity={0.35} />
      </mesh>

      {/* 2. Conduit Pathway to Local SLM (Warden [0,0] -> Local SLM [10, -5]) */}
      <mesh
        ref={lineSlmRef}
        position={[5, 0.04, -2.5]}
        rotation={[0, -Math.atan2(5, 10), 0]}
      >
        <boxGeometry args={[Math.hypot(10, 5), 0.05, 0.35]} />
        <meshBasicMaterial color="#ff6600" transparent opacity={0.35} />
      </mesh>

      {/* 3. Conduit Pathway to Cloud Fortress (Warden [0,0] -> Cloud Fortress [10, 5]) */}
      <mesh
        ref={lineCloudRef}
        position={[5, 0.04, 2.5]}
        rotation={[0, Math.atan2(5, 10), 0]}
      >
        <boxGeometry args={[Math.hypot(10, 5), 0.05, 0.35]} />
        <meshBasicMaterial color="#aa00ff" transparent opacity={0.35} />
      </mesh>

      {/* Travelling Energy Sparks along conduits */}
      {Array.from({ length: POOL_SIZE }).map((_, i) => (
        <mesh
          key={i}
          ref={(el) => {
            particleRefs.current[i] = el;
          }}
          visible={false}
        >
          <sphereGeometry args={[0.2, 10, 10]} />
          <meshBasicMaterial color="#ffffff" transparent opacity={1} />
        </mesh>
      ))}
    </group>
  );
}
