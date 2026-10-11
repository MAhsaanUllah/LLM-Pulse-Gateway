import React from 'react';

export default function MemoryVault({ hit = false, position = [-4, 0, 0] }) {
  return (
    <group position={position}>
      {/* File Cabinet Body */}
      <mesh position={[0, 1, 0]}>
        <boxGeometry args={[1.5, 2, 1.5]} />
        <meshStandardMaterial 
          color={hit ? "#2ecc71" : "#2c3e50"} 
          emissive={hit ? "#27ae60" : "#000000"}
          emissiveIntensity={hit ? 0.6 : 0.0}
        />
      </mesh>

      {/* Drawer Segments */}
      {[-0.4, 0.1, 0.6].map((yOffset, i) => (
        <mesh key={i} position={[0, 1 + yOffset, 0.76]}>
          <boxGeometry args={[1.2, 0.35, 0.05]} />
          <meshStandardMaterial color="#7f8c8d" metalness={0.6} roughness={0.3} />
        </mesh>
      ))}
    </group>
  );
}
