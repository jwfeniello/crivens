"""Grabbed by the Ghoulies animation (ANIM / "MINA") decoder, following the game's own code
(default.xbe: AnimInstance::updateFromAnimRes, ParsedAnimVal::getQuat/getVec3,
readBitsFromBitStream, Quaternion::slerpIntoQ1).

Descriptor layout (offsets from start of descriptor):
  0x00 'MINA'  0x04 f32 ?  0x08 f32 duration  0x0c u32 cvals (root-motion stream offset, 0 = none)
  0x14 u16 num_bones  0x18 u16 num_keyframes  0x1c u32 precision
  0x24 u32 num_root_keyframes  0x28 u32 tail (per-bone parent-scale-compensation bitmask offset)
  0x40 AnimStream: u16 header_size, u16 shorts_size, u16 nibbles_size, u16 keyframe_size, f32,
       pack formats (from stream+0x0c), shorts (stream+header_size), nibbles, keyframes.

Pack format byte: 0x80/0x40/0x20 = x/y/z present, 0x10/0x08/0x04 = x/y/z constant,
  (rotation byte only) 0x02 = translation byte follows, 0x01 = scale byte follows.
Present component: one i16 base. Non-constant: plus a 4-bit width-1 nibble and that many
  LSB-first bits from each keyframe; value = (base + unsigned bits) * scale.
"""
import struct


class AnimFormatError(Exception):
    pass


class BitReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0  # bit position

    def read(self, n):
        v = 0
        for i in range(n):
            byte = self.data[(self.pos >> 3)]
            v |= ((byte >> (self.pos & 7)) & 1) << i
            self.pos += 1
        return v


def decode_stream(d, base, num_bones, num_keyframes, prec):
    hs, s1, s2, kfs = struct.unpack_from("<HHHH", d, base)
    packs_off = base + 0x0C
    shorts_off = base + hs
    nib_off = shorts_off + s1
    kf_off = nib_off + s2
    if kf_off + kfs * num_keyframes > len(d):
        raise AnimFormatError(f"keyframes overrun descriptor ({kf_off + kfs * num_keyframes} > {len(d)})")

    quat_scale = 1.0 / ((1 << (((prec >> 23) & 0x1F) - 1)) - 1.0)
    pos_scale = 1.0 / (1 << ((prec >> 18) & 0x1F))
    scl_scale = 1.0 / (1 << ((prec >> 8) & 0x1F))

    # Build a channel plan shared by every keyframe.
    plan = []  # per bone: dict(kind -> list of (base_short, width or 0 for const) or None per component)
    p = packs_off
    sh = shorts_off
    nib_index = 0

    def take_short():
        nonlocal sh
        v = struct.unpack_from("<h", d, sh)[0]
        sh += 2
        return v

    def take_nibble():
        nonlocal nib_index
        b = d[nib_off + (nib_index >> 1)]
        w = ((b >> 4) if (nib_index & 1) else (b & 0xF)) + 1
        nib_index += 1
        return w

    def comps(fmt):
        out = []
        for i in range(3):
            if fmt & (0x80 >> i):
                const = bool(fmt & (0x10 >> i))
                base_v = take_short()
                out.append((base_v, 0 if const else take_nibble()))
            else:
                out.append(None)
        return out

    # The pack-format region can hold more tracks than num_bones (e.g. a carried prop's bones);
    # the game reads only num_bones, but we decode every track so the section sizes check out.
    while len(plan) < num_bones or p < shorts_off:
        q = d[p]
        p += 1
        bone = {"rot": comps(q), "pos": None, "scl": None}
        if q & 2:
            bone["pos"] = comps(d[p])
            p += 1
        if q & 1:
            bone["scl"] = comps(d[p])
            p += 1
        plan.append(bone)

    if p > shorts_off:
        raise AnimFormatError(f"pack formats overrun header ({p - base} > {hs})")
    if sh != nib_off:
        raise AnimFormatError(f"shorts mismatch: used {(sh - shorts_off) // 2}, have {s1 // 2}")
    if (nib_index + 1) // 2 != s2:
        raise AnimFormatError(f"nibbles mismatch: used {nib_index}, have {s2 * 2}")
    total_bits = sum(c[1] for b in plan for k in ("rot", "pos", "scl") if b[k] for c in b[k] if c)
    if total_bits > kfs * 8:
        raise AnimFormatError(f"bits per keyframe {total_bits} > {kfs * 8}")

    frames = []
    for k in range(num_keyframes):
        br = BitReader(d[kf_off + k * kfs: kf_off + (k + 1) * kfs])
        bones = []
        for b in plan:
            def val(c, scale, default):
                if c is None:
                    return default
                base_v, width = c
                return (base_v + (br.read(width) if width else 0)) * scale

            rx, ry, rz = (val(c, quat_scale, 0.0) for c in b["rot"])
            if any(b["rot"]):
                w2 = 1.0 - (rx * rx + ry * ry + rz * rz)
                rot = (rx, ry, rz, w2 ** 0.5 if w2 > 0 else 0.0)
            else:
                rot = (0.0, 0.0, 0.0, 1.0)
            pos = tuple(val(c, pos_scale, 0.0) for c in b["pos"]) if b["pos"] else None
            scl = tuple(val(c, scl_scale, 1.0) for c in b["scl"]) if b["scl"] else None
            bones.append((rot, pos, scl))
        frames.append(bones)
    animated = [
        {k: (b[k] is not None and any(c and c[1] for c in b[k])) or (k == "rot" and any(b["rot"]))
         for k in ("rot", "pos", "scl")}
        for b in plan
    ]
    return {"frames": frames, "plan": plan, "bits": total_bits, "kf_bytes": kfs, "animated": animated}


def decode(d):
    if d[:4] != b"MINA":
        raise AnimFormatError("bad magic")
    duration = struct.unpack_from("<f", d, 0x08)[0]
    cvals = struct.unpack_from("<I", d, 0x0C)[0]
    num_bones, = struct.unpack_from("<H", d, 0x14)
    num_keyframes, = struct.unpack_from("<H", d, 0x18)
    prec, = struct.unpack_from("<I", d, 0x1C)
    num_root_kf, = struct.unpack_from("<I", d, 0x24)
    tail, = struct.unpack_from("<I", d, 0x28)
    main = decode_stream(d, 0x40, num_bones, num_keyframes, prec)
    root = None
    if cvals and num_root_kf:
        root = decode_stream(d, cvals, 1, num_root_kf, prec)
    scale_comp = None
    if tail:
        scale_comp = [bool((d[tail + (j >> 3)] >> (j & 7)) & 1) for j in range(num_bones)]
    return {
        "duration": duration,
        "num_bones": num_bones,
        "num_keyframes": num_keyframes,
        "main": main,
        "root_motion": root,
        "scale_compensate": scale_comp,
    }
