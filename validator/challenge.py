"""
validator/challenge.py
Generates and broadcasts FieldAnalysisChallenge synapses to all miners.
Handles nonce generation, canary injection, and challenge ID tracking.
"""
from __future__ import annotations

import uuid
import time
import random
from typing import List, Tuple, Optional

from loguru import logger
import bittensor as bt

from irrigation.synapse import FieldAnalysisChallenge, FieldAnalysisResponse
from irrigation.utils.signing import generate_nonce
from irrigation.constants import CANARY_INJECTION_RATE
from validator.benchmarks.canary_fields import CANARY_FIELDS


class ChallengeIssuer:
    """
    Issues challenges to miners.
    Randomly injects canary fields at rate CANARY_INJECTION_RATE.
    """

    def __init__(
        self,
        wallet: bt.wallet,
        subtensor: bt.subtensor,
        netuid: int,
    ) -> None:
        self.wallet    = wallet
        self.subtensor = subtensor
        self.netuid    = netuid
        # challenge_id → (challenge, is_canary, ground_truth)
        self._issued: dict = {}

    def create_challenge(
        self,
        latitude: float,
        longitude: float,
        area_rai: float,
        query_date: str,
        grid_resolution_m: int = 20,
        crop_hint: Optional[str] = None,
        force_canary: bool = False,
    ) -> Tuple[FieldAnalysisChallenge, bool, Optional[dict]]:
        """
        Build a challenge. May substitute a canary field.

        Returns:
            (challenge, is_canary, ground_truth_or_None)
        """
        is_canary = force_canary or (random.random() < CANARY_INJECTION_RATE)

        if is_canary:
            canary = random.choice(CANARY_FIELDS)
            latitude         = canary["latitude"]
            longitude        = canary["longitude"]
            area_rai         = canary["area_rai"]
            ground_truth: Optional[dict] = canary.get("ground_truth")
            logger.debug(f"Injecting canary field: {canary['name']}")
        else:
            ground_truth = None

        challenge = FieldAnalysisChallenge(
            challenge_id=str(uuid.uuid4()),
            validator_hotkey=self.wallet.hotkey.ss58_address,
            latitude=latitude,
            longitude=longitude,
            area_rai=area_rai,
            query_date=query_date,
            grid_resolution_m=grid_resolution_m,
            crop_hint=crop_hint,
            nonce=generate_nonce(),
            timestamp_utc=int(time.time()),
        )
        self._issued[challenge.challenge_id] = (challenge, is_canary, ground_truth)
        return challenge, is_canary, ground_truth

    def get_issued(
        self, challenge_id: str
    ) -> Optional[Tuple[FieldAnalysisChallenge, bool, Optional[dict]]]:
        """Retrieve a previously issued challenge by ID."""
        return self._issued.get(challenge_id)

    def broadcast(
        self,
        challenge: FieldAnalysisChallenge,
        dendrite: bt.dendrite,
        axons: List[bt.AxonInfo],
        timeout: float = 90.0,
    ) -> List[Optional[FieldAnalysisResponse]]:
        """
        Send the challenge to all miner axons in parallel.
        Returns list of responses (one per axon, None if timeout/error).
        """
        logger.info(
            f"Broadcasting challenge {challenge.challenge_id} to {len(axons)} miners"
        )
        responses = dendrite.query(
            axons=axons,
            synapse=challenge,
            deserialize=False,
            timeout=timeout,
        )
        valid = [r for r in responses if r is not None]
        logger.info(
            f"Received {len(valid)}/{len(axons)} responses "
            f"for challenge {challenge.challenge_id}"
        )
        return responses
