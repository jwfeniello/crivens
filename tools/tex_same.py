# every texture, read the game's way (per-chunk translation), must equal the original's bytes
import struct, sys
from pathlib import Path
def load(d):
    d=Path(d); desc=(d/"descriptor").read_bytes(); ch=[]
    while (d/f"resource{len(ch)}").exists(): ch.append((d/f"resource{len(ch)}").read_bytes())
    fp,n=struct.unpack_from("<II",desc,0)
    t7=next(q for t,q in (struct.unpack_from("<II",desc,fp+8*e) for e in range(n)) if t==7)
    c,l=struct.unpack_from("<II",desc,t7); out=[]
    for i in range(c):
        rec=struct.unpack_from("<I",desc,l+4*i)[0]; off,size=struct.unpack_from("<II",desc,rec+0x14)
        tot=0
        for k,x in enumerate(ch):
            if off<tot+len(x): out.append(x[off-tot:off-tot+size]); break
            tot+=len(x)
    return out
a,b=load(sys.argv[1]),load(sys.argv[2])
print("textures", len(a), len(b), "identical:", sum(x==y for x,y in zip(a,b)))
