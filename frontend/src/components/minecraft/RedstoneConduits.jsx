import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';

export default function RedstoneConduits({ pulseActive = false }) {
  const lineRef = useRef();

  useFrame((state, delta) => {
    if (lineRef.current && pulseActive) {
      lineRef.current.material.opacity = 0.5 + Math.sin(state.clock.elapsedTime * 8) * 0.5;
    }
  });

  return (
    <group>
      {/* Floor Redstone Conduits */}
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[10, 10]} />
        <meshStandardMaterial 
          color="#111827" 
          roughness={0.9} 
        />
      </mesh>

      {/* Pulsing Redstone Pathway to Memory Vault */}
      <mesh ref={lineRef} position={[-2, 0.05, 0]}>
        <boxGeometry args={[4, 0.05, 0.2]} />
        <meshBasicMaterial 
          color="#ff0044" 
          transparent 
          opacity={pulseActive ? 0.9 : 0.3} 
        />
      </mesh>

      {/* Pathway to Model Stations */}
      <mesh position={[2, 0.05, 0]}>
        <boxGeometry args={[4, 0.05, 0.2]} />
        <meshBasicMaterial 
          color="#ff3366" 
          transparent 
          opacity={0.4} 
        />
      </mesh>
    </group>
  );
}
