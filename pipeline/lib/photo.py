"""Turn reference photos into tileable texture sources for zone materials."""
import bpy
import numpy as np

import imgio


def prepare(src, dst, size=1024, delight=0.1, tileable=True):
    """Centre-crop src to a square of size px, flatten its lighting and make it tile. Writes an sRGB PNG.
    delight is the blur radius, as a fraction of size, that separates lighting from surface detail; 0 skips it."""
    arr = imgio.read(src)[..., :3]
    h, w = arr.shape[:2]
    s = min(h, w)
    arr = arr[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s]
    arr = resize(arr, size)
    if delight:
        lum = arr.mean(-1)
        low = blur(lum, delight * size)
        arr = arr * (low.mean() / np.maximum(low, 1e-3))[..., None]
    if tileable:
        arr = tile(arr)
    imgio.write(np.clip(arr, 0, 1), dst, "sRGB")
    return dst


def derive(albedo, height_dst, roughness_dst, rough=(0.5, 0.9), detail=0.02):
    """Height (high-passed luminance, for a Bump node) and roughness (darker = rougher, mapped into rough)
    from a prepared albedo. Both are written as Non-Color PNGs."""
    lum = imgio.read(albedo)[..., :3].mean(-1)
    hp = lum - blur(lum, detail * lum.shape[0])
    height = np.clip(0.5 + hp / (4 * hp.std() + 1e-6), 0, 1)
    norm = (lum - lum.min()) / (np.ptp(lum) + 1e-6)
    r = rough[1] - norm * (rough[1] - rough[0])
    imgio.write(np.repeat(height[..., None], 3, -1), height_dst)
    imgio.write(np.repeat(r[..., None], 3, -1), roughness_dst)
    return height_dst, roughness_dst


def resize(arr, size):
    h, w = arr.shape[:2]
    img = bpy.data.images.new("resize", w, h, alpha=True)
    img.pixels.foreach_set(np.concatenate([arr, np.ones((h, w, 1), np.float32)], -1).astype(np.float32).ravel())
    img.scale(size, size)
    out = imgio.read(img)[..., :3].copy()
    bpy.data.images.remove(img)
    return out


def blur(a, sigma):
    """Gaussian blur with wrap-around edges."""
    h, w = a.shape
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    k = np.exp(-2 * (np.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k))


def tile(arr):
    """Cross-fade with a half-offset copy so opposite edges meet seamlessly."""
    h, w = arr.shape[:2]
    rolled = np.roll(arr, (h // 2, w // 2), axis=(0, 1))
    y = 1 - np.abs(np.linspace(-1, 1, h))[:, None]
    x = 1 - np.abs(np.linspace(-1, 1, w))[None, :]
    wgt = np.clip(np.minimum(y, x) * 3, 0, 1)[..., None]
    return arr * wgt + rolled * (1 - wgt)
