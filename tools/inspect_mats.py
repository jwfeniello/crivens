import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_modelwrite as mw, ghoul_model as gm
src = Path(sys.argv[1])
ch = []
while (src / f"resource{len(ch)}").exists(): ch.append((src / f"resource{len(ch)}").read_bytes())
m = mw.Model((src / "descriptor").read_bytes(), ch)
mb = m.mb
groups = {g.material: g for g in m.decode_groups()}
for si, var, sp in m.materials():
    p = mw.u32(mb, sp.off + 0x20)
    ts, nt = mw.u32(mb, p + 8), mw.u32(mb, p + 12)
    at, na = mw.u32(mb, p + 0x24), mw.u32(mb, p + 0x28)
    texs = [mw.u32(mb, ts + 28 * i) for i in range(nt)]
    attrs = [(gm.cstr(mb, struct.unpack_from("<III", mb, at + 16 * i)[0]),) + struct.unpack_from("<III", mb, at + 16 * i)[1:] for i in range(na)]
    g = groups.get(sp.off)
    sh2 = m.mtx.children[si]
    vs = next(v for v in sh2.children if sp in v.children or any(c.off == sp.off for c in v.children))
    print(f"sh2 {si} var {var:5s} sp {sp.off:#x} tris {len(g.tris) if g else 0:4d} maxb {g.max_bones if g else '-'} texs {texs} attrs {attrs} | {sh2.name} / {vs.name}")
