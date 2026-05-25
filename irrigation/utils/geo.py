"""
irrigation/utils/geo.py
Geospatial utility functions.
All coordinates in WGS84 (EPSG:4326) unless stated otherwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Tuple, List

from shapely.geometry import box, mapping


@dataclass
class BoundingBox:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    crs: str = "EPSG:4326"

    def to_wkt_polygon(self) -> str:
        return (
            f"POLYGON(({self.lon_min} {self.lat_min},"
            f"{self.lon_max} {self.lat_min},"
            f"{self.lon_max} {self.lat_max},"
            f"{self.lon_min} {self.lat_max},"
            f"{self.lon_min} {self.lat_min}))"
        )

    def to_tuple(self) -> Tuple[float, float, float, float]:
        """(lon_min, lat_min, lon_max, lat_max) — rasterio convention."""
        return self.lon_min, self.lat_min, self.lon_max, self.lat_max


def centroid_and_area_to_bbox(lat: float, lon: float, area_rai: float) -> BoundingBox:
    """
    Convert a field centroid + area in Rai to a WGS84 bounding box.

    1 Rai = 1,600 m². Assumes roughly square field.
    """
    area_m2 = area_rai * 1600.0
    side_m = math.sqrt(area_m2)
    half_side_m = side_m / 2.0

    # 1 degree latitude  ≈ 111,111 m
    # 1 degree longitude ≈ 111,111 * cos(lat) m
    lat_offset = half_side_m / 111_111.0
    lon_offset = half_side_m / (111_111.0 * math.cos(math.radians(lat)))

    return BoundingBox(
        lat_min=lat - lat_offset,
        lat_max=lat + lat_offset,
        lon_min=lon - lon_offset,
        lon_max=lon + lon_offset,
    )


def build_grid_cells(
    bbox: BoundingBox,
    resolution_m: int,
) -> List[dict]:
    """
    Divide a bounding box into a regular grid.

    Returns list of GeoJSON Feature dicts with geometry only (no properties).
    Cell IDs are assigned row-major: cell_id = row * n_cols + col.
    """
    area_m2 = (
        (bbox.lat_max - bbox.lat_min) * 111_111.0
        * (bbox.lon_max - bbox.lon_min) * 111_111.0
        * math.cos(math.radians((bbox.lat_min + bbox.lat_max) / 2))
    )
    side_m = math.sqrt(area_m2)
    n_cells = max(1, int(side_m / resolution_m))

    lat_step = (bbox.lat_max - bbox.lat_min) / n_cells
    lon_step = (bbox.lon_max - bbox.lon_min) / n_cells

    features: List[dict] = []
    cell_id = 0
    for row in range(n_cells):
        for col in range(n_cells):
            cell_bbox = box(
                bbox.lon_min + col * lon_step,
                bbox.lat_min + row * lat_step,
                bbox.lon_min + (col + 1) * lon_step,
                bbox.lat_min + (row + 1) * lat_step,
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(cell_bbox),
                    "properties": {
                        "cell_id": cell_id,
                        "row": row,
                        "col": col,
                    },
                }
            )
            cell_id += 1

    return features


def classify_moisture(moisture_index: float) -> str:
    """Map 0–1 moisture index to CRITICAL_DRY | DRY | OPTIMAL | WET."""
    from irrigation.constants import MOISTURE_THRESHOLDS

    for threshold, label in MOISTURE_THRESHOLDS:
        if moisture_index <= threshold:
            return label
    return "WET"
