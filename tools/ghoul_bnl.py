"""Read and write Grabbed by the Ghoulies .bnl bundles with the original layout rules.

Layout (verified byte-exact against every bundle on the disc):
  40-byte header: u16 asset_count, u8 flags, 5 bytes, 4 x (u32 offset, u32 size) for the
  sections below (offsets include the header). Everything after the header is one zlib stream.
  asset descriptions: 0xA0 each, sorted by name:
      char name[128], u32 type, u32 u1, u32 u2, u32 field (always 2),
      u32 descriptor_ptr, u32 descriptor_size, u32 dataview_list_ptr, u32 resource_size
  data-view lists, in asset order: u32 list_size (8+8n), u32 n, n x (u32 offset, u32 size)
  buffer: every asset's resource chunks, in asset order, packed back to back (no padding;
      most chunk sizes are multiples of 32/128, so pad new chunk data to 128 when building it)
  descriptors: every asset's descriptor, in asset order, no padding
  resource_size = list_size + sum(chunk sizes), sometimes rounded up to 128 (see Asset).

usage: python -I ghoul_bnl.py roundtrip <bundles_dir>
"""
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

CHUNK_ALIGN = 128


@dataclass
class Asset:
    name: str
    type: int
    u1: int
    u2: int
    field: int
    descriptor: bytes
    chunks: list = field(default_factory=list)  # list[bytes]
    # resource_size as stored on disc, with the chunk sizes it was computed for. Rare's tool
    # sometimes rounded it up to 128 and sometimes didn't (no pattern); we keep the original
    # while the chunks are unchanged and otherwise use the rounded-up value, which is never smaller.
    stored_rsize: tuple = None


@dataclass
class Bundle:
    flags: int
    unknown: bytes
    assets: list

    def get(self, name):
        return next(a for a in self.assets if a.name == name)


def read(data: bytes) -> Bundle:
    hdr = data[:40]
    full = hdr + zlib.decompress(data[40:])
    count, flags = struct.unpack_from("<HB", hdr, 0)
    (ad, _), (bv, _), (buf, _), (de, _) = (struct.unpack_from("<II", hdr, 8 + 8 * i) for i in range(4))
    assets = []
    for i in range(count):
        b = full[ad + 0xA0 * i: ad + 0xA0 * (i + 1)]
        name = b[:128].split(b"\0")[0].decode("latin-1")
        typ, u1, u2, fld, dptr, dsize, dvl, rsize = struct.unpack_from("<8I", b, 128)
        chunks = []
        if rsize:
            _lsize, n = struct.unpack_from("<II", full, bv + dvl)
            for k in range(n):
                o, s = struct.unpack_from("<II", full, bv + dvl + 8 + 8 * k)
                chunks.append(full[buf + o: buf + o + s])
        stored = (rsize, tuple(len(c) for c in chunks)) if rsize else None
        assets.append(Asset(name, typ, u1, u2, fld, full[de + dptr: de + dptr + dsize], chunks, stored))
    return Bundle(flags, hdr[3:8], assets)


def write(bundle: Bundle) -> bytes:
    assets = sorted(bundle.assets, key=lambda a: a.name)
    descs, views, buf, dsec = bytearray(), bytearray(), bytearray(), bytearray()
    for a in assets:
        dvl_ptr = rsize = 0
        if a.chunks:
            dvl_ptr = len(views)
            lsize = 8 + 8 * len(a.chunks)
            views += struct.pack("<II", lsize, len(a.chunks))
            for c in a.chunks:  # packed back to back; new chunks should be padded by their builder
                views += struct.pack("<II", len(buf), len(c))
                buf += c
            sizes = tuple(len(c) for c in a.chunks)
            if a.stored_rsize and a.stored_rsize[1] == sizes:
                rsize = a.stored_rsize[0]
            else:
                rsize = -(-(lsize + sum(sizes)) // CHUNK_ALIGN) * CHUNK_ALIGN
        name = a.name.encode("latin-1")
        assert len(name) < 128, f"asset name too long: {a.name}"
        descs += name.ljust(128, b"\0") + struct.pack("<8I", a.type, a.u1, a.u2, a.field, len(dsec),
                                                       len(a.descriptor), dvl_ptr, rsize)
        dsec += a.descriptor
    sections = [descs, views, buf, dsec]
    off, hdr_views = 40, b""
    for s in sections:
        hdr_views += struct.pack("<II", off, len(s))
        off += len(s)
    header = struct.pack("<HB", len(assets), bundle.flags) + bundle.unknown + hdr_views
    return header + zlib.compress(b"".join(sections), 9)


def roundtrip(root):
    ok = bad = 0
    for p in sorted(Path(root).rglob("*.bnl")):
        raw = p.read_bytes()
        rebuilt = write(read(raw))
        same = rebuilt[:40] == raw[:40] and zlib.decompress(rebuilt[40:]) == zlib.decompress(raw[40:])
        if same:
            ok += 1
        else:
            bad += 1
            print("MISMATCH", p.name)
    print(f"bundles rebuilt identically (decompressed): {ok}, different: {bad}")


if __name__ == "__main__":
    if sys.argv[1] == "roundtrip":
        roundtrip(sys.argv[2])
