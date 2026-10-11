import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';

/**
 * Model Fortress (Local SLM + Cloud Bastion) imported directly from Blender .glb export
 */
export default function ModelStations({ activeStation = null, position = [5, 0, 0] }) {
  const { scene } = useGLTF('/models/model_fortress.glb');
  const groupRef = useRef();

  useFrame((state, delta) => {
    if (groupRef.current && activeStation) {
      // Subtle pulse when a model route is active
      groupRef.current.position.y = Math.sin(state.clock.elapsedTime * 3) * 0.05;
    }
  });

  return (
    <group ref={groupRef} position={position}>
      <primitive object={scene.clone()} scale={[1, 1, 1]} />
    </group>
  );
}

useGLTF.preload('/models/model_fortress.glb');
