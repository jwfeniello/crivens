"""Survey skeletal models and animations across all extracted bundles.
usage: python -I survey.py <assets_dir> <out.json>
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_model as gm  # noqa: E402

root = Path(sys.argv[1])
models, anims = {}, {}
for d in root.rglob("Model__*"):
    name = d.name[len("Model__"):]
    rec = models.setdefault(name, {"dirs": [], "bones": None})
    rec["dirs"].append(str(d))
    if rec["bones"] is None:
        try:
            m = gm.read_model((d / "descriptor").read_bytes())
            sk = next((n for r in m["meshes"][0]["roots"] for _, n in r.walk() if n.name == "ndSkeleton"), None)
            rec["bones"] = len(sk.data["bones"]) if sk else 0
        except Exception as e:  # noqa: BLE001
            rec["bones"] = -1
            rec["error"] = str(e)[:120]
for d in root.rglob("Anim__*"):
    name = d.name[len("Anim__"):]
    rec = anims.setdefault(name, {"dirs": [], "bones": None})
    rec["dirs"].append(str(d))
    if rec["bones"] is None:
        desc = (d / "descriptor").read_bytes()
        rec["bones"] = struct.unpack_from("<H", desc, 0x14)[0] if desc[:4] == b"MINA" else -1
json.dump({"models": models, "anims": anims}, open(sys.argv[2], "w"))
sk = {k: v for k, v in models.items() if v["bones"] and v["bones"] > 0}
print(f"models: {len(models)} unique, {len(sk)} skeletal, {sum(1 for v in models.values() if v['bones'] == -1)} unreadable")
print(f"anims: {len(anims)} unique names, {sum(len(v['dirs']) for v in anims.values())} total copies")
