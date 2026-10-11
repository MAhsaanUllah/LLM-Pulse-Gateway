import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';

// Model Fortress: Houses both the Local SLM (Ollama) Outpost and the Cloud Fortress (OpenAI / Claude Citadel)
export default function ModelStations({ activeStation = null }) {
  const isLocalActive = activeStation === 'local_slm';
  const isCloudActive = activeStation === 'cloud_fortress';

  const cloudBeaconRef = useRef();
  const localCoreRef = useRef();

  useFrame((state, delta) => {
    if (cloudBeaconRef.current && isCloudActive) {
      cloudBeaconRef.current.rotation.y += delta * 2;
    }
    if (localCoreRef.current && isLocalActive) {
      localCoreRef.current.rotation.y += delta * 2.5;
    }
  });

  return (
    <group>
      {/* ========================================================
          1. LOCAL SLM OUTPOST (Ollama / Llama 3.2 Bronze Bunkers)
          ======================================================== */}
      <group position={[5, 0, -3]}>
        {/* Outpost Stone Base */}
        <mesh position={[0, 0.3, 0]}>
          <boxGeometry args={[2.4, 0.6, 2.4]} />
          <meshStandardMaterial color="#292524" roughness={0.9} />
        </mesh>

        {/* Forge Furnace / Local Engine Block */}
        <mesh position={[0, 1.1, 0]}>
          <boxGeometry args={[1.8, 1.0, 1.8]} />
          <meshStandardMaterial
            color={isLocalActive ? '#f97316' : '#7c2d12'}
            emissive={isLocalActive ? '#ea580c' : '#431407'}
            emissiveIntensity={isLocalActive ? 1.0 : 0.2}
            roughness={0.6}
          />
        </mesh>

        {/* Rotating Local Processing Core */}
        <mesh ref={localCoreRef} position={[0, 2.0, 0]}>
          <boxGeometry args={[0.8, 0.8, 0.8]} />
          <meshStandardMaterial
            color="#fb923c"
            emissive="#f97316"
            emissiveIntensity={isLocalActive ? 1.8 : 0.4}
          />
        </mesh>
      </group>

      {/* ========================================================
          2. CLOUD FORTRESS CITADEL (OpenAI / Claude Obsidian Bastion)
          ======================================================== */}
      <group position={[5, 0, 3]}>
        {/* Massive Fortress Foundation */}
        <mesh position={[0, 0.5, 0]}>
          <boxGeometry args={[3.2, 1.0, 3.2]} />
          <meshStandardMaterial color="#1e1b4b" roughness={0.8} />
        </mesh>

        {/* Bastion Lower Keep */}
        <mesh position={[0, 1.6, 0]}>
          <boxGeometry args={[2.4, 1.2, 2.4]} />
          <meshStandardMaterial
            color={isCloudActive ? '#9333ea' : '#3b0764'}
            emissive={isCloudActive ? '#7e22ce' : '#1e1b4b'}
            emissiveIntensity={isCloudActive ? 0.9 : 0.2}
            roughness={0.4}
          />
        </mesh>

        {/* Fortress Towers / Bastion Battlements */}
        {[
          [-1.0, 1.0],
          [1.0, 1.0],
          [-1.0, -1.0],
          [1.0, -1.0],
        ].map(([bx, bz], idx) => (
          <mesh key={idx} position={[bx, 2.6, bz]}>
            <boxGeometry args={[0.6, 1.2, 0.6]} />
            <meshStandardMaterial
              color="#581c87"
              emissive={isCloudActive ? '#a855f7' : '#2e1065'}
              emissiveIntensity={isCloudActive ? 1.0 : 0.2}
            />
          </mesh>
        ))}

        {/* Central Nether Portal Crystal / Cloud Beacon */}
        <mesh ref={cloudBeaconRef} position={[0, 3.2, 0]}>
          <boxGeometry args={[0.9, 1.4, 0.9]} />
          <meshStandardMaterial
            color="#c084fc"
            emissive="#a855f7"
            emissiveIntensity={isCloudActive ? 2.2 : 0.6}
            metalness={0.3}
            roughness={0.2}
          />
        </mesh>
      </group>
    </group>
  );
}
