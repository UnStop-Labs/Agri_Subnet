"""
miner/processing/ndwi.py
NDWI (Normalized Difference Water Index) computation.

NDWI = (Green - NIR) / (Green + NIR)
Sentinel-2 bands: Green = B03, NIR = B08
"""
from __future__ import annotations

from io import BytesIO

import numpy as np
import rasterio


def compute_ndwi_from_geotiff(geotiff_bytes: bytes) -> np.ndarray:
    """
    Read a Sentinel-2 GeoTIFF and return NDWI array.

    Band indices: 3=Green (B03), 8=NIR (B08) — 1-indexed in rasterio.

    Args:
        geotiff_bytes: Raw bytes of a multi-band GeoTIFF file.

    Returns:
        Float32 NDWI array clipped to [-1.0, 1.0], shape (H, W).
    """
    with rasterio.open(BytesIO(geotiff_bytes)) as src:
        green = src.read(3).astype(np.float32)
        nir   = src.read(8).astype(np.float32)

    ndwi = (green - nir) / (green + nir + 1e-8)
    return np.clip(ndwi, -1.0, 1.0)
