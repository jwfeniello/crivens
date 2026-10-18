# Grabbed by the Ghoulies: animation and rig formats

Reverse-engineered from the game's own code (`default.xbe`, using the annotated Ghidra
project in luboise/ghoulies-decomp) and checked against the data: all 22,062 animations
decode with exact section-size checks, and the rigged exports pass the Khronos glTF validator
and render correctly in Blender.

Coordinates are **right-handed, Y-up, character facing +Z** (`LF_*` bones sit at +X), the same as
glTF. No mirroring is needed. Triangle winding is CCW (99.8% agree with the stored normals).

## Animation (`Anim` asset descriptor, magic `MINA`)

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | char[4] | `MINA` |
| 0x08 | f32 | duration (seconds) |
| 0x0C | u32 | offset of root-motion stream (0 = none) |
| 0x14 | u16 | number of bones the game reads |
| 0x18 | u16 | number of keyframes |
| 0x1C | u32 | precision bits: scale = 2^-(bits 8..12), pos = 2^-(bits 18..22), quat = 1/(2^((bits 23..27)-1)-1) |
| 0x24 | u32 | number of root-motion keyframes |
| 0x28 | u32 | offset of per-bone bitmask: parent-scale compensation |
| 0x40 | AnimStream | main stream |

**AnimStream** (at 0x40, or at the root-motion offset): `u16 header_size, u16 shorts_size,
u16 nibbles_size, u16 keyframe_size, f32`, then from stream+0x0C:
- **pack formats**, one per track, filling the space up to stream+header_size. There can be more tracks
  than the bone count, e.g. a carried prop.
- **base values**: i16[], at stream+header_size.
- **bit widths**: 4-bit nibbles, low nibble first, value = width-1.
- **keyframes**: `num_keyframes x keyframe_size` bytes. Every keyframe has the same bit layout,
  read LSB-first.

**Pack format byte** (rotation): 0x80/0x40/0x20 mean x/y/z present, 0x10/0x08/0x04 mean x/y/z
constant, 0x02 means a translation byte follows, 0x01 means a scale byte follows. Translation and
scale bytes use the same present/constant bits.
- Each present component takes one i16 base.
- Each non-constant component also takes one nibble (bit width) and that many bits from the
  keyframe. Value = (base + unsigned bits) * scale.
- Track order: rotation xyz, then translation xyz, then scale xyz.
- Quaternion w = sqrt(1 - x² - y² - z²), always >= 0. With no rotation components the
  rotation is identity.
- Final bone local transform = rotation, plus **bind position + translation**, times scale.
- Looping anims have `num_keyframes == duration*60` and wrap. Others space keyframes
  `duration/(n-1)` apart. The game interpolates linearly or with cubic curves.

## Models (`Model` asset descriptor)

`u32 footer_ptr, u32 footer_count`, then footer entries `(u32 type, u32 offset)`. Type 0 is the
mesh list (offsets inside it are relative to the MeshHeader). Type 7 is textures, type 9 is rigid
bone indices. The MeshHeader at +0x10 holds a key/value map whose entries give
**bone name -> bone index** (BASE, LF_H, LF_K, ..., HEAD, RT_S, RT_E, RT_W, ...).

Nodes (`ndHeader`, 0x20 bytes): name*, u16 type, u16 drawMask, ?, ?, ?, child*, sibling*, prev*.

| Node | Payload at +0x20 |
|---|---|
| ndSkeleton | u32 n, u32 ptr -> bones[n] (0x20 each: u16 parent (0xFFFF = root), u16 id, vec3 bind (local), vec3 global, u32) |
| ndVertexBuffer | u32 ptr, u32 n -> views (0x18: u8 stride, u8 type, u16, u32, u32, u32, u32 begin, u32 size) |
| ndMtxArray | entries* (8 bytes: u16 bone, u16, u8, u8 flag, u8 matrixIndex, u8), u32 count, ..., +0x2C matrices*, +0x30 count |
| ndRigidSkinIdx | u8* palette, u32 count |
| ndPushBuffer | u32 draws, ..., +0x30 index ptrs*, +0x34 prim types*, +0x38 counts* (u16 indices; 6 = tri strip) |
| ndBlendShape | ndVertexBuffer** list, u32 count: base buffer, then morph targets stored as **offsets**. +0x26 u8: 0 = blend on the GPU, else on the CPU |
| ndShaderParam2 | payload*: ps consts*, vs consts*, tex assigns* (28 bytes, u32 texture index first), counts..., +0x24 attrs* (16 bytes: name*, v1, v2) |

**Vertex stream types:** 9 = position f32x3, 10 = normal f32x3, 13 = UV f32x2,
0 = skin slots f32x2, 8 = skin weights f32x2, 11 = colour (4 bytes).

**Blend shapes (faces):** each target is a full vertex buffer with the same vertex count as the
base; its position (and normal) streams hold offsets from the base. The targets are named in the
MeshHeader key/value map as `MORPH_TARGET_<NAME>` (value = the target's weight slot, 4 bytes
apart in target order); the game looks them up by name (`MeshHeaderInstance::loadMorphTargets`).
Cooper's, in order: BLINK, ANGRY, ANGRY1, HIT, MOUTH_OPEN, SMILE, HIT1, HIT2, HAIR_SPIKE, SCARED,
RAISE_BROW, CHEEK_BLOW. On the GPU path (`ndBlendShape::update`) the 8 highest-weighted targets
are bound to the base buffer's empty stream slots 27-34 and added in the vertex shader, so only
positions are morphed there.

**Skinning:** a vertex's skin slot value is `24 + 3*slot`, because each matrix takes 3 shader
registers starting at c[0x78]. Its palette entry = `mtxArray.entries[palette[slot]]`, with up to
2 per vertex. Skin matrix = `boneWorld * translate(-global)`, so the inverse bind matrix is a
translation by -global (the bind pose has no rotation). What the entry's flag means
(`ndMtxArray::writeMatrices`):
- **flag 2:** use the bone's skin matrix directly. Vertices are in model space (e.g. Cooper).
- **flag 0:** `stored_matrix[matrixIndex] * bone`. The stored matrix (D3D row-vector, usually a pure
  translation) moves piece-local vertices to their pivot (e.g. skeletonbad). The exporter bakes
  `sum(w * v * M)` into model-space positions.
- **flag 1:** a static stored matrix with no bone.

Models can have dozens of resource chunks (`resource0..resource70`). Vertex and texture offsets
index their concatenation.

**Materials:** the diffuse texture is the slot named by the `colour0` attribute. Other texture slots
are Rare's cel ramp and lightmap. Flat colours (skin, lips) are the first non-white pixel-shader
constant, stored as RGBA bytes.

## Textures

Formats used: 0x0C DXT1, 0x0E DXT3, 0x12 linear A8R8G8B8, 0x1E linear X8R8G8B8. Linear
formats are **B,G,R,A in memory** and may have up to 64 bytes of trailing pitch padding. Textures
with size 0 are runtime render targets (screen captures for page-turn transitions) and contain
no pixels. The extractor needs bnl with these fixed (branch `fix/texture-formats-anim-keyframes`):
ARGB8 byte order (its output had blue = alpha), format 0x1E, pitch padding, and anim decoding
stopping at `num_keyframes`.

## Known gaps

- Root motion is baked onto the armature by default (`ghoul_gltf.py --no-root-motion` gives
  in-place animations). Locomotion cycles have none, because the game moves the actor itself.
- Per-bone parent-scale compensation flags are decoded but can't be represented in glTF.
- The Rare cel-shading ramp and lightmap textures aren't wired into the glTF materials.
