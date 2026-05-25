"""
tests/test_scorer.py
Tests for MinerScorer — covers all five dimensions and EMA aggregation.
"""
import time
import uuid

import pytest

from validator.scorer import MinerScorer
from irrigation.synapse import FieldAnalysisChallenge, FieldAnalysisResponse
from irrigation.constants import EMA_WINDOW, QUALITY_FLOOR


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_challenge(**kwargs) -> FieldAnalysisChallenge:
    defaults = dict(
        challenge_id=str(uuid.uuid4()),
        validator_hotkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",
        latitude=14.471,
        longitude=100.131,
        area_rai=25.0,
        query_date="2024-03-15T06:00:00Z",
        grid_resolution_m=20,
        nonce="aabbcc" * 11,
        timestamp_utc=int(time.time()),
    )
    defaults.update(kwargs)
    return FieldAnalysisChallenge(**defaults)


def make_response(
    n_cells: int = 4,
    moisture_class: str = "OPTIMAL",
    moisture_index: float = 0.5,
    ndvi: float = 0.4,
    ndwi: float = 0.2,
    processing_ms: int = 5000,
    scene_id: str = "S2A_MSIL2A_20240315T030541_N0510_R075_T47PQT_20240315T070541",
    **kwargs,
) -> FieldAnalysisResponse:
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[]]},
            "properties": {
                "cell_id": i,
                "moisture_class": moisture_class,
                "moisture_index": moisture_index,
                "ndvi": ndvi,
                "ndwi": ndwi,
                "evapotranspiration_mm": 3.0,
                "cloud_masked": False,
                "data_source": "Sentinel-2 L2A",
                "cell_confidence": 0.85,
            },
        }
        for i in range(n_cells)
    ]
    defaults = dict(
        challenge_id="test",
        miner_hotkey="5test",
        geojson_grid={"type": "FeatureCollection", "features": features},
        processing_time_ms=processing_ms,
        satellite_scene_ids=[scene_id],
        model_version="v1.0",
        model_hash="abc123",
        docker_image_ref="ghcr.io/test/miner:v1",
        dependency_spec="bittensor\nrasterio",
        confidence_overall=0.85,
        signature="sig",
    )
    defaults.update(kwargs)
    return FieldAnalysisResponse(**defaults)


# ── Latency tests ─────────────────────────────────────────────────────────────

class TestLatencyScoring:
    def test_too_fast_scores_zero(self):
        s = MinerScorer()
        assert s._score_latency(500) == 0.0        # 0.5 s — too fast

    def test_ideal_scores_one(self):
        s = MinerScorer()
        assert s._score_latency(5_000) == 1.0      # 5 s — ideal

    def test_ok_scores_point_seven(self):
        s = MinerScorer()
        assert s._score_latency(15_000) == 0.7     # 15 s — ok

    def test_marginal_scores_point_four(self):
        s = MinerScorer()
        assert s._score_latency(60_000) == 0.4     # 60 s — marginal

    def test_timeout_scores_zero(self):
        s = MinerScorer()
        assert s._score_latency(120_000) == 0.0    # 120 s — timeout

    def test_boundary_ideal_max(self):
        s = MinerScorer()
        assert s._score_latency(8_000) == 1.0      # exactly 8 s — still ideal

    def test_boundary_ok_max(self):
        s = MinerScorer()
        assert s._score_latency(30_000) == 0.7     # exactly 30 s — still ok


# ── Spectral tests ────────────────────────────────────────────────────────────

class TestSpectralScoring:
    def test_valid_bands_score_one(self):
        s = MinerScorer()
        r = make_response()
        assert s._score_spectral(r) == 1.0

    def test_out_of_range_ndvi_penalised(self):
        s = MinerScorer()
        r = make_response(ndvi=2.5)   # INVALID: > 1.0
        assert s._score_spectral(r) < 1.0

    def test_out_of_range_ndwi_penalised(self):
        s = MinerScorer()
        r = make_response(ndwi=-2.0)  # INVALID: < -1.0
        assert s._score_spectral(r) < 1.0

    def test_empty_grid_scores_zero(self):
        s = MinerScorer()
        r = make_response()
        r.geojson_grid = {"type": "FeatureCollection", "features": []}
        assert s._score_spectral(r) == 0.0

    def test_all_cloud_masked_scores_zero(self):
        s = MinerScorer()
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[]]},
                "properties": {
                    "cell_id": 0, "moisture_class": "DRY",
                    "moisture_index": 0.3, "ndvi": 0.2, "ndwi": 0.1,
                    "evapotranspiration_mm": 2.0, "cloud_masked": True,
                    "data_source": "Sentinel-2 L2A", "cell_confidence": 0.0,
                },
            }
        ]
        r = make_response()
        r.geojson_grid = {"type": "FeatureCollection", "features": features}
        # All cells cloud-masked → penalised
        score = s._score_spectral(r)
        assert score < 1.0


