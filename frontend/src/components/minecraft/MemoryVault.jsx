import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';

// File Cabinet Block Vault (Semantic Cache / RedisVL / Qdrant Memory Store)
export default function MemoryVault({ hit = false, position = [-5, 0, 0] }) {
  const glowRef = useRef();

  useFrame((state, delta) => {
    if (glowRef.current && hit) {
      glowRef.current.material.emissiveIntensity = 1.0 + Math.sin(state.clock.elapsedTime * 8) * 0.5;
    }
  });

  return (
    <group position={position}>
      {/* Vault Pedestal Slab */}
      <mesh position={[0, 0.25, 0]}>
        <boxGeometry args={[2.2, 0.5, 2.0]} />
        <meshStandardMaterial color="#1f2937" roughness={0.8} />
      </mesh>

      {/* Heavy Steel File Cabinet Body */}
      <mesh ref={glowRef} position={[0, 1.6, 0]}>
        <boxGeometry args={[1.6, 2.2, 1.4]} />
        <meshStandardMaterial
          color={hit ? '#10b981' : '#374151'}
          emissive={hit ? '#059669' : '#064e3b'}
          emissiveIntensity={hit ? 1.0 : 0.1}
          metalness={0.5}
          roughness={0.4}
        />
      </mesh>

      {/* 4 Stacked Vault File Drawers */}
      {[-0.6, -0.2, 0.2, 0.6].map((yOffset, i) => (
        <group key={i} position={[0, 1.6 + yOffset, 0.72]}>
          {/* Drawer Face Block */}
          <mesh>
            <boxGeometry args={[1.3, 0.32, 0.06]} />
            <meshStandardMaterial color="#4b5563" metalness={0.6} roughness={0.3} />
          </mesh>
          {/* Golden Pull Handle */}
          <mesh position={[0, 0, 0.05]}>
            <boxGeometry args={[0.35, 0.08, 0.06]} />
            <meshStandardMaterial
              color="#fbbf24"
              emissive="#d97706"
              emissiveIntensity={hit ? 0.8 : 0.2}
              metalness={0.8}
            />
          </mesh>
        </group>
      ))}

      {/* Vault Status Beacon / Emerald Memory Crystal */}
      <mesh position={[0, 3.0, 0]}>
        <boxGeometry args={[0.5, 0.5, 0.5]} />
        <meshStandardMaterial
          color="#34d399"
          emissive="#10b981"
          emissiveIntensity={hit ? 2.0 : 0.5}
          wireframe={!hit}
        />
      </mesh>
    </group>
  );
}
