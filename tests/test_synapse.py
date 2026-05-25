"""
tests/test_synapse.py
Tests for FieldAnalysisChallenge and FieldAnalysisResponse validators.
"""
import time
import uuid

import pytest
from pydantic import ValidationError

from irrigation.synapse import FieldAnalysisChallenge, FieldAnalysisResponse


def _base_challenge(**kwargs) -> dict:
    defaults = dict(
        challenge_id=str(uuid.uuid4()),
        validator_hotkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",
        latitude=14.471,
        longitude=100.131,
        area_rai=25.0,
        query_date="2024-03-15T06:00:00Z",
        grid_resolution_m=20,
        nonce="aabbccdd" * 8,
        timestamp_utc=int(time.time()),
    )
    defaults.update(kwargs)
    return defaults


class TestFieldAnalysisChallenge:
    def test_valid_challenge_accepted(self):
        c = FieldAnalysisChallenge(**_base_challenge())
        assert c.challenge_id
        assert c.area_rai == 25.0
        assert c.grid_resolution_m == 20

    def test_negative_area_rejected(self):
        with pytest.raises(ValidationError, match="area_rai must be positive"):
            FieldAnalysisChallenge(**_base_challenge(area_rai=-5.0))

    def test_zero_area_rejected(self):
        with pytest.raises(ValidationError):
            FieldAnalysisChallenge(**_base_challenge(area_rai=0.0))

    def test_invalid_resolution_rejected(self):
        with pytest.raises(ValidationError, match="grid_resolution_m must be"):
            FieldAnalysisChallenge(**_base_challenge(grid_resolution_m=50))

    def test_valid_resolutions_accepted(self):
        for res in (10, 20, 30, 60):
            c = FieldAnalysisChallenge(**_base_challenge(grid_resolution_m=res))
            assert c.grid_resolution_m == res

    def test_crop_hint_is_optional(self):
        c = FieldAnalysisChallenge(**_base_challenge())
        assert c.crop_hint is None
        c2 = FieldAnalysisChallenge(**_base_challenge(crop_hint="rice"))
        assert c2.crop_hint == "rice"


class TestFieldAnalysisResponse:
    def _make_response(self, n_cells: int = 4) -> FieldAnalysisResponse:
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[]]},
                "properties": {
                    "cell_id": i,
                    "moisture_class": "OPTIMAL",
                    "moisture_index": 0.5,
                    "ndvi": 0.4,
                    "ndwi": 0.2,
                    "evapotranspiration_mm": 3.0,
                    "cloud_masked": False,
                    "data_source": "Sentinel-2 L2A",
                    "cell_confidence": 0.85,
                },
            }
            for i in range(n_cells)
        ]
        return FieldAnalysisResponse(
            challenge_id="test-id",
            miner_hotkey="5miner",
            geojson_grid={"type": "FeatureCollection", "features": features},
            processing_time_ms=5000,
            satellite_scene_ids=[
                "S2A_MSIL2A_20240315T030541_N0510_R075_T47PQT_20240315T070541"
            ],
            model_version="v1.0",
            model_hash="abc123",
            docker_image_ref="ghcr.io/test/miner:v1",
            dependency_spec="bittensor\nrasterio",
            confidence_overall=0.85,
            signature="testsig",
        )

    def test_deserialize_returns_dict(self):
        r = self._make_response()
        d = r.deserialize()
        assert "challenge_id" in d
        assert "geojson_grid" in d
        assert "watering_map" in d

    def test_watering_map_keyed_by_cell_id(self):
        r = self._make_response(n_cells=4)
        wmap = r._extract_watering_map()
        assert set(wmap.keys()) == {"0", "1", "2", "3"}
        for v in wmap.values():
            assert 0.0 <= v <= 1.0

    def test_get_cell_property_returns_value(self):
        r = self._make_response(n_cells=4)
        assert r.get_cell_property(0, "moisture_class") == "OPTIMAL"

    def test_get_cell_property_missing_returns_none(self):
        r = self._make_response(n_cells=4)
        assert r.get_cell_property(999, "moisture_class") is None

    def test_empty_response_defaults(self):
        r = FieldAnalysisResponse()
        assert r.geojson_grid == {}
        assert r.satellite_scene_ids == []
        assert r.confidence_overall == 0.0
