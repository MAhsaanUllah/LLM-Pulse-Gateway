import React from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import VoxelTerrain from './VoxelTerrain';
import WardenTower from './WardenTower';
import MemoryVault from './MemoryVault';
import ModelStations from './ModelStations';
import RedstoneConduits from './RedstoneConduits';

/**
 * Main 3D Voxel Scene for LLM Pulse Gateway
 * Renders:
 * - Minecraft-style blocky terrain with elevation
 * - Central Warden Control Tower
 * - File Cabinet Vault (Semantic Cache)
 * - Model Fortress (Local SLM Bunkers + Cloud Bastion)
 * - Pulsing Redstone signal conduits
 */
export default function VoxelCanvas({ telemetry = {} }) {
  const { activeDestination, isProcessing } = telemetry;

  return (
    <div className="relative w-full h-full min-h-[500px] bg-[#0a0d14] overflow-hidden select-none">
      <Canvas
        shadows
        camera={{ position: [0, 11, 14], fov: 45 }}
        gl={{ antialias: true }}
      >
        {/* Atmosphere & Lighting */}
        <color attach="background" args={['#070a10']} />
        <fog attach="fog" args={['#070a10', 14, 30]} />

        <ambientLight intensity={0.4} />
        <pointLight position={[0, 9, 0]} intensity={1.8} color="#38bdf8" distance={20} />
        <directionalLight
          position={[10, 16, 8]}
          intensity={1.2}
          color="#ffffff"
          castShadow
        />

        {/* 1. Procedural Minecraft-style blocky voxel terrain */}
        <VoxelTerrain gridSize={16} />

        {/* 2. Central Warden Control Tower */}
        <WardenTower active={isProcessing} position={[0, 0, 0]} />

        {/* 3. File Cabinet Vault (Semantic Cache) */}
        <MemoryVault hit={activeDestination === 'memory_vault'} position={[-5, 0, 0]} />

        {/* 4. Model Fortress (Local SLM + Cloud Bastion) */}
        <ModelStations activeStation={activeDestination} />

        {/* 5. Glowing Redstone Conduit trails */}
        <RedstoneConduits pulseActive={isProcessing} />

        {/* Camera Controls */}
        <OrbitControls
          makeDefault
          enablePan={false}
          minDistance={8}
          maxDistance={22}
          maxPolarAngle={Math.PI / 2.15}
        />
      </Canvas>
    </div>
  );
}
