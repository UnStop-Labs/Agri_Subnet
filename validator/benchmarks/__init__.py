"""
validator/benchmarks — synthetic and canary benchmark datasets.

Primary exports:
    CANARY_FIELDS            — list of canary field dicts (§6.3)
    build_canary_ground_truth — build {cell_id: class} for a canary field
    load_synthetic_benchmarks — load synthetic benchmarks from file or built-ins
    build_ground_truth        — build ground truth dict from a benchmark entry
    sample_spotcheck          — randomly select a benchmark for spot-checking
"""
from validator.benchmarks.canary_fields import CANARY_FIELDS, build_canary_ground_truth
from validator.benchmarks.synthetic import (
    load_synthetic_benchmarks,
    build_ground_truth,
    sample_spotcheck,
)

__all__ = [
    "CANARY_FIELDS",
    "build_canary_ground_truth",
    "load_synthetic_benchmarks",
    "build_ground_truth",
    "sample_spotcheck",
]
