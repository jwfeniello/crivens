"""Export every unique model to .glb with its matching animations.

usage: python -I batch_export.py <survey.json> <out_dir> [name_filter]
Animation pairing: an anim belongs to the model whose name is the longest prefix of the anim
name with the same bone count; leftover anims go to every model sharing their first two name
tokens (e.g. weapon_largetwohand) and bone count.
"""
import collections
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
survey = json.load(open(sys.argv[1]))
out_dir = Path(sys.argv[2])
flt = sys.argv[3] if len(sys.argv) > 3 else ""
MP, AP = "aid_model_ghoulies_", "aid_anim_ghoulies_"

def strip(name, prefix):
    # loose demand/ assets without a known name keep their hash (e.g. 0ddd9533)
    return name[len(prefix):] if name.startswith(prefix) else name


models = {strip(k, MP): v for k, v in survey["models"].items()}
anims = {strip(k, AP): v for k, v in survey["anims"].items()}
skel = {m: v["bones"] for m, v in models.items() if v["bones"] > 0}

pairs = collections.defaultdict(list)
left = []
for a, v in anims.items():
    c = [m for m, b in skel.items() if (a == m or a.startswith(m + "_")) and b == v["bones"]]
    if c:
        pairs[max(c, key=len)].append(a)
    else:
        left.append(a)
shared = 0
for a in left:
    grp = "_".join(a.split("_")[:2])
    c = [m for m, b in skel.items() if m.startswith(grp) and b == anims[a]["bones"]]
    for m in c:
        pairs[m].append(a)
    shared += bool(c)
# variants (e.g. skeletonbadmaid) reuse the anims of the base model they extend, if rigs match
inherited = 0
for m, b in skel.items():
    if pairs.get(m):
        continue
    bases = [o for o, ob in skel.items() if o != m and m.startswith(o) and ob == b and pairs.get(o)]
    if bases:
        pairs[m] = list(pairs[max(bases, key=len)])
        inherited += 1
print(f"{sum(len(v) for v in pairs.values())} anim assignments; {shared}/{len(left)} leftovers matched by group; "
      f"{inherited} variant models inherit a base model's anims")

out_dir.mkdir(parents=True, exist_ok=True)
lists = out_dir / "_anim_lists"
lists.mkdir(exist_ok=True)
log = open(out_dir / "_export_log.txt", "w", encoding="utf-8")
report = {}
t0 = time.time()
for i, (m, v) in enumerate(sorted(models.items())):
    if flt not in m:
        continue
    cat = m.split("_")[0] if "_" in m else "unnamed"
    out = out_dir / cat / f"{m}.glb"
    args = [sys.executable, "-I", str(HERE / "ghoul_gltf.py"), v["dirs"][0], str(out)]
    if pairs.get(m):
        lf = lists / f"{m}.txt"
        lf.write_text("\n".join(anims[a]["dirs"][0] for a in sorted(pairs[m])), encoding="utf-8")
        args.append("@" + str(lf))
    r = subprocess.run(args, capture_output=True, text=True)
    ok = r.returncode == 0
    msg = (r.stdout.strip().splitlines() or [""])[-1] if ok else (r.stderr.strip().splitlines() or ["?"])[-1]
    report[m] = {"ok": ok, "msg": msg, "anims_paired": len(pairs.get(m, []))}
    log.write(f"{'OK ' if ok else 'ERR'} {m}: {msg}\n")
    log.flush()
    print(f"[{i + 1}/{len(models)} {time.time() - t0:.0f}s] {'OK ' if ok else 'ERR'} {m}: {msg[:110]}", flush=True)
json.dump(report, open(out_dir / "_export_report.json", "w"), indent=1)
print("done:", sum(r["ok"] for r in report.values()), "ok,", sum(not r["ok"] for r in report.values()), "failed")