# ── Temporal tests ────────────────────────────────────────────────────────────

class TestTemporalScoring:
    def test_fresh_scene_scores_one(self):
        s = MinerScorer()
        c = make_challenge(query_date="2024-03-15T06:00:00Z")
        r = make_response(
            scene_id="S2A_MSIL2A_20240315T030541_N0510_R075_T47PQT_20240315T070541"
        )
        assert s._score_temporal(c, r) == 1.0

    def test_stale_scene_scores_zero(self):
        s = MinerScorer()
        c = make_challenge(query_date="2024-03-15T06:00:00Z")
        r = make_response(
            scene_id="S2A_MSIL2A_20231001T030541_N0510_R075_T47PQT_20231001T070541"
        )
        assert s._score_temporal(c, r) == 0.0

    def test_no_scene_ids_scores_zero(self):
        s = MinerScorer()
        c = make_challenge()
        r = make_response()
        r.satellite_scene_ids = []
        assert s._score_temporal(c, r) == 0.0

    def test_unparseable_scene_id_suspicious(self):
        s = MinerScorer()
        c = make_challenge()
        r = make_response(scene_id="RANDOM_GARBAGE_ID")
        score = s._score_temporal(c, r)
        assert score == 0.2  # unparseable → suspicious score


# ── Spatial tests ─────────────────────────────────────────────────────────────

class TestSpatialScoring:
    def test_ground_truth_perfect_match_scores_one(self):
        s = MinerScorer()
        r = make_response(n_cells=4, moisture_class="OPTIMAL")
        ground_truth = {"0": "OPTIMAL", "1": "OPTIMAL", "2": "OPTIMAL", "3": "OPTIMAL"}
        score = s._score_spatial(r, [r], ground_truth)
        assert score == 1.0

    def test_ground_truth_zero_match_scores_zero(self):
        s = MinerScorer()
        r = make_response(n_cells=4, moisture_class="WET")
        ground_truth = {"0": "DRY", "1": "DRY", "2": "DRY", "3": "DRY"}
        score = s._score_spatial(r, [r], ground_truth)
        assert score == 0.0

    def test_empty_response_scores_zero(self):
        s = MinerScorer()
        r = make_response()
        r.geojson_grid = {"type": "FeatureCollection", "features": []}
        assert s._score_spatial(r, [r], None) == 0.0


# ── Reproducibility tests ─────────────────────────────────────────────────────

class TestReproducibilityScoring:
    def test_env_valid_partial_credit(self):
        """Without docker rerun, valid artifacts get partial credit."""
        s = MinerScorer()
        r = make_response()
        score = s._score_reproducibility(r, docker_rerun_match=None)
        assert 0.0 < score < 1.0

    def test_perfect_docker_match_scores_high(self):
        s = MinerScorer()
        r = make_response()
        score = s._score_reproducibility(r, docker_rerun_match=1.0)
        assert score > 0.8

    def test_missing_artifacts_penalised(self):
        s = MinerScorer()
        r = make_response()
        r.docker_image_ref = ""
        r.dependency_spec  = ""
        r.model_hash       = ""
        score = s._score_reproducibility(r, docker_rerun_match=None)
        assert score < s._score_reproducibility(make_response(), docker_rerun_match=None)


# ── EMA and quality floor ─────────────────────────────────────────────────────

class TestEMAAndQualityFloor:
    def test_high_scores_above_floor(self):
        s = MinerScorer()
        c = make_challenge()
        r = make_response(processing_ms=5000)
        for _ in range(5):
            s.score_task(1, c, r, [r])
        assert s.final_score(1) >= QUALITY_FLOOR

    def test_no_history_returns_zero(self):
        s = MinerScorer()
        assert s.final_score(999) == 0.0

    def test_weights_sum_to_one(self):
        s = MinerScorer()
        c = make_challenge()
        for uid in [1, 2, 3]:
            r = make_response(processing_ms=5000)
            s.score_task(uid, c, r, [r])
        weights = s.compute_weights([1, 2, 3])
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_all_zero_scores_return_zero_weights(self):
        s = MinerScorer()
        # Never called score_task — all zeros
        weights = s.compute_weights([1, 2, 3])
        assert all(w == 0.0 for w in weights.values())

    def test_last_dimensions_returns_dict(self):
        s = MinerScorer()
        c = make_challenge()
        r = make_response()
        s.score_task(1, c, r, [r])
        dims = s.last_dimensions(1)
        assert dims is not None
        assert set(dims.keys()) == {"spatial", "spectral", "temporal", "reproducibility", "latency"}
