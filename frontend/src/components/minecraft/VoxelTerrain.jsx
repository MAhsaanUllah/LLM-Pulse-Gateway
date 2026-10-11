import React, { useMemo } from 'react';

// Blocky Minecraft Voxel Terrain with elevation variation and stone/grass strata
// ponytail: using lightweight procedural cube grid instead of external voxel heightmap dependency
export default function VoxelTerrain({ gridSize = 14 }) {
  const blocks = useMemo(() => {
    const list = [];
    const half = Math.floor(gridSize / 2);

    for (let x = -half; x <= half; x++) {
      for (let z = -half; z <= half; z++) {
        // Skip central path holes for clean conduit visibility
        const distFromCenter = Math.sqrt(x * x + z * z);
        
        // Procedural stepped heights for authentic Minecraft rolling terrain
        let height = 0;
        let color = '#2d3748'; // deep stone base

        if (distFromCenter > 4.5) {
          // Outer hills with stepped grass blocks
          const step = Math.sin(x * 0.7) * Math.cos(z * 0.7);
          height = step > 0.3 ? 1 : (step > -0.2 ? 0 : -0.5);
          color = height >= 1 ? '#27ae60' : (height === 0 ? '#1f2937' : '#111827');
        } else {
          // Central plaza courtyard (cobblestone / sculk bedrock)
          height = 0;
          color = (x + z) % 2 === 0 ? '#1e293b' : '#0f172a';
        }

        list.push({
          key: `${x}_${z}`,
          position: [x, height * 0.5 - 0.25, z],
          color,
          height: height >= 1 ? 1.0 : 0.5,
        });
      }
    }
    return list;
  }, [gridSize]);

  return (
    <group>
      {blocks.map((block) => (
        <mesh key={block.key} position={block.position} receiveShadow>
          <boxGeometry args={[0.96, block.height, 0.96]} />
          <meshStandardMaterial
            color={block.color}
            roughness={0.9}
            metalness={0.1}
          />
        </mesh>
      ))}
    </group>
  );
}
