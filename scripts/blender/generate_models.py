"""
Automated Blender script for LLM Pulse Gateway.
Generates optimized 3D glTF/GLB voxel assets:
- warden_tower.glb: Central Warden Tower with horns and soul core
- memory_vault.glb: Semantic Cache File Cabinet with gold drawers
- local_slm.glb: Bronze Forge Outpost for local Ollama inference
- cloud_fortress.glb: Obsidian Citadel Bastion for cloud fallback
"""

import bpy
import os
import sys
import math

def reset_scene():
    """Clear default cube, camera, and lamp."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat, do_unlink=True)

def create_pbr_material(name, base_color, roughness=0.5, metallic=0.0, emission_color=(0,0,0,1), emission_strength=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        # Base color input
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = base_color
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        # Emission inputs for glowing blocks
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission_color
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = emission_color
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat

def add_box(name, location, size, material=None, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0] / 2.0, size[1] / 2.0, size[2] / 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    return obj

def export_glb(filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format='GLB',
        use_selection=False,
        export_apply=True
    )
    print(f"[SUCCESS] Exported: {filepath}")

# ==============================================================================
# 1. BUILD WARDEN TOWER
# ==============================================================================
def build_warden_tower(output_path):
    reset_scene()
    
    # Materials
    mat_deepslate = create_pbr_material("Deepslate", (0.05, 0.08, 0.12, 1), roughness=0.9)
    mat_sculk = create_pbr_material("SculkCatalyst", (0.04, 0.14, 0.18, 1), roughness=0.7)
    mat_spire = create_pbr_material("WardenSpire", (0.02, 0.40, 0.50, 1), roughness=0.3, emission_color=(0.0, 0.8, 1.0, 1), emission_strength=1.2)
    mat_soul = create_pbr_material("SoulCore", (0.1, 0.9, 1.0, 1), roughness=0.2, emission_color=(0.1, 0.9, 1.0, 1), emission_strength=3.0)
    
    # Base
    add_box("Base", (0, 0, 0.4), (2.4, 2.4, 0.8), mat_deepslate)
    add_box("Pedestal", (0, 0, 1.2), (1.8, 1.8, 0.8), mat_sculk)
    
    # Tower Spire
    add_box("Spire", (0, 0, 2.8), (1.2, 1.2, 2.4), mat_spire)
    
    # Horns
    add_box("HornLeft", (-0.7, 0, 4.2), (0.3, 0.3, 0.8), mat_soul, rotation=(0, 0.2, 0))
    add_box("HornRight", (0.7, 0, 4.2), (0.3, 0.3, 0.8), mat_soul, rotation=(0, -0.2, 0))
    
    # Glowing Soul Core
    add_box("CoreChest", (0, 0.62, 2.8), (0.5, 0.1, 0.5), mat_soul)
    
    export_glb(output_path)

# ==============================================================================
# 2. BUILD MEMORY VAULT (FILE CABINET)
# ==============================================================================
def build_memory_vault(output_path):
    reset_scene()
    
    mat_cabinet = create_pbr_material("SteelCabinet", (0.15, 0.20, 0.25, 1), roughness=0.4, metallic=0.6)
    mat_drawer = create_pbr_material("DrawerMetal", (0.25, 0.30, 0.35, 1), roughness=0.3, metallic=0.8)
    mat_gold = create_pbr_material("GoldHandle", (0.98, 0.75, 0.15, 1), roughness=0.2, metallic=0.9, emission_color=(1.0, 0.7, 0.1, 1), emission_strength=0.5)
    mat_emerald = create_pbr_material("EmeraldBeacon", (0.1, 0.9, 0.4, 1), roughness=0.1, emission_color=(0.1, 0.9, 0.4, 1), emission_strength=2.5)

    # Base slab
    add_box("VaultBase", (0, 0, 0.25), (2.2, 2.0, 0.5), mat_cabinet)
    # Main cabinet body
    add_box("VaultBody", (0, 0, 1.6), (1.6, 1.4, 2.2), mat_cabinet)

    # 4 Drawers with Gold Pull Handles
    for i, z in enumerate([0.7, 1.2, 1.7, 2.2]):
        add_box(f"Drawer_{i}", (0, 0.72, z), (1.3, 0.08, 0.36), mat_drawer)
        add_box(f"Handle_{i}", (0, 0.78, z), (0.35, 0.06, 0.08), mat_gold)

    # Emerald Crystal Beacon
    add_box("Beacon", (0, 0, 3.0), (0.5, 0.5, 0.5), mat_emerald, rotation=(0.785, 0.785, 0))

    export_glb(output_path)

# ==============================================================================
# 3. BUILD MODEL FORTRESS (LOCAL SLM & CLOUD BASTION)
# ==============================================================================
def build_model_fortress(output_path):
    reset_scene()

    # Local Outpost Materials
    mat_outpost_base = create_pbr_material("OutpostBase", (0.12, 0.10, 0.09, 1), roughness=0.9)
    mat_forge = create_pbr_material("ForgeBody", (0.7, 0.3, 0.1, 1), roughness=0.6, emission_color=(0.9, 0.4, 0.1, 1), emission_strength=1.0)
    mat_core = create_pbr_material("LocalCore", (1.0, 0.6, 0.2, 1), roughness=0.2, emission_color=(1.0, 0.6, 0.1, 1), emission_strength=2.5)

    # Cloud Citadel Materials
    mat_citadel_base = create_pbr_material("CitadelBase", (0.08, 0.07, 0.18, 1), roughness=0.8)
    mat_bastion = create_pbr_material("BastionKeep", (0.35, 0.10, 0.55, 1), roughness=0.4, emission_color=(0.5, 0.1, 0.8, 1), emission_strength=0.8)
    mat_portal = create_pbr_material("PortalBeacon", (0.7, 0.3, 0.95, 1), roughness=0.2, emission_color=(0.8, 0.4, 1.0, 1), emission_strength=3.0)

    # --- Local SLM Outpost (X: 0, Y: -3) ---
    add_box("SLM_Base", (0, -3, 0.3), (2.4, 2.4, 0.6), mat_outpost_base)
    add_box("SLM_Forge", (0, -3, 1.1), (1.8, 1.8, 1.0), mat_forge)
    add_box("SLM_Core", (0, -3, 2.0), (0.8, 0.8, 0.8), mat_core)

    # --- Cloud Citadel Bastion (X: 0, Y: 3) ---
    add_box("Cloud_Base", (0, 3, 0.5), (3.2, 3.2, 1.0), mat_citadel_base)
    add_box("Cloud_Keep", (0, 3, 1.6), (2.4, 2.4, 1.2), mat_bastion)

    # 4 Bastion Battlements
    for bx, by in [(-1, 2), (1, 2), (-1, 4), (1, 4)]:
        add_box(f"Tower_{bx}_{by}", (bx, by, 2.6), (0.6, 0.6, 1.2), mat_bastion)

    # Nether Portal Crystal Beacon
    add_box("PortalCrystal", (0, 3, 3.2), (0.9, 0.9, 1.4), mat_portal)

    export_glb(output_path)


if __name__ == "__main__":
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_script_dir, "..", ".."))
    models_dir = os.path.join(project_root, "frontend", "public", "models")

    print("[*] Project root:", project_root)
    print("[*] Target models directory:", models_dir)

    build_warden_tower(os.path.join(models_dir, "warden_tower.glb"))
    build_memory_vault(os.path.join(models_dir, "memory_vault.glb"))
    build_model_fortress(os.path.join(models_dir, "model_fortress.glb"))

    print("\n[ALL GLB MODELS GENERATED SUCCESSFULLY!]")
