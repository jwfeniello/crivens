"""DXT1 (BC1) encoder/decoder for Ghoulies textures (Xbox DXT textures are plain block-linear).

encode_dxt1(rgba uint8 HxWx4) -> bytes ; decode_dxt1(bytes, w, h) -> rgba uint8 HxWx4
Blocks with any alpha < 128 use 3-colour + transparent mode; others use 4-colour mode.
"""
import numpy as np


def _to565(c):
    c = np.clip(np.round(c), 0, 255).astype(np.int32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def _from565(v):
    v = np.asarray(v, dtype=np.int32)
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.float64)


def _palette(c0, c1, transparent_mode):
    p0, p1 = _from565(c0), _from565(c1)
    if transparent_mode:
        return np.stack([p0, p1, (p0 + p1) / 2, np.zeros(3)])
    return np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3])


def _encode_block(px):
    """px: 16x4 float RGBA -> 8 bytes."""
    rgb, alpha = px[:, :3], px[:, 3]
    transparent = alpha < 128
    use_alpha = bool(transparent.any())
    opaque = rgb[~transparent] if use_alpha else rgb
    if len(opaque) == 0:  # fully transparent block
        return np.array([0, 0, 0, 0], np.uint16).tobytes() + (0xFFFFFFFF).to_bytes(4, "little")
    mean = opaque.mean(0)
    cov = np.cov((opaque - mean).T) if len(opaque) > 1 else np.zeros((3, 3))
    axis = np.linalg.eigh(cov)[1][:, -1] if np.any(cov) else np.array([1.0, 1.0, 1.0]) / 3 ** 0.5
    proj = (opaque - mean) @ axis
    e0, e1 = mean + axis * proj.max(), mean + axis * proj.min()
    best = None
    # try the endpoint pair and a slightly inset pair; keep the lower error
    for inset in (0.0, 1 / 16):
        a, b = e0 + (e1 - e0) * inset, e1 + (e0 - e1) * inset
        c0, c1 = int(_to565(a)), int(_to565(b))
        if use_alpha:
            if c0 > c1:
                c0, c1 = c1, c0
        else:
            if c0 < c1:
                c0, c1 = c1, c0
            if c0 == c1:  # degenerate: indices all 0 in 4-colour mode
                if c1 > 0:
                    c1 -= 1
                else:
                    c0 += 1
        pal = _palette(c0, c1, use_alpha)
        usable = pal[:3] if use_alpha else pal
        d = ((rgb[:, None, :] - usable[None, :, :]) ** 2).sum(-1)
        idx = d.argmin(1)
        err = d[np.arange(16), idx]
        if use_alpha:
            idx = np.where(transparent, 3, idx)
            err = np.where(transparent, 0, err)
        if best is None or err.sum() < best[0]:
            best = (err.sum(), c0, c1, idx)
    _, c0, c1, idx = best
    bits = 0
    for i, v in enumerate(idx):
        bits |= int(v) << (2 * i)
    return int(c0).to_bytes(2, "little") + int(c1).to_bytes(2, "little") + bits.to_bytes(4, "little")


def encode_dxt1(rgba):
    h, w = rgba.shape[:2]
    assert h % 4 == 0 and w % 4 == 0, "texture size must be a multiple of 4"
    img = rgba.astype(np.float64)
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            out += _encode_block(img[by:by + 4, bx:bx + 4].reshape(16, 4))
    return bytes(out)


def decode_dxt1(data, w, h):
    out = np.zeros((h, w, 4), np.uint8)
    k = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            c0 = int.from_bytes(data[k:k + 2], "little")
            c1 = int.from_bytes(data[k + 2:k + 4], "little")
            bits = int.from_bytes(data[k + 4:k + 8], "little")
            k += 8
            transparent_mode = c0 <= c1
            pal = _palette(c0, c1, transparent_mode)
            for i in range(16):
                v = (bits >> (2 * i)) & 3
                a = 0 if (transparent_mode and v == 3) else 255
                out[by + i // 4, bx + i % 4] = [*np.round(pal[v]).astype(np.uint8), a]
    return out
