import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';

export default function WardenTower({ active = false, position = [0, 0, 0] }) {
  const meshRef = useRef();

  useFrame((state, delta) => {
    if (meshRef.current && active) {
      meshRef.current.rotation.y += delta * 1.5;
    }
  });

  return (
    <group position={position}>
      {/* Central Base Block */}
      <mesh position={[0, 0.5, 0]}>
        <boxGeometry args={[2, 1, 2]} />
        <meshStandardMaterial color="#1a252c" roughness={0.8} />
      </mesh>

      {/* Warden Tower Spire */}
      <mesh ref={meshRef} position={[0, 2.5, 0]}>
        <boxGeometry args={[1.2, 3, 1.2]} />
        <meshStandardMaterial 
          color={active ? "#00ffff" : "#0d5c75"} 
          emissive={active ? "#00a8a8" : "#02242b"}
          emissiveIntensity={active ? 0.8 : 0.2}
          roughness={0.4}
        />
      </mesh>

      {/* Warden Sensor Antenna */}
      <mesh position={[0, 4.3, 0]}>
        <boxGeometry args={[0.4, 0.6, 0.4]} />
        <meshStandardMaterial color="#00ffff" emissive="#00ffff" emissiveIntensity={1} />
      </mesh>
    </group>
  );
}
