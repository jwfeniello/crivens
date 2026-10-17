"""Build a playable Grabbed by the Ghoulies mod disc from a mod folder.

usage: python -I build_mod.py <mod_dir> <iso_root> <work_root> <out.iso> <extract-xiso.exe>

<mod_dir> layout (all optional):
  scripts/<script asset name>.gscript        e.g. aid_script_ghoulies_chapter1_scene1_2playcam.gscript
  textures/<model asset name>/<index>.png    e.g. aid_model_ghoulies_actor_boy/8.png (same size, DXT1)

<iso_root>  unmodified extracted disc (never written to)
<work_root> full copy of the disc that gets modded bundles; bundles changed by a previous build
            but not by this one are restored from <iso_root> (tracked in <work_root>.manifest.json,
            kept outside the disc folder)
Every bundle containing a modded asset is rebuilt from the original with ghoul_bnl, so sizes may
change freely. Then the disc is packed with extract-xiso (xdvdfs-packed discs don't boot).
"""
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_bnl as gb  # noqa: E402
import ghoul_dxt as dxt  # noqa: E402
import ghoul_script as gs  # noqa: E402

mod_dir, iso_root, work_root, out_iso, extract_xiso = map(Path, sys.argv[1:6])

# ---- collect the requested changes
script_mods = {p.stem: gs.asm(p.read_text()) for p in sorted((mod_dir / "scripts").glob("*.gscript"))}
tex_mods = {}
for d in sorted((mod_dir / "textures").glob("*")):
    if d.is_dir():
        tex_mods[d.name] = {int(p.stem): p for p in d.glob("*.png")}
wanted = set(script_mods) | set(tex_mods)
print(f"mod: {len(script_mods)} script(s), {sum(len(v) for v in tex_mods.values())} texture(s) in {len(tex_mods)} model(s)")


def retexture(asset, replacements):
    """Replace DXT1 textures inside a model asset's resource chunks (same size)."""
    desc = asset.descriptor
    fp, n = struct.unpack_from("<II", desc, 0)
    entry = next((p for t, p in (struct.unpack_from("<II", desc, fp + 8 * e) for e in range(n)) if t == 7), None)
    count, lst = struct.unpack_from("<II", desc, entry)
    chunks = [bytearray(c) for c in asset.chunks]
    starts = np.cumsum([0] + [len(c) for c in chunks])
    for idx, png in replacements.items():
        if idx >= count:
            sys.exit(f"{asset.name}: texture {idx} does not exist ({count} textures)")
        tp = struct.unpack_from("<I", desc, lst + 4 * idx)[0]
        fmt, _hs, w, h, flags, _u, off, size = struct.unpack_from("<IIHHIIII", desc, tp)
        if fmt != 0x0C or flags >> 24 != 1:
            sys.exit(f"{asset.name} texture {idx}: only single-level DXT1 textures are supported")
        img = mpimg.imread(str(png))
        if img.dtype != np.uint8:
            img = np.round(img * 255).astype(np.uint8)
        if img.shape[2] == 3:
            img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
        if img.shape[:2] != (h, w):
            sys.exit(f"{png}: is {img.shape[1]}x{img.shape[0]}, texture is {w}x{h}")
        data = dxt.encode_dxt1(img)
        ci = int(np.searchsorted(starts, off, side="right") - 1)
        local = off - starts[ci]
        if local + size > len(chunks[ci]):
            sys.exit(f"{asset.name} texture {idx} spans resource chunks; not supported")
        chunks[ci][local:local + size] = data
    asset.chunks = [bytes(c) for c in chunks]


# ---- find and rebuild every bundle that contains a modded asset
changed, found = [], set()
for bnl in sorted(iso_root.rglob("*.bnl")):
    bundle = gb.read(bnl.read_bytes())
    hits = [a for a in bundle.assets if a.name in wanted]
    if not hits:
        continue
    for a in hits:
        found.add(a.name)
        if a.name in script_mods:
            a.descriptor = script_mods[a.name]
        if a.name in tex_mods:
            retexture(a, tex_mods[a.name])
    rel = bnl.relative_to(iso_root)
    (work_root / rel).write_bytes(gb.write(bundle))
    changed.append(rel.as_posix())  # '/' separators so manifest entries compare reliably
    print(f"  rebuilt {rel} ({', '.join(a.name for a in hits)})")
missing = wanted - found
if missing:
    sys.exit(f"assets not found in any bundle: {sorted(missing)}")

# ---- restore bundles modded by a previous build but not this one
manifest = work_root.with_name(work_root.name + ".manifest.json")
previous = [p.replace("\\", "/") for p in json.loads(manifest.read_text())] if manifest.exists() else []
for rel in previous:
    if rel not in changed:
        shutil.copy2(iso_root / rel, work_root / rel)
        print(f"  restored original {rel}")
manifest.write_text(json.dumps(changed, indent=1))

# ---- pack the disc
if out_iso.exists():
    out_iso.unlink()
r = subprocess.run([str(extract_xiso), "-c", str(work_root), out_iso.name], cwd=out_iso.parent,
                   capture_output=True, text=True)
print("  " + (r.stdout.strip().splitlines() or ["?"])[-1])
if r.returncode != 0 or not out_iso.exists():
    sys.exit("extract-xiso failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])
print(f"built {out_iso} ({out_iso.stat().st_size / 1e9:.2f} GB)")
