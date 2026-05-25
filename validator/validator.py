"""
validator/validator.py
Main validator loop. Issues challenges every tempo, collects responses,
scores miners, and sets on-chain weights.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger
import bittensor as bt

from irrigation.synapse import FieldAnalysisChallenge, FieldAnalysisResponse
from validator.challenge import ChallengeIssuer
from validator.scorer import MinerScorer
from validator.anticheats.nonce_checker import check_nonce_timing
from validator.anticheats.scene_auditor import verify_scene_ids
from validator.anticheats.plagiarism import detect_plagiarism, penalise_sybil_cluster
from validator.anticheats.docker_runner import rerun_miner_container
from validator.benchmarks.canary_fields import CANARY_FIELDS, build_canary_ground_truth
from irrigation.constants import CANARY_INJECTION_RATE


class IrrigationValidator(bt.BaseValidatorNeuron):
    """
    Validator neuron for the Field Irrigation Intelligence Network.

    Each tempo:
    1. Fetch metagraph — get all registered miner axons.
    2. Issue a challenge (possibly a canary) to all miners.
    3. Collect responses within 90 s timeout.
    4. Run anti-cheat checks (nonce timing, scene audit, plagiarism).
    5. Score all responses with MinerScorer.
    6. Set on-chain weights via subtensor.set_weights().
    """

    def __init__(self, config: Optional[bt.config] = None) -> None:
        super().__init__(config=config)
        self.scorer = MinerScorer()
        self.issuer = ChallengeIssuer(self.wallet, self.subtensor, self.config.netuid)
        logger.info(
            f"IrrigationValidator started | "
            f"hotkey={self.wallet.hotkey.ss58_address} "
            f"netuid={self.config.netuid}"
        )

    async def forward(self) -> None:
        """Called once per tempo by the Bittensor base class."""
        metagraph = self.metagraph
        axons     = [metagraph.axons[uid] for uid in range(len(metagraph.axons))]
        uids      = list(range(len(axons)))

        if not axons:
            logger.warning("No miners registered — skipping tempo")
            return

        # ── Issue challenge ────────────────────────────────────────────────
        # Phase 2: source lat/lon/area from a real farm request queue.
        # See the Phase 2 stub below for the farm job queue interface.
        lat, lon, area = self._get_next_farm_location()

        challenge, is_canary, ground_truth = self.issuer.create_challenge(
            latitude=lat,
            longitude=lon,
            area_rai=area,
            query_date=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            grid_resolution_m=int(os.environ.get("GRID_RESOLUTION_M", "20")),
        )

        # ── Broadcast & collect responses ──────────────────────────────────
        responses: List[Optional[FieldAnalysisResponse]] = self.issuer.broadcast(
            challenge,
            self.dendrite,
            axons,
            timeout=float(os.environ.get("MAX_RESPONSE_TIMEOUT_S", "90")),
        )

        # ── Anti-cheat pass ────────────────────────────────────────────────
        uid_responses: dict = {}
        for uid, response in zip(uids, responses):
            if response is None:
                continue

            # Nonce timing check (§6.1)
            if not check_nonce_timing(
                challenge.challenge_id,
                response.processing_time_ms,
                challenge.nonce,
            ):
                logger.warning(f"uid={uid} flagged for fast response — auditing")

            # Scene ID audit (§6.2)
            scene_score = verify_scene_ids(
                response.satellite_scene_ids,
                challenge.latitude,
                challenge.longitude,
                challenge.query_date,
            )
            if scene_score < 0.5:
                logger.warning(f"uid={uid} scene audit failed: {scene_score:.2f}")

            uid_responses[uid] = response

        # Plagiarism / Sybil detection (§6.5)
        flagged_pairs = detect_plagiarism(uid_responses)

        # ── Build ground truth for canary fields ───────────────────────────
        if is_canary and ground_truth is None:
            # Auto-build from expected class using first response cell count
            first = next(iter(uid_responses.values()), None)
            if first:
                n_cells = len(first.geojson_grid.get("features", []))
                for cf in CANARY_FIELDS:
                    if abs(cf["latitude"] - challenge.latitude) < 0.001:
                        ground_truth = build_canary_ground_truth(cf, n_cells)
                        break

        # ── Phase 1 qualification gate (Phase 2 stub) ─────────────────────
        # self._filter_to_qualified_miners(uid_responses, challenge)

        # ── Score all miners ───────────────────────────────────────────────
        for uid, response in uid_responses.items():
            self.scorer.score_task(
                uid=uid,
                challenge=challenge,
                response=response,
                all_responses=list(uid_responses.values()),
                ground_truth=ground_truth,
                docker_rerun_match=None,  # async Docker re-run handled separately
            )

        # ── Compute & set on-chain weights ─────────────────────────────────
        raw_weights = self.scorer.compute_weights(uids)

        # Apply Sybil penalty
        raw_weights = penalise_sybil_cluster(flagged_pairs, raw_weights)

        weight_list = [raw_weights.get(uid, 0.0) for uid in uids]
        uid_list    = uids

        logger.info(
            f"Setting weights | non-zero={sum(1 for w in weight_list if w > 0)} "
            f"/ {len(weight_list)} miners"
        )

        self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=self.config.netuid,
            uids=uid_list,
            weights=weight_list,
            wait_for_inclusion=False,
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _get_next_farm_location(self) -> tuple[float, float, float]:
        """
        Return (latitude, longitude, area_rai) for the next challenge.

        Phase 2: replace the hardcoded fallback with a real farm job queue.
        The queue should be an API or database table populated by registered
        farms requesting irrigation analysis. Pull the next pending job,
        mark it as in-progress, and return its coordinates.

        Farm job queue implementation requirements:
        - POST /jobs endpoint for farms to submit analysis requests.
        - GET /jobs/next to pop the oldest pending job.
        - PATCH /jobs/{id}/complete after scoring and weight-setting.
        - Store lat/lon/area/crop_hint/priority per job.
        """
        # Hardcoded fallback for Phase 1 / testnet operation
        return 14.471, 100.131, 25.0

    def _filter_to_qualified_miners(
        self,
        uid_responses: dict,
        challenge: FieldAnalysisChallenge,
    ) -> None:
        """
        Phase 2 — Phase 1 qualification gate.

        Only broadcast to miners that have passed Phase 1 synthetic benchmarks.
        Track per-miner qualification state in a persistent store (SQLite or Redis).

        Implementation required:
        - Maintain a {uid: qualification_status} store.
        - "qualification_status" ∈ {UNQUALIFIED, QUALIFYING, QUALIFIED, BANNED}.
        - QUALIFIED: miner scored ≥ 0.5 on ≥ 3 synthetic benchmark challenges.
        - BANNED: miner was caught plagiarising (Sybil cluster) or failed 5+ canaries.
        - Only include QUALIFIED miners in the axons list passed to self.issuer.broadcast().
        - Newly registered miners start UNQUALIFIED and receive synthetic-only challenges.
        """
        raise NotImplementedError(
            "Phase 2: implement Phase 1 qualification gate. "
            "Maintain a persistent {uid: QualificationStatus} store. "
            "Send synthetic-only challenges to UNQUALIFIED miners. "
            "Promote to QUALIFIED after ≥3 synthetic passes with score ≥ 0.5. "
            "Exclude BANNED uids from all future challenges."
        )
