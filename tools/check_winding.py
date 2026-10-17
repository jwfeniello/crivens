"""Check a .glb's triangle winding against its vertex normals.
Prints the fraction of triangles whose CCW face normal agrees with the averaged vertex normal.
usage: python -I check_winding.py <file.glb>
"""
import json
import struct
import sys

data = open(sys.argv[1], "rb").read()
jlen = struct.unpack_from("<I", data, 12)[0]
g = json.loads(data[20:20 + jlen])
binoff = 20 + jlen + 8


def read(ai):
    a = g["accessors"][ai]
    bv = g["bufferViews"][a["bufferView"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    fmt = {5126: "f", 5123: "H", 5125: "I"}[a["componentType"]]
    vals = struct.unpack_from(f"<{a['count'] * n}{fmt}", data, binoff + bv["byteOffset"])
    return [vals[i:i + n] for i in range(0, len(vals), n)] if n > 1 else list(vals)


agree = total = 0
for m in g["meshes"]:
    for p in m["primitives"]:
        if "NORMAL" not in p["attributes"]:
            continue
        P, N, I = read(p["attributes"]["POSITION"]), read(p["attributes"]["NORMAL"]), read(p["indices"])
        for t in range(0, len(I), 3):
            a, b, c = I[t:t + 3]
            u = [P[b][k] - P[a][k] for k in range(3)]
            v = [P[c][k] - P[a][k] for k in range(3)]
            fn = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            vn = [N[a][k] + N[b][k] + N[c][k] for k in range(3)]
            d = sum(fn[k] * vn[k] for k in range(3))
            if d != 0:
                total += 1
                agree += d > 0
print(f"winding agrees with normals: {agree}/{total} = {agree / max(total, 1):.1%}")
