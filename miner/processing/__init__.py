"""
miner/processing — spectral index computation and grid assembly.

Primary exports:
    compute_ndvi_from_geotiff  — returns NDVI float32 array
    compute_ndwi_from_geotiff  — returns NDWI float32 array
    build_geojson_grid         — assembles the final GeoJSON FeatureCollection
"""
from miner.processing.ndvi import compute_ndvi_from_geotiff, ndvi_to_moisture_index
from miner.processing.ndwi import compute_ndwi_from_geotiff
from miner.processing.grid_builder import build_geojson_grid

__all__ = [
    "compute_ndvi_from_geotiff",
    "ndvi_to_moisture_index",
    "compute_ndwi_from_geotiff",
    "build_geojson_grid",
]
