"""Rebuild Cooper's body geometry through ghoul_modelwrite and write the result as a
model asset folder (descriptor + resourceN + imageN.png) for offline checks and modding.

usage: python -I regen_cooper.py <Model__aid_model_ghoulies_actor_boy dir> <out_dir>
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_modelwrite as mw  # noqa: E402

src, out = Path(sys.argv[1]), Path(sys.argv[2])
chunks = []
while (src / f"resource{len(chunks)}").exists():
    chunks.append((src / f"resource{len(chunks)}").read_bytes())
model = mw.Model((src / "descriptor").read_bytes(), chunks)
groups = model.decode_groups()
print("decoded groups:", [(hex(g.material), len(g.tris), g.max_bones) for g in groups])
stats = model.write_geometry(groups)
desc, new_chunks = model.finish()
print("written:", stats, "descriptor", len(model.desc), "chunks", [len(c) for c in new_chunks])

out.mkdir(parents=True, exist_ok=True)
for f in out.glob("resource*"):
    f.unlink()
(out / "descriptor").write_bytes(desc)
for i, c in enumerate(new_chunks):
    (out / f"resource{i}").write_bytes(c)
for png in src.glob("image*.png"):
    shutil.copy2(png, out / png.name)
for extra in ("metadata",):
    if (src / extra).exists():
        shutil.copy2(src / extra, out / extra)
print("wrote", out)
