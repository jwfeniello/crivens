<p align="center">
  <img width="600" alt="crivens" src="https://github.com/user-attachments/assets/3968ef1b-3441-4186-b5b3-c903605873cd" />
  <img width="110" alt="Crivens the butler" src="https://github.com/user-attachments/assets/1c017424-bcca-4670-8f39-02ae9b981297" />
</p>

Tools for taking apart and modding Grabbed by the Ghoulies (Xbox, 2003).

- Extract every asset: models, textures, animations, audio, video, text
- Export models to rigged, animated .glb (skinning, blend shapes, root motion) for Blender
- Disassemble and reassemble the scene scripts
- Rebuild .bnl bundles with any size changes and pack a bootable disc
- Write new geometry into character models, e.g. replacing Cooper with another character

<p align="center">
  <img width="49%" alt="Sonic replacing Cooper in the basement" src="https://github.com/user-attachments/assets/79a01a50-fc5e-40fd-8978-1e9e686ae143" />
  <img width="49%" alt="Sonic from behind in the basement" src="https://github.com/user-attachments/assets/57f6f11b-974a-48a7-9ece-7ab643946939" />
  <br>
  <em>Sonic swapped in for Cooper, running on xemu. How it's done: <a href="docs/MODDING.md#replacing-cooper-with-another-character">docs/MODDING.md</a></em>
</p>

Works with the USA disc. You need your own copy of the game; no game files are included.

## Extract everything

```
python -I extract_all.py "Grabbed by the Ghoulies (USA).iso" out
```

That unpacks the disc and writes:

| Folder | What's in it |
|---|---|
| `out/assets` | every bundle unpacked: models, textures as PNG, fonts, text |
| `out/rigged` | about 390 models as rigged, animated .glb (open in Blender) |
| `out/scripts` | every scene script as .gscript text |
| `out/audio` | all sound and music as WAV |
| `out/video` | all videos as MP4 |

You need Python 3.10+ with numpy and matplotlib, git, and [Rust](https://rustup.rs). Put these on
your PATH or in a folder you pass with `--tools DIR`:

- [xdvdfs](https://github.com/antangelo/xdvdfs/releases) (to read the ISO)
- [vgmstream-cli](https://github.com/vgmstream/vgmstream/releases) (audio)
- [ffmpeg](https://ffmpeg.org/download.html) (video)

The script downloads [luboise/bnl](https://github.com/luboise/bnl) and the asset name list from
[x1nixmzeng/project-grabbed](https://github.com/x1nixmzeng/project-grabbed) itself. `--no-av` skips
audio and video, `--no-glb` skips the model export. If something fails, fix it and run the same
command again; finished steps are skipped.

One model at a time:

```
python -I tools/ghoul_gltf.py <Model__... dir> out.glb <dir with Anim__... folders>
```

## Modding

See [docs/MODDING.md](docs/MODDING.md): building a mod disc, editing scripts and textures, the
rules for writing models, and the character swap.

## Docs

- [docs/FORMATS.md](docs/FORMATS.md): animation, model, skinning and texture formats
- [docs/SCRIPTS.md](docs/SCRIPTS.md): scene script VM and all 150 opcodes
- [docs/MODDING.md](docs/MODDING.md): mods and model writing

## Layout

| Folder | What's in it |
|---|---|
| `tools/` | Python: `ghoul_bnl` (bundles), `ghoul_model` / `ghoul_gltf` (models to glTF), `ghoul_anim` (animations), `ghoul_script` (scripts), `ghoul_dxt` (DXT1), `ghoul_modelwrite` (model writer), `build_mod`, checks |
| `extract/` | Rust extractor built on bnl. Extra bins: `anim_dump`, `anim_probe`, `model_textures` |
| `blender/` | Headless Blender scripts for render checks and the Sonic export |
| `ghidra_scripts/` | Headless Ghidra scripts used on the ghoulies-decomp project |
| `gltf_validator/` | Runs the Khronos validator over a folder (`npm i gltf-validator`) |

## Credits

- [luboise/bnl](https://github.com/luboise/bnl): the BNL bundle library everything started from
- [luboise/ghoulies-decomp](https://github.com/luboise/ghoulies-decomp): annotated Ghidra project of
  `default.xbe`. The animation, skinning, loader and script formats were worked out from it
- [x1nixmzeng/project-grabbed](https://github.com/x1nixmzeng/project-grabbed): asset name hashes
