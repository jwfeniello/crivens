# Modding

Everything here works on the USA disc (Redump: Grabbed by the Ghoulies (USA) (En,Fr,De,Es,It)).
Tested in xemu.

## Getting the disc files

Unpack the game partition of the ISO with xdvdfs (`xdvdfs unpack game.iso iso_root`). You need
an untouched copy of this folder; the build script reads from it and never writes to it.

## Building a mod disc

```
python -I tools/build_mod.py <mod_dir> <iso_root> <work_root> <out.iso> <extract-xiso.exe>
```

- `mod_dir` is your mod (layout below).
- `iso_root` is the untouched disc folder.
- `work_root` is a full copy of the disc folder that gets the changed bundles. Make it once
  (just copy `iso_root`). Bundles changed by an earlier build but not this one get restored from
  `iso_root`, so you can keep building into the same folder.
- The disc is packed with extract-xiso (XboxDev). Discs packed with `xdvdfs pack` boot to a black
  screen in xemu.

Mod folder layout (all optional):

```
scripts/<script asset name>.gscript         edited scene script (start from a dumped one)
textures/<model asset name>/<index>.png     replacement texture, same size as the original
assets/<asset name>/descriptor, resource0..  replace a whole asset (e.g. output of sonic_build.py)
```

Every bundle that contains a changed asset gets rebuilt with `ghoul_bnl.py`, so sizes can change.
An asset can be in more than one bundle (Cooper's model is in two); all of them get the change.

When testing in xemu, load your save with Continue rather than a snapshot. A snapshot already
has the old assets in memory.

## Scene scripts

```
python -I tools/ghoul_script.py dumpall <assets_dir> <out_dir>   every script as .gscript text
python -I tools/ghoul_script.py asm <in.gscript> <out.bin>
```

`assets_dir` is the extractor's output (see the README). The opcode list is in [SCRIPTS.md](SCRIPTS.md). Example: setting a room's title with
`SetSceneName`, or adding `CreateTimeLimitChallenge` to a room.

## Model rules (learned the hard way)

These are what `ghoul_modelwrite.py` follows. Breaking any of them crashes the game or draws
garbage.

- **Each resource chunk is its own allocation** (`XPhysicalAlloc`, 128-byte aligned, no limit on the
  number of chunks). Offsets in
  the descriptor index the concatenation of all chunks, but the game translates each one into a
  single chunk. So:
  - Vertex streams are offsets from the mesh base (footer type 0, +4; chunk 0 for Cooper) and
    must all be inside that one chunk. New vertex data goes at the end of chunk 0.
  - A texture can't span two chunks.
  - New textures go in a new last chunk (`Model.add_texture`), so nothing else moves.
- **Growing chunk 0 moves everything after it.** Every texture whose offset is past the old end of
  chunk 0 has to be shifted by the same amount.
- **Texture record** (64 bytes): u32 format, u32 0x1c, u16 width, u16 height, u32 flags (top byte =
  mip count), u32, **u32 resource offset (+0x14)**, **u32 size (+0x18)**.
- **Keep the node tree intact.** The game finds nodes like Cooper's face (`ndBlendShape`) at runtime.
  Unlinking one crashes on spawn. To hide geometry, zero its index lists instead
  (`Model.hide_blend_shape`), or put new geometry in it (`Model.write_face`).
- **Faces:** `Model.write_face` replaces the blend-shape head. Each vertex carries one position
  offset per morph target (`Vertex.deltas`, in `Model.morph_target_names()` order). The materials
  are the ndShaderParam2s inside the ndBlendShape subtree; its ndMtxArray gets its own palette.
- **Textures:** `Model.add_texture` adds a texture of any size and `Model.set_material_texture`
  points a material at it. `Model.replace_texture` overwrites one in place (same size, single-level
  DXT1). The byte at +0x0E registers a texture in a global texture bank; it's 0 on Cooper's, so
  copying one of his records as a template is fine.
- Each node has a slot in a per-instance runtime buffer (ndHeader +0x0C). MeshHeader +0 is the
  buffer size. New ndRigidSkinIdx / ndPushBuffer nodes take 4 bytes each.
- Draws go under the **blend** variant of an ndShader2 (2 bones per vertex). Skin slot floats are
  `24 + 3*slot`; palettes of up to 4 bones per draw are safe.

Checks before putting a model on a disc:

```
python -I tools/check_model.py <asset_dir>                 vertex views / textures inside their chunks
python -I tools/sim_load.py <bundle.bnl> <asset name>      reads the bundle the way the game does
python -I tools/tex_same.py <original_dir> <new_dir>       textures still land on the same data
python -I tools/ghoul_gltf.py <asset_dir> out.glb @anims.txt   then look at it in Blender
```

`regen_cooper.py` rebuilds Cooper's whole body through the writer. It looks identical in-game
and is a good first test after changing the writer.

## Replacing Cooper with another character

Cooper's animations are rotations plus translation *offsets* from each bone's bind position. The
bind positions live in the model's skeleton, so the skeleton can be moved to fit a new character
and every animation still works with the new proportions.

The Sonic example (I used Sonic Unleashed (Wii) rip from The Models Resource):

1. Export the mesh, weights and joints from the Collada file:
   ```
   blender -b --python blender/bl_sonic_export.py -- Sonic.DAE sonic.npz N100,N101,N104,N105,N106,N107,N108,N109,N114,N115
   ```
   The last argument picks the parts to keep. The rip has 12 hand poses and 2 mouths;
   `blender/bl_parts.py` renders every part so you can choose. The input can also be a .blend
   with shape keys (see Expressions below).
2. Build the model asset:
   ```
   python -I tools/sonic_build.py <Model__aid_model_ghoulies_actor_boy dir> sonic.npz <Textures dir> <out_dir> [height] [--fit-textures]
   ```
   This moves Cooper's skeleton onto Sonic's joints, maps Sonic's bones to Cooper's (table at the
   top of the script), writes the geometry, adds Sonic's three textures at full size on the
   materials that used Cooper's skin (11), jumper (8) and texture 7, and puts the head into
   Cooper's face mesh so the game drives its expressions. Height defaults to 21 (Cooper's height).
   `--fit-textures` shrinks the textures into Cooper's slots instead of adding new ones.
   `--no-face` keeps the head in the body and hides Cooper's face.
