import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';

/** Sculk Warden Tower: full anatomy model from Blender. Active = slow rotation + cyan soul pulse. */
export default function WardenTower({ active = false, position = [0, 0, 0] }) {
  const { scene } = useGLTF('/models/warden_tower.glb');
  const ref = useRef();

  useFrame((_, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * (active ? 1.2 : 0.25);
    }
  });

  return (
    <group ref={ref} position={position} scale={active ? [1.05, 1.05, 1.05] : [1, 1, 1]}>
      <primitive object={scene.clone()} />
    </group>
  );
}

useGLTF.preload('/models/warden_tower.glb');
