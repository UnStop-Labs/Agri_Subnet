"""
irrigation/utils — geospatial and cryptographic helpers.

Primary exports:
    geo        : BoundingBox, centroid_and_area_to_bbox, build_grid_cells, classify_moisture
    signing    : generate_nonce, compute_grid_hash, sign_response, verify_signature
    logging    : setup_logging
"""
from irrigation.utils.geo import (
    BoundingBox,
    centroid_and_area_to_bbox,
    build_grid_cells,
    classify_moisture,
)
from irrigation.utils.signing import (
    generate_nonce,
    compute_grid_hash,
    compute_model_hash,
    sign_response,
    verify_signature,
)
from irrigation.utils.logging import setup_logging

__all__ = [
    "BoundingBox",
    "centroid_and_area_to_bbox",
    "build_grid_cells",
    "classify_moisture",
    "generate_nonce",
    "compute_grid_hash",
    "compute_model_hash",
    "sign_response",
    "verify_signature",
    "setup_logging",
]