3. Copy `out_dir` to `<mod_dir>/assets/aid_model_ghoulies_actor_boy/` and build the disc.

### Expressions

Every triangle bound only to the head or eye bones goes into the face mesh. The pupils go on
Cooper's eye bones, so they follow his eye movement. The game picks Cooper's expressions by name,
so the new head needs a morph target for each one: BLINK, ANGRY, ANGRY1, HIT, MOUTH_OPEN, SMILE,
HIT1, HIT2, HAIR_SPIKE, SCARED, RAISE_BROW, CHEEK_BLOW. Render Cooper's with
`blender/bl_face_targets.py` to see what each one does.

`sonic_build.py` generates three of them: BLINK (a blue copy of each eye white sits just behind
it and moves out in front, and the pupils move back), MOUTH_OPEN (the mouth's lower half drops)
and HAIR_SPIKE (the quills fan out). To make the rest, sculpt them as shape keys:

```
blender -b --python blender/bl_face_template.py -- Sonic.DAE sonic_face.blend N100,N101,N104,N105,N106,N107,N108,N109,N114,N115
```

This saves the kept parts with an empty shape key per expression. Sculpt any of them, then give
the .blend to `bl_sonic_export.py` in place of the .DAE. A sculpted key replaces the generated
version (the eyelids still close on BLINK); keys left alone don't move anything.

For a different character, change the bone map, part list and material table in
`sonic_build.py`. Cooper's bones: BASE, BACK, BACK_A, NECK, HEAD, LF_/RT_ S E W (shoulder,
elbow, wrist), H K A T (hip, knee, ankle, toe), plus finger and eye bones. The character's
left is +X.
