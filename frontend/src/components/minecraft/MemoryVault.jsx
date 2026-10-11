import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';

/** Ender Chest-style Memory Vault from Blender. Bounces when cache hit active. */
export default function MemoryVault({ hit = false, position = [-5, 0, 0] }) {
  const { scene } = useGLTF('/models/memory_vault.glb');
  const ref = useRef();

  useFrame((state) => {
    if (ref.current && hit) {
      ref.current.position.y = position[1] + Math.abs(Math.sin(state.clock.elapsedTime * 6)) * 0.25;
    } else if (ref.current) {
      ref.current.position.y = position[1];
    }
  });

  return (
    <group ref={ref} position={position}>
      <primitive object={scene.clone()} />
    </group>
  );
}

useGLTF.preload('/models/memory_vault.glb');
