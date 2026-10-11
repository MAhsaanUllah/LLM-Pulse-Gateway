import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';

/**
 * Memory Vault (Semantic Cache) imported directly from Blender .glb export
 */
export default function MemoryVault({ hit = false, position = [-5, 0, 0] }) {
  const { scene } = useGLTF('/models/memory_vault.glb');
  const groupRef = useRef();

  useFrame((state) => {
    if (groupRef.current && hit) {
      groupRef.current.position.y = Math.sin(state.clock.elapsedTime * 4) * 0.1;
    }
  });

  return (
    <group ref={groupRef} position={position}>
      <primitive object={scene.clone()} scale={[1, 1, 1]} />
    </group>
  );
}

useGLTF.preload('/models/memory_vault.glb');
