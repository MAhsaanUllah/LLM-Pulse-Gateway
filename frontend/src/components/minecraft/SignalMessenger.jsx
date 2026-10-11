import React, { useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';

/**
 * SignalMessenger — Minecraft Allay-like character & glowing courier.
 * Features:
 * 1. Constant Courier (Scout): always patrolling between towers with flapping wings and light aura.
 * 2. Express Messengers: spawned dynamically whenever telemetry/routing events fire.
 */

export const TOWER_POSITIONS = {
  warden_tower:   [0,   2.5,  0],
  memory_vault:   [-10, 1.8,  0],
  local_slm:      [10,  2.0, -5],
  cloud_fortress: [10,  3.0,  5],
};

const PATROL_WAYPOINTS = [
  TOWER_POSITIONS.warden_tower,
  TOWER_POSITIONS.memory_vault,
  TOWER_POSITIONS.warden_tower,
  TOWER_POSITIONS.local_slm,
  TOWER_POSITIONS.cloud_fortress,
];

const EVENT_COLORS = {
  CACHE_HIT:       '#55ff55',
  CACHE_MISS:      '#ffaa00',
  ROUTING_SIGNAL:  '#ff0044',
  MODEL_EXECUTION: '#00e5ff',
  EVALUATION:      '#ffff55',
  COMPLETION:      '#ff55ff',
  ERROR:           '#ff2222',
};

const TRAVEL_TIME = 1.8;   // seconds for express event messenger
const MAX_POOL    = 8;

const nodeAt = (name) => TOWER_POSITIONS[name] || TOWER_POSITIONS.warden_tower;

export default function SignalMessenger({ signal = null }) {
  // Constant patrol courier ref
  const courierRef = useRef();
  const courierWingsRef = useRef({ left: null, right: null });
  const courierLightRef = useRef();

  // Dynamic express messengers
  const messengerRefs = useRef([]);
  const messengers = useRef([]);

  // Spawn express messenger on telemetry signal
  useEffect(() => {
    if (!signal || !signal.event) return;
    const color = EVENT_COLORS[signal.event] || '#00e5ff';
    messengers.current.push({
      from:  nodeAt(signal.source),
      to:    nodeAt(signal.destination),
      color,
      t:     0,
      key:   signal.id ?? Date.now(),
    });
    if (messengers.current.length > MAX_POOL) {
      messengers.current.splice(0, messengers.current.length - MAX_POOL);
    }
  }, [signal]);

  useFrame((state, delta) => {
    const time = state.clock.elapsedTime;

    // ──────────────────────────────────────────────────────────
    // 1. CONSTANT PATROL COURIER (Traveling between towers)
    // ──────────────────────────────────────────────────────────
    if (courierRef.current) {
      const loopTime = 16.0; // 16 seconds full round trip across all towers
      const progress = (time % loopTime) / loopTime;
      const totalSegments = PATROL_WAYPOINTS.length;
      const segmentFloat = progress * totalSegments;
      const segIndex = Math.floor(segmentFloat);
      const nextIndex = (segIndex + 1) % totalSegments;
      const segT = segmentFloat - segIndex;

      // Smooth step
      const smoothT = segT * segT * (3 - 2 * segT);

      const p1 = PATROL_WAYPOINTS[segIndex];
      const p2 = PATROL_WAYPOINTS[nextIndex];

      const arcH = Math.sin(Math.PI * smoothT) * 2.2 + Math.sin(time * 3) * 0.25;

      const cx = p1[0] + (p2[0] - p1[0]) * smoothT;
      const cy = p1[1] + (p2[1] - p1[1]) * smoothT + arcH;
      const cz = p1[2] + (p2[2] - p1[2]) * smoothT;

      courierRef.current.position.set(cx, cy, cz);

      // Facing direction of motion
      const dx = p2[0] - p1[0];
      const dz = p2[2] - p1[2];
      if (Math.hypot(dx, dz) > 0.01) {
        courierRef.current.rotation.y = Math.atan2(dx, dz);
      }

      // Flapping wings
      const flap = Math.sin(time * 16) * 0.7;
      if (courierWingsRef.current.left)  courierWingsRef.current.left.rotation.z = flap;
      if (courierWingsRef.current.right) courierWingsRef.current.right.rotation.z = -flap;

      // Light glow pulse
      if (courierLightRef.current) {
        courierLightRef.current.intensity = 2.5 + Math.sin(time * 6) * 1.0;
      }
    }

    // ──────────────────────────────────────────────────────────
    // 2. EXPRESS SIGNAL MESSENGERS (Telemetric query packets)
    // ──────────────────────────────────────────────────────────
    const active = messengers.current;
    for (let i = active.length - 1; i >= 0; i--) {
      active[i].t += delta / TRAVEL_TIME;
      if (active[i].t >= 1) active.splice(i, 1);
    }

    messengerRefs.current.forEach((group, idx) => {
      if (!group) return;
      const m = active[idx];
      if (!m) {
        group.visible = false;
        return;
      }

      group.visible = true;
      const [fx, fy, fz] = m.from;
      const [tx, ty, tz] = m.to;
      const t = m.t;

      const arcH = 4.0 * Math.sin(Math.PI * t);
      group.position.set(
        fx + (tx - fx) * t,
        fy + (ty - fy) * t + arcH,
        fz + (tz - fz) * t
      );

      group.rotation.y = Math.atan2(tx - fx, tz - fz);

      const opacity = t > 0.8 ? 1 - (t - 0.8) / 0.2 : 1;
      group.children.forEach((child) => {
        if (child.material) {
          child.material.opacity = opacity * 0.95;
          if (child.material.color && child.name === 'core') {
            child.material.color.set(m.color);
          }
        }
      });
    });
  });

  return (
    <group>
      {/* ───────────────────────────────────────────────────────
          MAIN COURIER CHARACTER (Allay / Fairy Golem)
          Always travels between towers with a glowing lantern light
          ─────────────────────────────────────────────────────── */}
      <group ref={courierRef} position={[0, 3, 0]}>
        {/* Glow Light on courier */}
        <pointLight
          ref={courierLightRef}
          color="#38bdf8"
          intensity={3.0}
          distance={8}
          decay={2}
        />

        {/* Head (Voxel Cube) */}
        <mesh position={[0, 0.38, 0]}>
          <boxGeometry args={[0.32, 0.32, 0.32]} />
          <meshStandardMaterial
            color="#38bdf8"
            emissive="#0284c7"
            emissiveIntensity={0.8}
            roughness={0.3}
          />
        </mesh>

        {/* Glowing Eyes */}
        <mesh position={[0.08, 0.38, 0.17]}>
          <boxGeometry args={[0.06, 0.06, 0.02]} />
          <meshBasicMaterial color="#ffffff" />
        </mesh>
        <mesh position={[-0.08, 0.38, 0.17]}>
          <boxGeometry args={[0.06, 0.06, 0.02]} />
          <meshBasicMaterial color="#ffffff" />
        </mesh>

        {/* Body (Voxel Torso) */}
        <mesh position={[0, 0.08, 0]}>
          <boxGeometry args={[0.26, 0.32, 0.20]} />
          <meshStandardMaterial
            color="#0ea5e9"
            emissive="#0369a1"
            emissiveIntensity={0.6}
            roughness={0.4}
          />
        </mesh>

        {/* Left Wing */}
        <mesh
          ref={(el) => { courierWingsRef.current.left = el; }}
          position={[0.22, 0.14, -0.06]}
        >
          <boxGeometry args={[0.32, 0.04, 0.24]} />
          <meshStandardMaterial
            color="#bae6fd"
            transparent
            opacity={0.85}
            emissive="#7dd3fc"
            emissiveIntensity={0.5}
          />
        </mesh>

        {/* Right Wing */}
        <mesh
          ref={(el) => { courierWingsRef.current.right = el; }}
          position={[-0.22, 0.14, -0.06]}
        >
          <boxGeometry args={[0.32, 0.04, 0.24]} />
          <meshStandardMaterial
            color="#bae6fd"
            transparent
            opacity={0.85}
            emissive="#7dd3fc"
            emissiveIntensity={0.5}
          />
        </mesh>

        {/* Glowing Soul Orb in hands (carries query payloads) */}
        <mesh position={[0, -0.08, 0.16]}>
          <boxGeometry args={[0.14, 0.14, 0.14]} />
          <meshBasicMaterial color="#67e8f9" />
        </mesh>
      </group>

      {/* ───────────────────────────────────────────────────────
          EXPRESS SIGNAL MESSENGERS (Spawned on Gateway events)
          ─────────────────────────────────────────────────────── */}
      {Array.from({ length: MAX_POOL }).map((_, i) => (
        <group
          key={i}
          ref={(el) => { messengerRefs.current[i] = el; }}
          visible={false}
        >
          <pointLight color="#ffffff" intensity={2.0} distance={5} />
          {/* Glowing particle body */}
          <mesh name="core">
            <boxGeometry args={[0.25, 0.25, 0.25]} />
            <meshBasicMaterial color="#00e5ff" transparent opacity={0.9} />
          </mesh>
          {/* Wings */}
          <mesh position={[0.2, 0, 0]}>
            <boxGeometry args={[0.18, 0.03, 0.22]} />
            <meshBasicMaterial color="#ffffff" transparent opacity={0.7} />
          </mesh>
          <mesh position={[-0.2, 0, 0]}>
            <boxGeometry args={[0.18, 0.03, 0.22]} />
            <meshBasicMaterial color="#ffffff" transparent opacity={0.7} />
          </mesh>
        </group>
      ))}
    </group>
  );
}
