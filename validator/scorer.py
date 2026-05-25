"""
validator/scorer.py
Full multi-dimensional scoring implementation.
Spec: §5 — Score-Per-Task Framework, EMA aggregation, quality floor.
"""
from __future__ import annotations

import numpy as np
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

from loguru import logger

from irrigation.synapse import FieldAnalysisChallenge, FieldAnalysisResponse
from irrigation.constants import (
    SCORE_WEIGHTS,
    EMA_ALPHA,
    EMA_WINDOW,
    QUALITY_FLOOR,
    LATENCY_TOO_FAST_S,
    LATENCY_IDEAL_MAX_S,
    LATENCY_OK_MAX_S,
    LATENCY_MARGINAL_MAX_S,
    NDVI_RANGE,
    NDWI_RANGE,
    MAX_CLOUD_FRACTION_NO_PENALTY,
    SCENE_FRESHNESS_DAYS,
    SCENE_STALE_PENALTY_DAYS,
)


class MinerScorer:
    """
    Implements §5 of the Field Irrigation Intelligence Network spec v1.1.

    Usage::
        scorer = MinerScorer()
        task_score = scorer.score_task(uid, challenge, response, all_responses)
        final = scorer.final_score(uid)
        weights = scorer.compute_weights(all_uids)
    """

    def __init__(self) -> None:
        self._history: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=EMA_WINDOW)
        )
        self._dimension_log: Dict[int, list] = defaultdict(list)
        # Phase 2: ECE (Expected Calibration Error) tracker per miner
        self._calibration_log: Dict[int, list] = defaultdict(list)

    # ── Public API ────────────────────────────────────────────────

    def score_task(
        self,
        uid: int,
        challenge: FieldAnalysisChallenge,
        response: FieldAnalysisResponse,
        all_responses: List[FieldAnalysisResponse],
        ground_truth: Optional[dict] = None,
        docker_rerun_match: Optional[float] = None,
    ) -> float:
        """
        Score one miner response across all five dimensions.
        Appends to EMA history. Returns task score 0–1.

        Args:
            uid:               Miner's on-chain UID.
            challenge:         The original challenge issued.
            response:          This miner's response.
            all_responses:     All miner responses to this challenge (for consensus).
            ground_truth:      Dict {cell_id_str: moisture_class} for synthetic tasks.
            docker_rerun_match: 0–1 from validator Docker re-run (None if not run yet).
        """
        dims = {
            "spatial":         self._score_spatial(response, all_responses, ground_truth),
            "spectral":        self._score_spectral(response),
            "temporal":        self._score_temporal(challenge, response),
            "reproducibility": self._score_reproducibility(response, docker_rerun_match),
            "latency":         self._score_latency(response.processing_time_ms),
        }
        task_score = sum(SCORE_WEIGHTS[d] * s for d, s in dims.items())
        task_score = float(np.clip(task_score, 0.0, 1.0))

        self._history[uid].append(task_score)
        self._dimension_log[uid].append(dims)

        logger.debug(
            f"uid={uid} | task={task_score:.3f} | "
            + " ".join(f"{k}={v:.2f}" for k, v in dims.items())
        )
        return task_score

    def final_score(self, uid: int) -> float:
        """
        EMA over stored task scores → final miner score.
        Returns 0.0 if below quality floor or no history.
        """
        history = list(self._history[uid])
        if not history:
            return 0.0
        ema = history[0]
        for s in history[1:]:
            ema = EMA_ALPHA * s + (1 - EMA_ALPHA) * ema
        return ema if ema >= QUALITY_FLOOR else 0.0

    def compute_weights(self, uids: List[int]) -> Dict[int, float]:
        """
        Normalise final scores to sum to exactly 1.0 for on-chain weight setting.
        Spec §7.1.

        Rounds all weights to 6 decimal places, then corrects the largest weight
        to absorb any floating-point residual so the sum is precisely 1.0.
        """
        scores = {uid: self.final_score(uid) for uid in uids}
        total = sum(scores.values())
        if total == 0.0:
            return {uid: 0.0 for uid in uids}

        weights = {uid: round(s / total, 6) for uid, s in scores.items()}

        # Absorb rounding error into the largest-weight miner
        residual = round(1.0 - sum(weights.values()), 6)
        if residual and weights:
            max_uid = max(weights, key=weights.__getitem__)
            weights[max_uid] = round(weights[max_uid] + residual, 6)

        return weights

    def last_dimensions(self, uid: int) -> Optional[dict]:
        """Return the most recent per-dimension breakdown for a miner."""
        log = self._dimension_log.get(uid)
        return log[-1] if log else None

    def track_calibration_error(
        self, uid: int, predicted_confidence: float, actual_accuracy: float
    ) -> None:
        """
        Phase 2 — Confidence Calibration (ECE).
        Track predicted vs. actual accuracy for confidence signal calibration.

        Full implementation requires:
        - Binning predicted_confidence into 10 buckets (0–0.1, 0.1–0.2, …, 0.9–1.0).
        - For each bucket, computing |mean_predicted - mean_actual| (calibration gap).
        - Summing bucket gaps weighted by fraction of samples to get ECE.
        - Penalising overconfident miners (confidence >> accuracy) in scoring.
        """
        raise NotImplementedError(
            "Phase 2: implement ECE tracking. "
            "Bin (predicted_confidence, actual_accuracy) pairs by confidence bucket, "
            "compute |mean_predicted - mean_accuracy| per bucket, "
            "weight by bucket fraction, and sum to get the ECE score. "
            "Penalise miners with ECE > 0.15 in the reproducibility dimension."
        )

    # ── Dimension scorers ──────────────────────────────────────────

    def _score_spatial(
        self,
        response: FieldAnalysisResponse,
        all_responses: List[FieldAnalysisResponse],
        ground_truth: Optional[dict],
    ) -> float:
        """
        §5.3 — 35% weight.
        Uses synthetic ground truth when available; cross-miner consensus otherwise.
        """
        features = response.geojson_grid.get("features", [])
        if not features:
            return 0.0

        non_cloud = [f for f in features if not f["properties"].get("cloud_masked")]
        if not non_cloud:
            return 0.0

        if ground_truth:
            # Direct comparison against known expected outputs (§5.3.2)
            correct = sum(
                1
                for f in non_cloud
                if str(f["properties"]["cell_id"]) in ground_truth
                and f["properties"]["moisture_class"]
                == ground_truth[str(f["properties"]["cell_id"])]
            )
            return correct / len(non_cloud)

        # Cross-miner consensus (§5.3.1)
        cell_votes: Dict[str, List[str]] = defaultdict(list)
        for r in all_responses:
            if r is None:
                continue
            for feat in r.geojson_grid.get("features", []):
                p = feat["properties"]
                if not p.get("cloud_masked"):
                    cell_votes[str(p["cell_id"])].append(p["moisture_class"])

        if not cell_votes:
            return 0.5  # no consensus possible — neutral

        consensus = {
            cid: max(set(votes), key=votes.count)
            for cid, votes in cell_votes.items()
        }
        my_cells = {
            str(f["properties"]["cell_id"]): f["properties"]["moisture_class"]
            for f in non_cloud
        }
        matches = sum(
            1 for cid, cls in my_cells.items() if consensus.get(cid) == cls
        )
        return matches / len(my_cells)

    def _score_spectral(self, response: FieldAnalysisResponse) -> float:
        """
        §5.4 — 20% weight.
        Physics-bound NDVI/NDWI range checks + cloud fraction penalty.
        """
        features = response.geojson_grid.get("features", [])
        if not features:
            return 0.0

        valid_count = 0
        cloud_count = 0
        for f in features:
            p = f["properties"]
            if p.get("cloud_masked"):
                cloud_count += 1
                continue
            ndvi_ok = NDVI_RANGE[0] <= p.get("ndvi", 0.0) <= NDVI_RANGE[1]
            ndwi_ok = NDWI_RANGE[0] <= p.get("ndwi", 0.0) <= NDWI_RANGE[1]
            mi_ok   = 0.0 <= p.get("moisture_index", 0.0) <= 1.0
            if ndvi_ok and ndwi_ok and mi_ok:
                valid_count += 1

        cloud_fraction = cloud_count / len(features)
        non_cloud      = len(features) - cloud_count
        base           = valid_count / max(non_cloud, 1)

        # Penalise excessive cloud masking (§5.4)
        if cloud_fraction > MAX_CLOUD_FRACTION_NO_PENALTY:
            penalty = cloud_fraction - MAX_CLOUD_FRACTION_NO_PENALTY
            base = base * (1.0 - penalty)

        return float(np.clip(base, 0.0, 1.0))

    def _score_temporal(
        self,
        challenge: FieldAnalysisChallenge,
        response: FieldAnalysisResponse,
    ) -> float:
        """
        §5.5 — 20% weight.
        Checks satellite scene freshness against query_date.
        """
        if not response.satellite_scene_ids:
            return 0.0

        try:
            query_dt = datetime.fromisoformat(
                challenge.query_date.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            return 0.5

        scene_id = response.satellite_scene_ids[0]
        try:
            # Sentinel-2 scene ID format: S2A_MSIL2A_20240315T...
            date_str = scene_id.split("_")[2][:8]
            scene_dt = datetime.strptime(date_str, "%Y%m%d").replace(
                tzinfo=timezone.utc
            )
        except (IndexError, ValueError):
            logger.warning(f"Could not parse scene date from: {scene_id}")
            return 0.2  # unparseable — suspicious

        delta_days = abs(
            (query_dt.replace(tzinfo=timezone.utc) - scene_dt).days
        )

        if delta_days <= SCENE_FRESHNESS_DAYS:
            return 1.0
        elif delta_days <= SCENE_STALE_PENALTY_DAYS:
            # Linear decay from 1.0 at 14 days to 0.6 at 30 days
            decay = (delta_days - SCENE_FRESHNESS_DAYS) / (
                SCENE_STALE_PENALTY_DAYS - SCENE_FRESHNESS_DAYS
            )
            return round(1.0 - 0.4 * decay, 3)
        else:
            return 0.0

    def _score_reproducibility(
        self,
        response: FieldAnalysisResponse,
        docker_rerun_match: Optional[float],
    ) -> float:
        """
        §5.6 — 15% weight.
        Three sub-checks: output match (50%), determinism (30%), env validity (20%).
        """
        # Environment validity — are the reproducibility artifacts present?
        env_valid = 1.0 if (
            response.docker_image_ref
            and response.dependency_spec
            and response.model_hash
            and response.model_hash != "no-artifact"
        ) else 0.0

        if docker_rerun_match is None:
            # Not yet re-run — partial credit, flag for later async check
            return round(0.50 * 0.5 + 0.30 * 0.5 + 0.20 * env_valid, 3)

        output_match = float(np.clip(docker_rerun_match, 0.0, 1.0))
        determinism  = output_match  # high match implies determinism

        return round(
            0.50 * output_match + 0.30 * determinism + 0.20 * env_valid,
            3,
        )

    def _score_latency(self, processing_time_ms: int) -> float:
        """§5.7 — 10% weight. See latency table in constants."""
        t = processing_time_ms / 1000.0
        if t < LATENCY_TOO_FAST_S:
            return 0.0   # suspicious — flagged
        elif t <= LATENCY_IDEAL_MAX_S:
            return 1.0
        elif t <= LATENCY_OK_MAX_S:
            return 0.7
        elif t <= LATENCY_MARGINAL_MAX_S:
            return 0.4
        else:
            return 0.0   # timeout
