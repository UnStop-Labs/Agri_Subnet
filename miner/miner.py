"""
miner/miner.py
Full miner implementation. Receives FieldAnalysisChallenge, fetches
Sentinel-2 imagery, computes NDVI/NDWI grid, returns signed response.
"""
from __future__ import annotations

import os
import time
from loguru import logger

import bittensor as bt

from irrigation.synapse import FieldAnalysisChallenge, FieldAnalysisResponse
from irrigation.constants import CHALLENGE_MAX_AGE_S
from irrigation.utils.geo import centroid_and_area_to_bbox
from irrigation.utils.signing import (
    compute_grid_hash,
    compute_model_hash,
    sign_response,
)
from miner.satellite.copernicus import CopernicusClient
from miner.processing.ndvi import compute_ndvi_from_geotiff
from miner.processing.ndwi import compute_ndwi_from_geotiff
from miner.processing.grid_builder import build_geojson_grid


class IrrigationMiner(bt.BaseMinorNeuron):
    """
    Bittensor miner for the Field Irrigation Intelligence Network.

    On each forward() call:
    1. Validates the challenge (age, hotkey, nonce format)
    2. Fetches the best available Sentinel-2 scene from Copernicus
    3. Computes NDVI + NDWI over the field bounding box
    4. Builds a GeoJSON grid with per-cell moisture classification
    5. Signs and returns the response
    """

    def __init__(self, config: bt.config | None = None) -> None:
        super().__init__(config=config)
        self.copernicus = CopernicusClient()
        self._copernicus_token_time: float = 0.0
        logger.info(
            f"IrrigationMiner started | hotkey={self.wallet.hotkey.ss58_address}"
        )

    def forward(self, synapse: FieldAnalysisChallenge) -> FieldAnalysisResponse:
        """Process a single challenge and return a signed response."""
        t0 = time.time()
        logger.info(
            f"Challenge received | id={synapse.challenge_id} "
            f"lat={synapse.latitude} lon={synapse.longitude} "
            f"area={synapse.area_rai} rai date={synapse.query_date}"
        )

        # ── Step 1: Validate ─────────────────────────────────────
        self._validate_challenge(synapse)

        # ── Step 2: Fetch satellite data ──────────────────────────
        bbox = centroid_and_area_to_bbox(
            synapse.latitude, synapse.longitude, synapse.area_rai
        )
        geotiff_bytes, scene_ids = self.copernicus.fetch_best_scene(
            bbox, synapse.query_date
        )
        logger.info(f"Scene downloaded: {scene_ids[0]}")

        # ── Step 3: Compute spectral indices ──────────────────────
        ndvi = compute_ndvi_from_geotiff(geotiff_bytes)
        ndwi = compute_ndwi_from_geotiff(geotiff_bytes)

        # ── Step 4: Build GeoJSON grid ────────────────────────────
        geojson_grid = build_geojson_grid(
            ndvi,
            ndwi,
            bbox,
            resolution_m=synapse.grid_resolution_m,
        )
        logger.info(
            f"Grid built: {len(geojson_grid['features'])} cells "
            f"at {synapse.grid_resolution_m}m resolution"
        )

        # ── Step 5: Sign and return ───────────────────────────────
        grid_hash = compute_grid_hash(geojson_grid)
        signature = sign_response(
            self.wallet, synapse.challenge_id, synapse.nonce, grid_hash
        )
        processing_ms = int((time.time() - t0) * 1000)
        confidence = self._compute_overall_confidence(geojson_grid)

        response = FieldAnalysisResponse(
            challenge_id=synapse.challenge_id,
            miner_hotkey=self.wallet.hotkey.ss58_address,
            geojson_grid=geojson_grid,
            processing_time_ms=processing_ms,
            satellite_scene_ids=scene_ids,
            model_version=os.environ.get("MODEL_VERSION", "v1.1.0"),
            model_hash=compute_model_hash(
                os.environ.get("MODEL_PATH", "model/weights.pt")
            ),
            docker_image_ref=os.environ.get(
                "DOCKER_IMAGE_REF",
                "ghcr.io/yourorg/irrigation-miner:v1.1.0",
            ),
            dependency_spec=self._read_dependency_spec(),
            confidence_overall=confidence,
            signature=signature,
        )

        logger.info(
            f"Response ready | cells={len(geojson_grid['features'])} "
            f"time={processing_ms}ms confidence={confidence:.3f}"
        )
        return response

    # ── Private helpers ───────────────────────────────────────────

    def _validate_challenge(self, synapse: FieldAnalysisChallenge) -> None:
        """Reject stale or malformed challenges."""
        age = time.time() - synapse.timestamp_utc
        if age > CHALLENGE_MAX_AGE_S:
            raise ValueError(
                f"Challenge too old: {age:.0f}s > {CHALLENGE_MAX_AGE_S}s limit"
            )
        if not synapse.nonce or len(synapse.nonce) < 32:
            raise ValueError("Invalid or missing nonce")

        # Phase 2: on-chain validator_hotkey verification
        # Verify that synapse.validator_hotkey is a registered validator in the
        # subnet metagraph before processing the challenge.
        # Implementation requires:
        #   metagraph = self.subtensor.metagraph(self.config.netuid)
        #   validator_uids = [uid for uid in metagraph.uids if metagraph.validator_permit[uid]]
        #   validator_hotkeys = [metagraph.hotkeys[uid] for uid in validator_uids]
        #   if synapse.validator_hotkey not in validator_hotkeys:
        #       raise ValueError(f"Unknown validator hotkey: {synapse.validator_hotkey}")
        # Uncomment and adapt once metagraph access is confirmed stable.

    def _compute_overall_confidence(self, geojson_grid: dict) -> float:
        """Average cell_confidence across non-cloud-masked cells."""
        import numpy as np

        confidences = [
            f["properties"]["cell_confidence"]
            for f in geojson_grid.get("features", [])
            if not f["properties"].get("cloud_masked", False)
        ]
        if not confidences:
            return 0.0
        return round(float(np.mean(confidences)), 3)

    def _read_dependency_spec(self) -> str:
        """Read requirements.txt if present, otherwise return a placeholder."""
        try:
            with open("requirements.txt") as f:
                return f.read()
        except FileNotFoundError:
            return "# requirements.txt not found — see pyproject.toml"
