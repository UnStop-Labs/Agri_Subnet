"""
validator/benchmarks/synthetic.py
Synthetic benchmark dataset for offline validator evaluation.

Spec §5.3.2 — 10% of challenge batches are spot-checked against a
pre-computed synthetic dataset with known ground-truth moisture maps.

Each benchmark entry contains:
  - A FieldAnalysisChallenge-compatible dict (lat/lon/area/date/resolution)
  - A ground_truth dict mapping str(cell_id) → moisture_class
  - Optional metadata (crop type, source, creation date)

The synthetic benchmarks are generated from processed historical
Sentinel-2 imagery where the correct moisture classification is known.
"""
from __future__ import annotations

import json
import os
import random
from typing import List, Optional

from loguru import logger

from irrigation.constants import SYNTHETIC_SPOTCHECK_RATE


# ── Built-in synthetic cases ──────────────────────────────────────────────────
# These are minimal illustrative cases. In production, load from
# SYNTHETIC_BENCHMARK_PATH (see .env.example).

BUILTIN_SYNTHETIC_BENCHMARKS: List[dict] = [
    {
        "name": "Chao Phraya delta — irrigated rice, wet season",
        "challenge": {
            "latitude":         14.471,
            "longitude":        100.131,
            "area_rai":         25.0,
            "query_date":       "2024-07-15T06:00:00Z",
            "grid_resolution_m": 20,
            "crop_hint":        "rice",
        },
        # All cells expected OPTIMAL during wet-season rice paddy
        "ground_truth_class": "OPTIMAL",
        "n_cells": 25,   # approximate — real count depends on resolution
    },
    {
        "name": "Northeast plateau — dry season cassava",
        "challenge": {
            "latitude":         15.120,
            "longitude":        103.450,
            "area_rai":         15.0,
            "query_date":       "2024-02-10T06:00:00Z",
            "grid_resolution_m": 20,
            "crop_hint":        "cassava",
        },
        "ground_truth_class": "DRY",
        "n_cells": 20,
    },
]


def load_synthetic_benchmarks(path: Optional[str] = None) -> List[dict]:
    """
    Load synthetic benchmarks from a JSON file, falling back to built-ins.

    Args:
        path: Path to a JSON file containing a list of benchmark dicts.
              Defaults to SYNTHETIC_BENCHMARK_PATH env var, then built-ins.

    Returns:
        List of benchmark dicts, each with 'challenge' and ground truth keys.
    """
    benchmark_path = path or os.environ.get("SYNTHETIC_BENCHMARK_PATH")
    if benchmark_path and os.path.exists(benchmark_path):
        try:
            with open(benchmark_path) as f:
                data = json.load(f)
            logger.info(f"Loaded {len(data)} synthetic benchmarks from {benchmark_path}")
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load synthetic benchmarks from {benchmark_path}: {exc}")

    logger.info(
        f"Using {len(BUILTIN_SYNTHETIC_BENCHMARKS)} built-in synthetic benchmarks"
    )
    return BUILTIN_SYNTHETIC_BENCHMARKS


def build_ground_truth(benchmark: dict) -> dict:
    """
    Build a {cell_id_str: moisture_class} dict from a benchmark entry.

    All cells get the same class (uniform synthetic fields for simplicity).
    Phase 2 will support spatially heterogeneous ground truth maps loaded
    from real-world labelled datasets.
    """
    n_cells = benchmark.get("n_cells", 25)
    cls     = benchmark.get("ground_truth_class", "OPTIMAL")
    return {str(i): cls for i in range(n_cells)}


def sample_spotcheck(benchmarks: List[dict]) -> Optional[dict]:
    """
    Randomly select a benchmark for a spot-check at rate SYNTHETIC_SPOTCHECK_RATE.
    Returns None if this tempo is not selected for a spot-check.
    """
    if random.random() > SYNTHETIC_SPOTCHECK_RATE:
        return None
    return random.choice(benchmarks) if benchmarks else None
