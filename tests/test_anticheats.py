"""
tests/test_anticheats.py
Tests for all four anti-cheat subsystems.
"""
import pytest
import numpy as np

from validator.anticheats.nonce_checker import check_nonce_timing
from validator.anticheats.plagiarism import (
    extract_moisture_vector,
    detect_plagiarism,
    penalise_sybil_cluster,
    _cosine_similarity,
)
from validator.anticheats.docker_runner import _compare_grids
from irrigation.synapse import FieldAnalysisResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response_with_moisture(moisture_values: list) -> FieldAnalysisResponse:
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[]]},
            "properties": {
                "cell_id": i,
                "moisture_class": "OPTIMAL",
                "moisture_index": v,
                "ndvi": 0.4, "ndwi": 0.2,
                "evapotranspiration_mm": 3.0,
                "cloud_masked": False,
                "data_source": "Sentinel-2 L2A",
                "cell_confidence": 0.85,
            },
        }
        for i, v in enumerate(moisture_values)
    ]
    return FieldAnalysisResponse(
        challenge_id="test", miner_hotkey="5test",
        geojson_grid={"type": "FeatureCollection", "features": features},
        processing_time_ms=5000,
        satellite_scene_ids=["S2A_MSIL2A_20240315T030541"],
        model_version="v1", model_hash="abc", docker_image_ref="img",
        dependency_spec="bt", confidence_overall=0.8, signature="sig",
    )


# ── Nonce checker ─────────────────────────────────────────────────────────────

class TestNonceChecker:
    def test_fast_response_fails(self):
        assert check_nonce_timing("cid", 500, "abc") is False    # 0.5 s

    def test_ideal_response_passes(self):
        assert check_nonce_timing("cid", 5_000, "abc") is True   # 5 s

    def test_boundary_exactly_2s_fails(self):
        # < 2.0 s fails; 2000 ms == 2.0 s → should pass (not strictly less)
        assert check_nonce_timing("cid", 2_000, "abc") is True

    def test_1999ms_fails(self):
        assert check_nonce_timing("cid", 1_999, "abc") is False


# ── Plagiarism detector ───────────────────────────────────────────────────────

class TestPlagiarismDetection:
    def test_identical_responses_flagged(self):
        values = [0.1, 0.5, 0.7, 0.3]
        r1 = _make_response_with_moisture(values)
        r2 = _make_response_with_moisture(values)
        flagged = detect_plagiarism({1: r1, 2: r2})
        assert len(flagged) == 1
        uid_a, uid_b, sim = flagged[0]
        assert sim > 0.99

    def test_different_responses_not_flagged(self):
        r1 = _make_response_with_moisture([0.1, 0.2, 0.3, 0.4])
        r2 = _make_response_with_moisture([0.9, 0.8, 0.7, 0.6])
        flagged = detect_plagiarism({1: r1, 2: r2})
        assert len(flagged) == 0

    def test_empty_responses_not_flagged(self):
        r1 = FieldAnalysisResponse()
        r2 = FieldAnalysisResponse()
        flagged = detect_plagiarism({1: r1, 2: r2})
        assert len(flagged) == 0

    def test_mismatched_lengths_not_flagged(self):
        r1 = _make_response_with_moisture([0.5, 0.5, 0.5])
        r2 = _make_response_with_moisture([0.5, 0.5, 0.5, 0.5])
        flagged = detect_plagiarism({1: r1, 2: r2})
        assert len(flagged) == 0


class TestSybilPenalty:
    def test_cluster_penalised(self):
        scores = {1: 0.9, 2: 0.9, 3: 0.5}
        flagged = [(1, 2, 0.999)]
        penalised = penalise_sybil_cluster(flagged, scores)
        assert penalised[1] == penalised[2]
        assert penalised[1] < 0.9            # was capped
        assert penalised[3] == 0.5           # untouched

    def test_no_flagged_pairs_returns_unchanged(self):
        scores = {1: 0.7, 2: 0.5}
        penalised = penalise_sybil_cluster([], scores)
        assert penalised == scores


# ── Cosine similarity ─────────────────────────────────────────────────────────

class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        a = np.array([0.1, 0.5, 0.7])
        assert abs(_cosine_similarity(a, a) - 1.0) < 1e-6

    def test_orthogonal_vectors_score_zero(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_zero_vector_scores_zero(self):
        a = np.zeros(4)
        b = np.array([0.5, 0.3, 0.1, 0.7])
        assert _cosine_similarity(a, b) == 0.0


# ── Grid comparison ───────────────────────────────────────────────────────────

class TestCompareGrids:
    def _make_grid(self, values: dict) -> dict:
        return {
            "features": [
                {"properties": {"cell_id": cid, "moisture_index": val}}
                for cid, val in values.items()
            ]
        }

    def test_identical_grids_match_fully(self):
        g = self._make_grid({0: 0.5, 1: 0.3, 2: 0.7})
        assert _compare_grids(g, g) == 1.0

    def test_small_difference_within_tolerance(self):
        g1 = self._make_grid({0: 0.5, 1: 0.3})
        g2 = self._make_grid({0: 0.52, 1: 0.28})   # Δ ≤ 0.05
        assert _compare_grids(g1, g2) == 1.0

    def test_large_difference_fails(self):
        g1 = self._make_grid({0: 0.5, 1: 0.3})
        g2 = self._make_grid({0: 0.9, 1: 0.8})     # Δ >> 0.05
        assert _compare_grids(g1, g2) == 0.0

    def test_no_common_cells_returns_zero(self):
        g1 = self._make_grid({0: 0.5})
        g2 = self._make_grid({99: 0.5})
        assert _compare_grids(g1, g2) == 0.0

    def test_empty_grids_return_zero(self):
        assert _compare_grids({"features": []}, {"features": []}) == 0.0
