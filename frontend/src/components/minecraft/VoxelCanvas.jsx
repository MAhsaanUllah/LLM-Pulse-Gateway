import React from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import WardenTower from './WardenTower';
import MemoryVault from './MemoryVault';
import ModelStations from './ModelStations';
import RedstoneConduits from './RedstoneConduits';

export default function VoxelCanvas({ telemetry = {} }) {
  const { activeDestination, isProcessing } = telemetry;

  return (
    <div style={{ width: '100%', height: '100%', minHeight: '500px', background: '#0a0d14' }}>
      <Canvas camera={{ position: [0, 8, 10], fov: 45 }}>
        <ambientLight intensity={0.6} />
        <pointLight position={[0, 10, 0]} intensity={1.5} color="#60a5fa" />
        <directionalLight position={[5, 10, 5]} intensity={1.0} />

        {/* Voxel Scene Sub-components */}
        <WardenTower active={isProcessing} position={[0, 0, 0]} />
        <MemoryVault hit={activeDestination === 'memory_vault'} position={[-4, 0, 0]} />
        <ModelStations activeStation={activeDestination} />
        <RedstoneConduits pulseActive={isProcessing} />

        <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.1} />
      </Canvas>
    </div>
  );
}
