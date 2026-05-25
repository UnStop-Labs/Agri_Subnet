"""
miner/processing/grid_builder.py
Build a GeoJSON FeatureCollection irrigation grid from satellite bands.

Each cell gets:
  moisture_class, moisture_index, ndvi, ndwi, confidence,
  evapotranspiration_mm (Phase 2), cloud_masked, data_source.
"""
from __future__ import annotations

import numpy as np
from typing import List

from irrigation.utils.geo import BoundingBox, build_grid_cells, classify_moisture


def build_geojson_grid(
    ndvi: np.ndarray,
    ndwi: np.ndarray,
    bbox: BoundingBox,
    resolution_m: int,
    data_source: str = "Sentinel-2 L2A",
) -> dict:
    """
    Given full-field NDVI and NDWI arrays, produce a GeoJSON FeatureCollection
    where each cell has all properties from spec §4.4.

    The arrays are divided into n×n grid cells matching resolution_m.
    Cell-level values are the spatial mean within each cell.

    Args:
        ndvi:          Float32 NDVI array, shape (H, W), range [-1, 1].
        ndwi:          Float32 NDWI array, same shape as ndvi.
        bbox:          Bounding box of the field.
        resolution_m:  Target cell size in metres (10 | 20 | 30 | 60).
        data_source:   Identifier string for the satellite product.

    Returns:
        GeoJSON FeatureCollection dict with one Feature per grid cell.
    """
    cell_features = build_grid_cells(bbox, resolution_m)
    n_cells_per_side = max(1, int(len(cell_features) ** 0.5))

    h, w = ndvi.shape
    features: List[dict] = []

    for feat in cell_features:
        cell_id = feat["properties"]["cell_id"]
        row     = feat["properties"]["row"]
        col     = feat["properties"]["col"]
        n       = n_cells_per_side

        # Slice the array region for this cell
        r0, r1 = int(row * h / n),       int((row + 1) * h / n)
        c0, c1 = int(col * w / n),       int((col + 1) * w / n)

        # Protect against zero-sized slices
        cell_ndvi_arr = ndvi[r0:r1, c0:c1]
        cell_ndwi_arr = ndwi[r0:r1, c0:c1]
        cell_ndvi = float(cell_ndvi_arr.mean()) if cell_ndvi_arr.size else 0.0
        cell_ndwi = float(cell_ndwi_arr.mean()) if cell_ndwi_arr.size else 0.0

        # Moisture index: blend NDVI-derived and NDWI-derived signals
        ndvi_moisture = float(np.clip(1.0 - (cell_ndvi + 1.0) / 2.0, 0.0, 1.0))
        ndwi_moisture = float(np.clip(1.0 - (cell_ndwi + 1.0) / 2.0, 0.0, 1.0))
        moisture_index = round(0.6 * ndvi_moisture + 0.4 * ndwi_moisture, 4)

        # Per-cell confidence: higher when NDVI and NDWI agree
        agreement  = 1.0 - abs(ndvi_moisture - ndwi_moisture)
        confidence = round(float(np.clip(agreement, 0.0, 1.0)), 3)

        features.append(
            {
                "type": "Feature",
                "geometry": feat["geometry"],
                "properties": {
                    "cell_id":               cell_id,
                    "moisture_class":        classify_moisture(moisture_index),
                    "moisture_index":        moisture_index,
                    "ndvi":                  round(cell_ndvi, 4),
                    "ndwi":                  round(cell_ndwi, 4),
                    "evapotranspiration_mm": _compute_evapotranspiration(cell_ndvi),
                    "cloud_masked":          False,
                    "data_source":           data_source,
                    "cell_confidence":       confidence,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def _compute_evapotranspiration(ndvi: float) -> float:
    """
    Estimate evapotranspiration in mm/day from NDVI.

    Phase 2: replace with ERA5 CDSAPI integration for proper
    Penman-Monteith evapotranspiration per cell.
    See: https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-land

    Current implementation uses a simple empirical proxy:
      ET ≈ 0–6 mm/day scaled linearly from NDVI range [-1, 1].
    """
    # Simple linear proxy — Phase 2 will integrate ERA5 reference ET
    return round(float(np.clip((ndvi + 1.0) / 2.0 * 6.0, 0.0, 6.0)), 2)
