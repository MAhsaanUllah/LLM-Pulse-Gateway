"""
LLM Pulse Gateway - Real Minecraft-Style 3D Asset Generator
============================================================
Generates 4 authentic Minecraft-aesthetic GLB assets:

1. warden_tower.glb  - Sculk Warden with body, ribcage, horns, soul lantern
2. memory_vault.glb  - Ender Chest with obsidian frame, lid, teal rune
3. local_slm.glb     - Blast Furnace block with ore details and chimney
4. cloud_fortress.glb- Obsidian Nether Portal frame with swirling portal plate

All built from multi-block cube primitives with Minecraft-accurate proportions,
PBR materials, and glowing emission passes.
"""

import bpy
import math
import os
from pathlib import Path


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for col in [bpy.data.objects, bpy.data.meshes, bpy.data.materials]:
        for item in list(col):
            col.remove(item, do_unlink=True)


def mat(name, base, roughness=0.8, metallic=0.0, emit=None, emit_str=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    if emit:
        # Blender 4+ uses "Emission Color" + "Emission Strength"
        for key in ("Emission Color", "Emission"):
            if key in b.inputs:
                b.inputs[key].default_value = (*emit, 1.0)
                break
        b.inputs["Emission Strength"].default_value = emit_str
    return m


def box(name, loc, size, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    return o


def export(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=False,
        export_apply=True,
    )
    print(f"[GLB] {path}")


# ──────────────────────────────────────────────────────────────────
# 1. WARDEN TOWER
#    Sculk anatomy: feet, torso, ribcage stripes, shoulder pads,
#    neck, head, horns (left/right), soul lantern chest plate.
# ──────────────────────────────────────────────────────────────────

def build_warden_tower(out):
    reset()

    # Materials
    sculk_dark   = mat("sculk_dark",    (0.02, 0.08, 0.12))
    sculk_body   = mat("sculk_body",    (0.03, 0.14, 0.18), roughness=0.6)
    sculk_rib    = mat("sculk_rib",     (0.06, 0.22, 0.28), roughness=0.5)
    sculk_pad    = mat("sculk_pad",     (0.08, 0.30, 0.38), roughness=0.4)
    soul_blue    = mat("soul_blue",     (0.05, 0.55, 1.00), roughness=0.2,
                       emit=(0.05, 0.60, 1.00), emit_str=4.0)
    horn_tip     = mat("horn_tip",      (0.04, 0.40, 0.55), roughness=0.3,
                       emit=(0.04, 0.70, 0.90), emit_str=2.0)
    obsidian     = mat("obsidian",      (0.04, 0.03, 0.08), roughness=0.85)

    # Base platform (obsidian slab)
    box("base_slab",    (0, 0, 0.25),  (3.0, 3.0, 0.5),  obsidian)
    box("base_step",    (0, 0, 0.70),  (2.2, 2.2, 0.4),  sculk_dark)

    # Feet / legs
    box("foot_L",       (-0.55, 0, 1.15), (0.7, 0.6, 0.9), sculk_body)
    box("foot_R",       ( 0.55, 0, 1.15), (0.7, 0.6, 0.9), sculk_body)

    # Lower torso
    box("torso_lo",     (0, 0, 1.85),  (1.6, 0.9, 0.7),  sculk_body)

    # Ribcage stripes (4 horizontal plates giving cage look)
    for i, z in enumerate([2.35, 2.65, 2.95, 3.25]):
        box(f"rib_{i}",  (0, 0, z),   (1.8, 0.2, 0.18), sculk_rib)

    # Upper torso / chest block
    box("torso_hi",     (0, 0, 2.85),  (1.5, 0.85, 1.0), sculk_body)

    # Soul Lantern chest plate (glowing)
    box("soul_chest",   (0, 0.44, 2.85), (0.65, 0.08, 0.65), soul_blue)

    # Shoulder pads
    box("shoulder_L",   (-1.15, 0, 3.10), (0.55, 0.55, 0.55), sculk_pad)
    box("shoulder_R",   ( 1.15, 0, 3.10), (0.55, 0.55, 0.55), sculk_pad)

    # Arms
    box("arm_L",        (-1.30, 0, 2.50), (0.38, 0.38, 1.10), sculk_body)
    box("arm_R",        ( 1.30, 0, 2.50), (0.38, 0.38, 1.10), sculk_body)

    # Neck
    box("neck",         (0, 0, 3.70),  (0.7, 0.6, 0.45), sculk_body)

    # Head
    box("head",         (0, 0, 4.30),  (1.10, 0.9, 0.85), sculk_body)

    # Face soul glow (eye sockets)
    box("eye_L",        (-0.28, 0.46, 4.38), (0.22, 0.06, 0.16), soul_blue)
    box("eye_R",        ( 0.28, 0.46, 4.38), (0.22, 0.06, 0.16), soul_blue)

    # Horns (left side: two segments angled outward)
    box("horn_L1",  (-0.45, 0, 4.88), (0.18, 0.18, 0.55),
        sculk_rib, rot=(0,  0.25, 0.18))
    box("horn_L2",  (-0.68, 0, 5.30), (0.12, 0.12, 0.40),
        horn_tip, rot=(0,  0.40, 0.28))

    box("horn_R1",  ( 0.45, 0, 4.88), (0.18, 0.18, 0.55),
        sculk_rib, rot=(0, -0.25,-0.18))
    box("horn_R2",  ( 0.68, 0, 5.30), (0.12, 0.12, 0.40),
        horn_tip, rot=(0, -0.40,-0.28))

    export(out)


# ──────────────────────────────────────────────────────────────────
# 2. MEMORY VAULT  (Ender Chest aesthetics)
#    Obsidian outer frame, dark interior, glowing teal rune on lid,
#    metal lock hasp, 3-layer drawers inside.
# ──────────────────────────────────────────────────────────────────

def build_memory_vault(out):
    reset()

    obs   = mat("obs",       (0.04, 0.03, 0.08), roughness=0.85)
    lid   = mat("lid",       (0.06, 0.05, 0.12), roughness=0.75)
    rune  = mat("rune",      (0.10, 0.90, 0.80), roughness=0.15,
                emit=(0.10, 0.95, 0.85), emit_str=3.5)
    steel = mat("steel",     (0.55, 0.55, 0.60), roughness=0.3, metallic=0.9)
    inner = mat("inner",     (0.08, 0.06, 0.14), roughness=0.9)
    teal  = mat("teal",      (0.12, 0.70, 0.65), roughness=0.2,
                emit=(0.12, 0.75, 0.68), emit_str=2.0)

    # Base pedestal
    box("pedestal",   (0, 0, 0.20),   (2.4, 2.0, 0.40), obs)

    # Chest body (obsidian shell)
    box("chest_body", (0, 0, 0.85),   (2.0, 1.6, 0.90), obs)
    # Interior void face
    box("interior",   (0, 0.81, 0.85),(1.6, 0.06, 0.70), inner)

    # Lid (slightly open/raised for aesthetics)
    box("lid_block",  (0, 0, 1.42),   (2.0, 1.6, 0.28), lid)

    # Teal rune cross on lid face
    box("rune_h",     (0, 0.82, 1.42),(0.80, 0.04, 0.08), rune)
    box("rune_v",     (0, 0.82, 1.42),(0.08, 0.04, 0.40), rune)

    # Lock hasp (steel bracket)
    box("hasp",       (0, 0.82, 0.98),(0.28, 0.06, 0.24), steel)

    # Corner metal reinforcements
    corners = [(-0.88,-0.72), (-0.88, 0.72), (0.88,-0.72), (0.88, 0.72)]
    for ci, (cx, cy) in enumerate(corners):
        box(f"corner_{ci}", (cx, cy, 0.85), (0.18, 0.18, 0.90), steel)

    # 3 glowing drawer slots on the front
    for i, z in enumerate([0.58, 0.85, 1.12]):
        box(f"drawer_{i}",  (0, 0.82, z), (1.30, 0.04, 0.20), teal)

    export(out)


# ──────────────────────────────────────────────────────────────────
# 3. LOCAL SLM  (Blast Furnace Station)
#    Stone base, blast furnace body with face grate, orange glow
#    interior, iron chimney stack, coal ore blocks on sides.
# ──────────────────────────────────────────────────────────────────

def build_local_slm(out):
    reset()

    stone    = mat("stone",     (0.22, 0.21, 0.20), roughness=0.95)
    furnace  = mat("furnace",   (0.30, 0.28, 0.26), roughness=0.85)
    iron     = mat("iron",      (0.55, 0.52, 0.50), roughness=0.4, metallic=0.8)
    fire     = mat("fire",      (0.95, 0.42, 0.05), roughness=0.3,
                   emit=(1.00, 0.50, 0.05), emit_str=5.0)
    coal_ore = mat("coal_ore",  (0.14, 0.13, 0.12), roughness=0.9)
    coal_vein= mat("coal_vein", (0.05, 0.05, 0.05), roughness=1.0)
    grate    = mat("grate",     (0.18, 0.17, 0.16), roughness=0.8)
    smoke    = mat("smoke",     (0.40, 0.38, 0.38), roughness=0.9)

    # Base stone slab (2 layers)
    box("base1",     (0, 0, 0.20), (2.6, 2.6, 0.40), stone)
    box("base2",     (0, 0, 0.60), (2.0, 2.0, 0.40), stone)

    # Blast furnace body
    box("furnace_body",  (0, 0, 1.40), (1.8, 1.8, 1.6), furnace)

    # Glowing interior (fire mouth) – front face
    box("fire_mouth",    (0, 0.91, 1.25), (0.90, 0.06, 0.50), fire)
    # Inner glow halo
    box("fire_inner",    (0, 0.88, 1.25), (0.70, 0.04, 0.36), fire)

    # Iron grate bars (3 vertical bars over the mouth)
    for xi in [-0.28, 0, 0.28]:
        box(f"grate_{xi:.0f}",  (xi, 0.93, 1.25), (0.06, 0.04, 0.54), grate)

    # Coal ore decorations on left/right faces
    box("ore_L",  (-0.92, 0, 1.50), (0.06, 0.80, 0.60), coal_ore)
    box("ore_R",  ( 0.92, 0, 1.50), (0.06, 0.80, 0.60), coal_ore)
    # Ore veins
    box("vein_L",  (-0.93, 0, 1.55), (0.04, 0.30, 0.22), coal_vein)
    box("vein_R",  ( 0.93, 0, 1.45), (0.04, 0.30, 0.22), coal_vein)

    # Iron chimney stack (3 segments, narrowing)
    box("chimney1",  (0, 0, 2.45), (0.80, 0.80, 0.50), iron)
    box("chimney2",  (0, 0, 2.95), (0.64, 0.64, 0.40), iron)
    box("chimney3",  (0, 0, 3.35), (0.50, 0.50, 0.30), iron)
    # Chimney cap
    box("chimney_cap", (0, 0, 3.60), (0.70, 0.70, 0.14), iron)

    # Smoke puffs (lighter grey boxes above chimney)
    box("smoke1",  (0.10, 0.10, 3.82), (0.26, 0.26, 0.22), smoke)
    box("smoke2",  (-0.08, 0.05, 4.08),(0.18, 0.18, 0.18), smoke)
    box("smoke3",  (0.05,-0.08, 4.28), (0.12, 0.12, 0.14), smoke)

    export(out)


# ──────────────────────────────────────────────────────────────────
# 4. CLOUD FORTRESS  (Nether Portal Frame)
#    Chiseled obsidian corner pillars, top/bottom connecting beams,
#    glowing purple portal plate inside, crying obsidian accents.
# ──────────────────────────────────────────────────────────────────

def build_cloud_fortress(out):
    reset()

    obs       = mat("obs",      (0.04, 0.03, 0.08), roughness=0.85)
    cry_obs   = mat("cry_obs",  (0.14, 0.04, 0.22), roughness=0.75,
                    emit=(0.55, 0.10, 0.95), emit_str=1.0)
    portal    = mat("portal",   (0.38, 0.08, 0.75), roughness=0.15,
                    emit=(0.55, 0.10, 1.00), emit_str=6.0)
    gold_trim = mat("gold_trim",(0.80, 0.65, 0.05), roughness=0.35,
                    metallic=0.9, emit=(0.85, 0.70, 0.10), emit_str=0.6)

    # Ground stone base
    box("base_plinth",  (0, 0, 0.20),  (4.0, 2.0, 0.40), obs)

    # Portal frame: 4 corner pillars (full height)
    for lx, lz in [(-1.40, 0), (1.40, 0)]:
        for segment in range(5):    # 5 blocks tall per pillar
            bname = f"pillar_{lx:.0f}_{segment}"
            mat_to = cry_obs if segment % 2 == 1 else obs
            box(bname, (lx, 0, 0.60 + segment * 0.76), (0.54, 0.54, 0.72), mat_to)

    # Top horizontal beam
    box("beam_top",    (0, 0, 4.22),  (3.40, 0.54, 0.54), obs)
    # Bottom horizontal beam
    box("beam_bot",    (0, 0, 0.60),  (3.40, 0.54, 0.54), obs)

    # Gold corner trim blocks
    for lx in [-1.40, 1.40]:
        box(f"gold_top_{lx:.0f}",  (lx, 0, 4.22), (0.60, 0.60, 0.60), gold_trim)
        box(f"gold_bot_{lx:.0f}",  (lx, 0, 0.60), (0.60, 0.60, 0.60), gold_trim)

    # Purple portal fill plates (4 stacked tiles to fill interior)
    for i in range(4):
        box(f"portal_{i}", (0, 0.04, 1.40 + i * 0.68), (2.28, 0.06, 0.64), portal)

    # Crying obsidian drips on pillar faces
    for lx in [-1.40, 1.40]:
        for dz in [1.10, 2.00, 2.90]:
            box(f"drip_{lx:.0f}_{dz:.0f}", (lx, 0.28, dz), (0.10, 0.08, 0.28), cry_obs)

    export(out)


# ──────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    script_path  = Path(__file__).resolve()
    project_root = script_path.parent.parent.parent
    models_dir   = project_root / "frontend" / "public" / "models"

    print(f"[*] Project root : {project_root}")
    print(f"[*] Output dir   : {models_dir}")

    build_warden_tower  (models_dir / "warden_tower.glb")
    build_memory_vault  (models_dir / "memory_vault.glb")
    build_local_slm     (models_dir / "local_slm.glb")
    build_cloud_fortress(models_dir / "cloud_fortress.glb")

    print("\n[ALL MODELS GENERATED SUCCESSFULLY]")
