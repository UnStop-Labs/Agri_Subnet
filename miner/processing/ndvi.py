"""
miner/processing/ndvi.py
NDVI (Normalized Difference Vegetation Index) computation.

NDVI = (NIR - Red) / (NIR + Red)
Sentinel-2 bands: Red = B04, NIR = B08
"""
from __future__ import annotations

from io import BytesIO

import numpy as np
import rasterio


def compute_ndvi_from_geotiff(geotiff_bytes: bytes) -> np.ndarray:
    """
    Read a Sentinel-2 GeoTIFF and return NDVI array.

    Band indices: 4=Red (B04), 8=NIR (B08) — 1-indexed in rasterio.

    Args:
        geotiff_bytes: Raw bytes of a multi-band GeoTIFF file.

    Returns:
        Float32 NDVI array clipped to [-1.0, 1.0], shape (H, W).
    """
    with rasterio.open(BytesIO(geotiff_bytes)) as src:
        red = src.read(4).astype(np.float32)
        nir = src.read(8).astype(np.float32)

    ndvi = (nir - red) / (nir + red + 1e-8)
    return np.clip(ndvi, -1.0, 1.0)


def ndvi_to_moisture_index(ndvi: np.ndarray) -> np.ndarray:
    """
    Convert NDVI (-1 to 1) to a soil moisture proxy index (0 to 1).

    Low NDVI (dry/bare soil)         → high watering need (1.0).
    High NDVI (dense vegetation)     → low watering need (0.0).

    Formula: moisture_need = 1 - (ndvi + 1) / 2
    """
    return np.clip(1.0 - (ndvi + 1.0) / 2.0, 0.0, 1.0)
