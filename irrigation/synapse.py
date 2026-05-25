"""
irrigation/synapse.py
Bittensor synapse definitions for the Field Irrigation Intelligence Network.
Spec: §4.1 (FieldAnalysisChallenge) and §4.2 (FieldAnalysisResponse).
"""
from __future__ import annotations

import bittensor as bt
from typing import Optional, List
from pydantic import Field, field_validator


class FieldAnalysisChallenge(bt.Synapse):
    """
    Validator → Miner challenge message.

    Issued once per tempo per registered miner. The nonce prevents
    pre-computation; timestamp_utc enforces a 90-second freshness window.
    """

    # Identity
    challenge_id: str = Field(..., description="UUID — unique per challenge instance")
    validator_hotkey: str = Field(..., description="SS58 address of issuing validator")

    # Field geometry
    latitude: float = Field(..., description="WGS84 centroid latitude")
    longitude: float = Field(..., description="WGS84 centroid longitude")
    area_rai: float = Field(..., description="Field area in Thai Rai (1 Rai = 1600 m²)")

    # Task parameters
    query_date: str = Field(..., description="ISO 8601 target date for analysis")
    grid_resolution_m: int = Field(default=20, description="Output grid cell size in metres")
    crop_hint: Optional[str] = Field(default=None, description="Optional crop type hint")

    # Security
    nonce: str = Field(..., description="256-bit hex random — prevents pre-computation")
    timestamp_utc: int = Field(..., description="Unix timestamp — miner rejects if > 90s old")

    @field_validator("area_rai")
    @classmethod
    def area_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("area_rai must be positive")
        return v

    @field_validator("grid_resolution_m")
    @classmethod
    def resolution_must_be_valid(cls, v: int) -> int:
        if v not in (10, 20, 30, 60):
            raise ValueError("grid_resolution_m must be 10, 20, 30, or 60")
        return v


class FieldAnalysisResponse(bt.Synapse):
    """
    Miner → Validator response message.

    Contains the GeoJSON irrigation grid plus full reproducibility
    artifacts required by spec §4.2 and §4.3.
    """

    # Identity (echoed)
    challenge_id: str = Field(default="", description="Must exactly match challenge")
    miner_hotkey: str = Field(default="", description="SS58 address of responding miner")

    # Primary output
    geojson_grid: dict = Field(
        default_factory=dict,
        description="GeoJSON FeatureCollection — one Feature per grid cell",
    )

    # Audit trail
    processing_time_ms: int = Field(default=0, description="Self-reported compute time")
    satellite_scene_ids: List[str] = Field(
        default_factory=list,
        description="Exact scene IDs used — must be verifiable in ESA/USGS STAC",
    )

    # Reproducibility artifacts (§4.3 — required for non-zero repro score)
    model_version: str = Field(default="", description="Miner model version tag")
    model_hash: str = Field(default="", description="SHA-256 of submitted model artifact")
    docker_image_ref: str = Field(default="", description="Docker image ref for re-execution")
    dependency_spec: str = Field(default="", description="requirements.txt or conda env")

    # Confidence
    confidence_overall: float = Field(
        default=0.0, description="Miner self-assessed confidence 0–1"
    )

    # Cryptographic binding
    signature: str = Field(
        default="",
        description="hotkey.sign(challenge_id + nonce + sha256(geojson_grid))",
    )

    def deserialize(self) -> dict:
        return {
            "challenge_id": self.challenge_id,
            "geojson_grid": self.geojson_grid,
            "watering_map": self._extract_watering_map(),
        }

    def _extract_watering_map(self) -> dict:
        """Flatten GeoJSON → {cell_id: moisture_index} for quick validator access."""
        result: dict = {}
        for feature in self.geojson_grid.get("features", []):
            props = feature.get("properties", {})
            result[str(props.get("cell_id", ""))] = props.get("moisture_index", 0.0)
        return result

    def get_cell_property(self, cell_id: int, prop: str):
        for f in self.geojson_grid.get("features", []):
            if f["properties"].get("cell_id") == cell_id:
                return f["properties"].get(prop)
        return None
