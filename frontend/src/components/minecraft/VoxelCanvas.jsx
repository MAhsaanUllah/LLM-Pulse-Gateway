import React from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import VoxelTerrain from './VoxelTerrain';
import WardenTower from './WardenTower';
import MemoryVault from './MemoryVault';
import ModelStations from './ModelStations';
import RedstoneConduits from './RedstoneConduits';
import SignalMessenger from './SignalMessenger';

/**
 * Main 3D Voxel Scene for LLM Pulse Gateway
 * Buildings are spread far apart; Allay messengers travel between them.
 *
 * Layout (top-down):
 *
 *        [-10, 0]          [0, 0]          [10, -5]
 *       Memory Vault  <-- Warden Tower --> Local SLM
 *                                 \------> Cloud Fortress [10, 5]
 */
export default function VoxelCanvas({ telemetry = {} }) {
  const { activeDestination, isProcessing, vaultHit, signal } = telemetry;

  return (
    <div className="relative w-full h-full min-h-[500px] bg-[#0a0d14] overflow-hidden select-none">
      <Canvas
        shadows
        camera={{ position: [0, 18, 22], fov: 50 }}
        gl={{ antialias: true }}
      >
        {/* Atmosphere */}
        <color attach="background" args={['#060810']} />
        <fog attach="fog" args={['#060810', 18, 50]} />

        {/* Lighting */}
        <ambientLight intensity={0.35} />
        <pointLight position={[0, 12, 0]}   intensity={2.0} color="#38bdf8" distance={30} />
        <pointLight position={[-10, 8, 0]}  intensity={1.2} color="#55ff99" distance={20} />
        <pointLight position={[10, 8, -4]}  intensity={1.0} color="#ff8844" distance={20} />
        <pointLight position={[10, 8, 5]}   intensity={1.2} color="#aa44ff" distance={20} />
        <directionalLight position={[12, 20, 8]} intensity={1.0} color="#ffffff" castShadow />

        {/* Terrain — wider grid to fill the spread */}
        <VoxelTerrain gridSize={28} />

        {/* ── TOWERS (spread far apart) ─────────────────────────── */}

        {/* 1. Central Warden Control Tower  [0, 0, 0] */}
        <WardenTower active={isProcessing} position={[0, 0, 0]} />

        {/* 2. Memory Vault — far left  [-10, 0, 0] */}
        <MemoryVault hit={vaultHit} position={[-10, 0, 0]} />

        {/* 3. Local SLM + Cloud Fortress — far right (handled internally) */}
        <ModelStations activeStation={activeDestination} />

        {/* ── REDSTONE CONDUITS (ground trails between towers) ─── */}
        <RedstoneConduits pulseActive={isProcessing} signal={signal} />

        {/* ── SIGNAL MESSENGER (flying Allay character) ────────── */}
        <SignalMessenger signal={signal} />

        {/* Camera Controls */}
        <OrbitControls
          makeDefault
          enablePan={false}
          minDistance={10}
          maxDistance={40}
          maxPolarAngle={Math.PI / 2.1}
        />
      </Canvas>
    </div>
  );
}
