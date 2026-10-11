import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';

/**
 * Warden Tower Model imported directly from Blender .glb export
 * With live telemetry reactivity on rotation & emission glow
 */
export default function WardenTower({ active = false, position = [0, 0, 0] }) {
  const { scene } = useGLTF('/models/warden_tower.glb');
  const groupRef = useRef();

  useFrame((state, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * (active ? 2.0 : 0.4);
    }
  });

  return (
    <group ref={groupRef} position={position}>
      <primitive object={scene.clone()} scale={[1, 1, 1]} />
    </group>
  );
}

useGLTF.preload('/models/warden_tower.glb');
