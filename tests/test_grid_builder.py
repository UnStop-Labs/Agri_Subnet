"""
tests/test_grid_builder.py
Tests for the GeoJSON grid builder and geo utilities.
"""
import numpy as np
import pytest

from miner.processing.grid_builder import build_geojson_grid
from irrigation.utils.geo import (
    centroid_and_area_to_bbox,
    build_grid_cells,
    classify_moisture,
    BoundingBox,
)


class TestCentroidToBbox:
    def test_returns_bounding_box(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 25.0)
        assert isinstance(bbox, BoundingBox)

    def test_centroid_inside_bbox(self):
        lat, lon = 14.471, 100.131
        bbox = centroid_and_area_to_bbox(lat, lon, 25.0)
        assert bbox.lat_min < lat < bbox.lat_max
        assert bbox.lon_min < lon < bbox.lon_max

    def test_larger_area_produces_larger_bbox(self):
        small = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        large = centroid_and_area_to_bbox(14.471, 100.131, 100.0)
        assert (large.lat_max - large.lat_min) > (small.lat_max - small.lat_min)

    def test_wkt_polygon_format(self):
        bbox = centroid_and_area_to_bbox(14.0, 100.0, 10.0)
        wkt = bbox.to_wkt_polygon()
        assert wkt.startswith("POLYGON((")
        assert wkt.endswith("))")

    def test_to_tuple_order(self):
        bbox = centroid_and_area_to_bbox(14.0, 100.0, 10.0)
        t = bbox.to_tuple()
        assert len(t) == 4
        lon_min, lat_min, lon_max, lat_max = t
        assert lon_min < lon_max
        assert lat_min < lat_max


class TestBuildGridCells:
    def test_returns_nonempty_list(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 25.0)
        cells = build_grid_cells(bbox, resolution_m=20)
        assert len(cells) > 0

    def test_each_cell_has_geometry_and_properties(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        cells = build_grid_cells(bbox, resolution_m=20)
        for cell in cells:
            assert "geometry" in cell
            assert "properties" in cell
            assert "cell_id" in cell["properties"]
            assert "row" in cell["properties"]
            assert "col" in cell["properties"]

    def test_cell_ids_are_unique(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 25.0)
        cells = build_grid_cells(bbox, resolution_m=20)
        ids = [c["properties"]["cell_id"] for c in cells]
        assert len(ids) == len(set(ids))


class TestBuildGeojsonGrid:
    def test_grid_has_cells(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 25.0)
        ndvi = np.full((100, 100), 0.4, dtype=np.float32)
        ndwi = np.full((100, 100), 0.2, dtype=np.float32)
        grid = build_geojson_grid(ndvi, ndwi, bbox, resolution_m=20)
        assert len(grid["features"]) > 0

    def test_feature_collection_type(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        ndvi = np.random.uniform(-0.3, 0.8, (50, 50)).astype(np.float32)
        ndwi = np.random.uniform(-0.5, 0.5, (50, 50)).astype(np.float32)
        grid = build_geojson_grid(ndvi, ndwi, bbox, resolution_m=20)
        assert grid["type"] == "FeatureCollection"

    def test_all_cells_have_required_properties(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        ndvi = np.random.uniform(-0.3, 0.8, (50, 50)).astype(np.float32)
        ndwi = np.random.uniform(-0.5, 0.5, (50, 50)).astype(np.float32)
        grid = build_geojson_grid(ndvi, ndwi, bbox, resolution_m=20)
        required = {
            "cell_id", "moisture_class", "moisture_index",
            "ndvi", "ndwi", "cloud_masked", "data_source", "cell_confidence",
            "evapotranspiration_mm",
        }
        for feat in grid["features"]:
            missing = required - set(feat["properties"].keys())
            assert not missing, f"Cell missing properties: {missing}"

    def test_moisture_index_in_range(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        ndvi = np.random.uniform(-1, 1, (50, 50)).astype(np.float32)
        ndwi = np.random.uniform(-1, 1, (50, 50)).astype(np.float32)
        grid = build_geojson_grid(ndvi, ndwi, bbox, resolution_m=20)
        for feat in grid["features"]:
            mi = feat["properties"]["moisture_index"]
            assert 0.0 <= mi <= 1.0, f"moisture_index out of range: {mi}"

    def test_moisture_class_enum_values(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        ndvi = np.random.uniform(-1, 1, (50, 50)).astype(np.float32)
        ndwi = np.random.uniform(-1, 1, (50, 50)).astype(np.float32)
        grid = build_geojson_grid(ndvi, ndwi, bbox, resolution_m=20)
        valid_classes = {"CRITICAL_DRY", "DRY", "OPTIMAL", "WET"}
        for feat in grid["features"]:
            cls = feat["properties"]["moisture_class"]
            assert cls in valid_classes, f"Invalid moisture_class: {cls}"

    def test_ndvi_ndwi_preserved_in_cells(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        ndvi = np.full((50, 50), 0.5, dtype=np.float32)
        ndwi = np.full((50, 50), 0.3, dtype=np.float32)
        grid = build_geojson_grid(ndvi, ndwi, bbox, resolution_m=20)
        for feat in grid["features"]:
            assert -1.0 <= feat["properties"]["ndvi"] <= 1.0
            assert -1.0 <= feat["properties"]["ndwi"] <= 1.0

    def test_confidence_in_range(self):
        bbox = centroid_and_area_to_bbox(14.471, 100.131, 10.0)
        ndvi = np.random.uniform(-1, 1, (50, 50)).astype(np.float32)
        ndwi = np.random.uniform(-1, 1, (50, 50)).astype(np.float32)
        grid = build_geojson_grid(ndvi, ndwi, bbox, resolution_m=20)
        for feat in grid["features"]:
            conf = feat["properties"]["cell_confidence"]
            assert 0.0 <= conf <= 1.0


class TestClassifyMoisture:
    def test_zero_is_critical_dry(self):
        assert classify_moisture(0.0) == "CRITICAL_DRY"

    def test_critical_dry_boundary(self):
        assert classify_moisture(0.20) == "CRITICAL_DRY"

    def test_dry_range(self):
        assert classify_moisture(0.30) == "DRY"

    def test_dry_boundary(self):
        assert classify_moisture(0.40) == "DRY"

    def test_optimal_range(self):
        assert classify_moisture(0.55) == "OPTIMAL"

    def test_optimal_boundary(self):
        assert classify_moisture(0.70) == "OPTIMAL"

    def test_wet_range(self):
        assert classify_moisture(0.90) == "WET"

    def test_one_is_wet(self):
        assert classify_moisture(1.0) == "WET"
