import React from 'react';

export default function ModelStations({ activeStation = null }) {
  const isLocalActive = activeStation === 'local_slm';
  const isCloudActive = activeStation === 'cloud_fortress';

  return (
    <group>
      {/* Station 1: Local SLM (Ollama) Block */}
      <group position={[4, 0, -2]}>
        <mesh position={[0, 0.75, 0]}>
          <boxGeometry args={[1.5, 1.5, 1.5]} />
          <meshStandardMaterial 
            color={isLocalActive ? "#f39c12" : "#d35400"} 
            emissive={isLocalActive ? "#e67e22" : "#5a2300"}
            emissiveIntensity={isLocalActive ? 0.9 : 0.1}
          />
        </mesh>
      </group>

      {/* Station 2: Cloud Fortress (OpenAI / Anthropic) */}
      <group position={[4, 0, 2]}>
        <mesh position={[0, 1.5, 0]}>
          <boxGeometry args={[2, 3, 2]} />
          <meshStandardMaterial 
            color={isCloudActive ? "#9b59b6" : "#4a235a"} 
            emissive={isCloudActive ? "#8e44ad" : "#1a092b"}
            emissiveIntensity={isCloudActive ? 0.9 : 0.1}
          />
        </mesh>
      </group>
    </group>
  );
}
