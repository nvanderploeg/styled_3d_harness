import os

import bpy
import numpy as np


def read(path_or_image):
    """(h, w, 4) float array of an image file or bpy image, row 0 at the bottom, values as stored (no colour conversion)."""
    img = path_or_image
    owned = isinstance(img, str)
    if owned:
        img = bpy.data.images.load(img, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    if owned:
        bpy.data.images.remove(img)
    return px.reshape(h, w, 4)


def write(arr, path, colorspace="Non-Color"):
    """Save an (h, w, 3|4) float array as an 8-bit PNG. colorspace tags how the stored values are encoded."""
    arr = np.asarray(arr, np.float32)
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1), np.float32)], axis=2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.clip(arr, 0, 1).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
