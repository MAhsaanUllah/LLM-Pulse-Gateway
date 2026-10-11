import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';

// Central Warden Control Tower (Sculk/Obsidian aesthetic with pulsing sensor horns)
export default function WardenTower({ active = false, position = [0, 0, 0] }) {
  const coreRef = useRef();
  const antennaLeftRef = useRef();
  const antennaRightRef = useRef();

  useFrame((state, delta) => {
    if (coreRef.current) {
      // Idle float & rotation
      coreRef.current.rotation.y += delta * (active ? 2.5 : 0.6);
    }
    if (antennaLeftRef.current && antennaRightRef.current && active) {
      const pulse = Math.sin(state.clock.elapsedTime * 6) * 0.15;
      antennaLeftRef.current.rotation.z = 0.2 + pulse;
      antennaRightRef.current.rotation.z = -0.2 - pulse;
    }
  });

  return (
    <group position={position}>
      {/* Bedrock / Deepslate Foundation Base */}
      <mesh position={[0, 0.4, 0]}>
        <boxGeometry args={[2.4, 0.8, 2.4]} />
        <meshStandardMaterial color="#0b1325" roughness={0.9} />
      </mesh>

      {/* Sculk Catalyst Pedestal */}
      <mesh position={[0, 1.2, 0]}>
        <boxGeometry args={[1.8, 0.8, 1.8]} />
        <meshStandardMaterial color="#0f2b38" roughness={0.7} />
      </mesh>

      {/* Main Warden Spire Tower */}
      <mesh ref={coreRef} position={[0, 2.8, 0]}>
        <boxGeometry args={[1.2, 2.4, 1.2]} />
        <meshStandardMaterial
          color={active ? '#00ffff' : '#083344'}
          emissive={active ? '#06b6d4' : '#02242b'}
          emissiveIntensity={active ? 1.2 : 0.3}
          roughness={0.3}
          metalness={0.2}
        />
      </mesh>

      {/* Warden Sensor Antennas / Horns */}
      <mesh ref={antennaLeftRef} position={[-0.7, 4.2, 0]} rotation={[0, 0, 0.2]}>
        <boxGeometry args={[0.3, 0.8, 0.3]} />
        <meshStandardMaterial
          color="#00ffff"
          emissive="#00ffff"
          emissiveIntensity={active ? 1.5 : 0.6}
        />
      </mesh>

      <mesh ref={antennaRightRef} position={[0.7, 4.2, 0]} rotation={[0, 0, -0.2]}>
        <boxGeometry args={[0.3, 0.8, 0.3]} />
        <meshStandardMaterial
          color="#00ffff"
          emissive="#00ffff"
          emissiveIntensity={active ? 1.5 : 0.6}
        />
      </mesh>

      {/* Central Soul Core Heart Block */}
      <mesh position={[0, 2.8, 0.62]}>
        <boxGeometry args={[0.5, 0.5, 0.1]} />
        <meshStandardMaterial
          color="#38bdf8"
          emissive="#38bdf8"
          emissiveIntensity={active ? 2.0 : 0.8}
        />
      </mesh>
    </group>
  );
}
