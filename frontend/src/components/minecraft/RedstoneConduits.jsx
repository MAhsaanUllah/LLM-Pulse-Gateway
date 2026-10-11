import React, { useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';

// Anchor nodes the redstone signals travel between (must match the voxel scene layout).
const NODES = {
  warden_tower: [0, 2.8, 0],
  memory_vault: [-5, 1.6, 0],
  local_slm: [5, 2.0, -3],
  cloud_fortress: [5, 3.2, 3],
};

const EVENT_COLORS = {
  CACHE_HIT: '#55ff55',
  CACHE_MISS: '#ffaa00',
  ROUTING_SIGNAL: '#ff0044',
  MODEL_EXECUTION: '#00e5ff',
  EVALUATION: '#ffff55',
  COMPLETION: '#ff55ff',
  ERROR: '#ff2222',
};

const POOL_SIZE = 16;
const TRAVEL_SECONDS = 1.1;

const nodeAt = (name) => NODES[name] || NODES.warden_tower;

export default function RedstoneConduits({ pulseActive = false, signal = null }) {
  const lineRef = useRef();
  const particleRefs = useRef([]);
  const particles = useRef([]);

  // Spawn one travelling particle per incoming telemetry packet.
  useEffect(() => {
    if (!signal) return;
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
    if (lineRef.current && pulseActive) {
      lineRef.current.material.opacity = 0.5 + Math.sin(state.clock.elapsedTime * 8) * 0.5;
    }

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
      const arc = Math.sin(Math.PI * p.t) * 1.2; // lift the signal mid-flight
      mesh.position.set(
        fx + (tx - fx) * p.t,
        fy + (ty - fy) * p.t + arc,
        fz + (tz - fz) * p.t
      );
      mesh.material.color.set(p.color);
      mesh.material.opacity = p.t < 0.75 ? 1 : 1 - (p.t - 0.75) / 0.25;
      mesh.scale.setScalar(0.8 + Math.sin(p.t * Math.PI) * 0.9);
    });
  });

  return (
    <group>
      {/* Floor Redstone Conduits */}
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[10, 10]} />
        <meshStandardMaterial color="#111827" roughness={0.9} />
      </mesh>

      {/* Pulsing Redstone Pathway to Memory Vault */}
      <mesh ref={lineRef} position={[-2.5, 0.3, 0]}>
        <boxGeometry args={[5, 0.06, 0.24]} />
        <meshBasicMaterial color="#ff0044" transparent opacity={pulseActive ? 0.9 : 0.3} />
      </mesh>

      {/* Pathway to Model Fortress */}
      <mesh position={[2.5, 0.3, 0]}>
        <boxGeometry args={[5, 0.06, 0.24]} />
        <meshBasicMaterial color="#ff3366" transparent opacity={0.4} />
      </mesh>

      {/* Glowing redstone particle signals travelling the conduits */}
      {Array.from({ length: POOL_SIZE }).map((_, i) => (
        <mesh
          key={i}
          ref={(el) => {
            particleRefs.current[i] = el;
          }}
          visible={false}
        >
          <sphereGeometry args={[0.14, 10, 10]} />
          <meshBasicMaterial color="#ff0044" transparent opacity={1} />
        </mesh>
      ))}
    </group>
  );
}
