import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';

/** Separate model stations: Blast Furnace (local SLM) + Nether Portal (cloud fortress). */
export default function ModelStations({ activeStation = null }) {
  const { scene: slmScene }   = useGLTF('/models/local_slm.glb');
  const { scene: cloudScene } = useGLTF('/models/cloud_fortress.glb');

  const slmRef   = useRef();
  const cloudRef = useRef();

  useFrame((state, delta) => {
    // Local SLM: slight bob when active
    if (slmRef.current) {
      if (activeStation === 'local_slm') {
        slmRef.current.position.y = Math.sin(state.clock.elapsedTime * 5) * 0.07;
      } else {
        slmRef.current.position.y = 0;
      }
    }
    // Cloud Fortress: slow Y rotation always, faster when active
    if (cloudRef.current) {
      cloudRef.current.rotation.y += delta * (activeStation === 'cloud_fortress' ? 1.8 : 0.3);
    }
  });

  return (
    <group>
      {/* Blast Furnace – Local SLM Outpost (spread far right-top) */}
      <group ref={slmRef} position={[10, 0, -5]}>
        <primitive object={slmScene.clone()} />
      </group>

      {/* Nether Portal – Cloud Fortress Citadel (spread far right-bottom) */}
      <group ref={cloudRef} position={[10, 0, 5]}>
        <primitive object={cloudScene.clone()} />
      </group>
    </group>
  );
}

useGLTF.preload('/models/local_slm.glb');
useGLTF.preload('/models/cloud_fortress.glb');
