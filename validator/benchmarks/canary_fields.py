"""
validator/benchmarks/canary_fields.py
Canary field definitions with deterministic, time-stable satellite signatures.

Spec §6.3 — permanent water bodies, arid zones, forest, urban surfaces.
Ground truth uses cell_id keys (as strings) → expected moisture_class.
For simplicity, all cells in a canary field return the same class.
"""
from __future__ import annotations

from typing import List, Optional


CANARY_FIELDS: List[dict] = [
    {
        "name": "Bhumibol Reservoir — permanent water body",
        "latitude":  17.2456,
        "longitude": 99.0234,
        "area_rai":  50.0,
        "expected_class": "WET",
        "ground_truth": None,   # populated dynamically — all cells → WET
        "_auto_gt": True,
    },
    {
        "name": "Mae Wong arid scrubland — dry zone",
        "latitude":  15.8012,
        "longitude": 99.6543,
        "area_rai":  20.0,
        "expected_class": "CRITICAL_DRY",
        "ground_truth": None,
        "_auto_gt": True,
    },
    {
        "name": "Doi Inthanon dense forest — high NDVI",
        "latitude":  18.5893,
        "longitude": 98.4862,
        "area_rai":  30.0,
        "expected_class": "OPTIMAL",
        "ground_truth": None,
        "_auto_gt": True,
    },
    {
        "name": "Bangkok urban — low NDVI impervious surface",
        "latitude":  13.7563,
        "longitude": 100.5018,
        "area_rai":  10.0,
        "expected_class": "CRITICAL_DRY",
        "ground_truth": None,
        "_auto_gt": True,
    },
]


def build_canary_ground_truth(canary: dict, n_cells: int) -> dict:
    """
    Build a {cell_id_str: moisture_class} dict for all cells in a canary field.
    All cells get the same expected class (the field is spatially uniform).

    Args:
        canary:  One entry from CANARY_FIELDS.
        n_cells: Total number of grid cells in the response (auto-detected).

    Returns:
        Dict mapping str(cell_id) → expected moisture_class for every cell.
    """
    expected: str = canary["expected_class"]
    return {str(i): expected for i in range(n_cells)}
