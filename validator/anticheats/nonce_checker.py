"""
validator/anticheats/nonce_checker.py
Nonce-based pre-computation prevention (§6.1).
Flags responses that are suspiciously fast given the nonce was unknown.
"""
from __future__ import annotations

from loguru import logger

from irrigation.constants import LATENCY_TOO_FAST_S


def check_nonce_timing(
    challenge_id: str,
    processing_time_ms: int,
    nonce: str,
) -> bool:
    """
    Returns True if the response passes nonce timing check.

    A response under LATENCY_TOO_FAST_S seconds cannot have made a live
    satellite API call — flag it for spectral and reproducibility audit.

    Args:
        challenge_id:       UUID of the challenge (for log correlation).
        processing_time_ms: Self-reported miner processing time.
        nonce:              The 256-bit hex nonce sent with the challenge.

    Returns:
        True  — timing looks legitimate.
        False — suspiciously fast; caller should flag for audit.
    """
    t = processing_time_ms / 1000.0
    if t < LATENCY_TOO_FAST_S:
        logger.warning(
            f"ANTI-CHEAT: challenge={challenge_id} response in {t:.2f}s "
            f"(nonce={nonce[:8]}…) — suspiciously fast, flagging for audit"
        )
        return False
    return True
