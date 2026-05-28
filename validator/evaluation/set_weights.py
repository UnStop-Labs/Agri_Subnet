"""
Set on-chain miner weights based on 24-hour rolling average scores.

Weight formula from the design doc:
  weight[i] = smoothed_score[i] / Σ smoothed_score[j]
  Miners with score < 0.10 receive weight = 0 (quality floor).

Yuma Consensus reconciles disagreements between multiple validators.
"""

import asyncio
import hashlib
import os
import struct
import time
from typing import List

from fiber.chain import chain_utils, interface
from fiber.chain.fetch_nodes import get_nodes_for_netuid
from fiber.logging_utils import get_logger

from validator.config import (
    HOTKEY_NAME,
    NETUID,
    SUBTENSOR_ADDRESS,
    SUBTENSOR_NETWORK,
    VERSION_KEY,
    WALLET_NAME,
)
from validator.db.operations import DatabaseManager

logger = get_logger(__name__)

QUALITY_FLOOR = 0.10


# ---------------------------------------------------------------------------
# SCALE encoding helpers — used to reproduce the on-chain commit hash
# ---------------------------------------------------------------------------

def _scale_u16(v: int) -> bytes:
    return struct.pack('<H', v & 0xFFFF)


def _scale_compact(n: int) -> bytes:
    if n < 64:
        return bytes([n << 2])
    elif n < 16384:
        return struct.pack('<H', (n << 2) | 1)
    else:
        return struct.pack('<I', (n << 2) | 2)


def _scale_vec_u16(vals: list) -> bytes:
    return _scale_compact(len(vals)) + b''.join(_scale_u16(v) for v in vals)


def _scale_u64(v: int) -> bytes:
    return struct.pack('<Q', v)


def _commit_hash(netuid: int, uids: list, values: list, salt: list, version_key: int) -> str:
    """Blake2-256 of SCALE(netuid, uids, values, salt, version_key) — matches subtensor on-chain logic."""
    encoded = (
        _scale_u16(netuid) +
        _scale_vec_u16(uids) +
        _scale_vec_u16(values) +
        _scale_vec_u16(salt) +
        _scale_u64(version_key)
    )
    digest = hashlib.blake2b(encoded, digest_size=32).digest()
    return '0x' + digest.hex()


def _current_block(substrate) -> int:
    try:
        return substrate.get_block()['header']['number']
    except Exception:
        return substrate.query('System', 'Number').value


# ---------------------------------------------------------------------------
# Weight-setting implementations
# ---------------------------------------------------------------------------

def _set_weights_commit_reveal(substrate, keypair, node_ids, weights_u16, netuid, version_key):
    """Use commit_weights + reveal_weights for chains with commit-reveal enabled."""
    salt = [int.from_bytes(os.urandom(2), 'little') for _ in range(8)]
    commit = _commit_hash(netuid, node_ids, weights_u16, salt, version_key)
    logger.info(f"Committing weight hash {commit} (salt={salt})")

    call = substrate.compose_call(
        call_module='SubtensorModule',
        call_function='commit_weights',
        call_params={'netuid': netuid, 'commit_hash': commit},
    )
    extrinsic = substrate.create_signed_extrinsic(call=call, keypair=keypair)
    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    if not receipt.is_success:
        logger.error(f"commit_weights failed: {receipt.error_message}")
        return False

    # Fetch the reveal interval from chain (default 1 if not found)
    try:
        interval = substrate.query('SubtensorModule', 'CommitRevealWeightsInterval', [netuid]).value or 1
    except Exception:
        interval = 1

    start_block = _current_block(substrate)
    target_block = start_block + interval
    logger.info(f"Committed at block {start_block}. Waiting {interval} blocks (until {target_block}) to reveal…")

    while True:
        cur = _current_block(substrate)
        if cur >= target_block:
            break
        time.sleep(0.5)

    logger.info(f"Revealing weights at block {_current_block(substrate)}")
    reveal_call = substrate.compose_call(
        call_module='SubtensorModule',
        call_function='reveal_weights',
        call_params={
            'netuid': netuid,
            'uids': node_ids,
            'values': weights_u16,
            'salt': salt,
            'version_key': version_key,
        },
    )
    extrinsic = substrate.create_signed_extrinsic(call=reveal_call, keypair=keypair)
    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    if not receipt.is_success:
        logger.error(f"reveal_weights failed: {receipt.error_message}")
        return False
    logger.info("reveal_weights succeeded")
    return True


def _set_weights_direct(substrate, keypair, node_ids, node_weights, netuid, version_key):
    """Try direct set_weights; if commit-reveal is enabled fall back to commit+reveal flow."""
    weights_u16 = [min(65535, int(w * 65535)) for w in node_weights]
    logger.info(f"Submitting set_weights: netuid={netuid} version_key={version_key} dests={node_ids} weights={weights_u16}")

    call = substrate.compose_call(
        call_module='SubtensorModule',
        call_function='set_weights',
        call_params={
            'netuid': netuid,
            'dests': node_ids,
            'weights': weights_u16,
            'version_key': version_key,
        },
    )
    extrinsic = substrate.create_signed_extrinsic(call=call, keypair=keypair)
    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)

    if receipt.is_success:
        return True

    error = receipt.error_message or {}
    if isinstance(error, dict) and error.get('name') == 'CommitRevealEnabled':
        logger.info("Chain requires commit-reveal — switching to commit+reveal flow")
        return _set_weights_commit_reveal(substrate, keypair, node_ids, weights_u16, netuid, version_key)

    logger.error(f"set_weights chain error: {error}")
    return False


# ---------------------------------------------------------------------------
# Main entry point called by the weights loop
# ---------------------------------------------------------------------------

async def set_weights(db_manager: DatabaseManager) -> None:
    try:
        substrate = interface.get_substrate(
            subtensor_network=SUBTENSOR_NETWORK,
            subtensor_address=SUBTENSOR_ADDRESS,
        )
        keypair = chain_utils.load_hotkey_keypair(WALLET_NAME, HOTKEY_NAME)

        nodes = get_nodes_for_netuid(substrate=substrate, netuid=NETUID)

        if not nodes:
            logger.info("No nodes found — skipping weight setting this round")
            return

        miner_scores = db_manager.get_miner_scores(lookback_hours=24)
        logger.info(f"Setting weights for {len(nodes)} nodes; have scores for {len(miner_scores)}")

        node_ids: List[int] = []
        node_weights: List[float] = []

        for node in nodes:
            nid = node.node_id
            score_data = miner_scores.get(nid, {})
            raw_score = score_data.get("final_score", 0.0)
            adjusted = raw_score if raw_score >= QUALITY_FLOOR else 0.0
            node_ids.append(nid)
            node_weights.append(adjusted)

        total = sum(node_weights)
        if total > 0:
            node_weights = [w / total for w in node_weights]
        else:
            node_weights = [1.0 / len(nodes)] * len(nodes)

        for nid, w in zip(node_ids, node_weights):
            if w > 0:
                logger.info(f"  node {nid}: weight={w:.4f}")

        # Commit-reveal can take many blocks; use a long timeout (10 min)
        success = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                _set_weights_direct,
                substrate,
                keypair,
                node_ids,
                node_weights,
                NETUID,
                VERSION_KEY,
            ),
            timeout=600.0,
        )

        if success:
            logger.info("Weights set successfully on chain")
        else:
            logger.error("set_weights returned False — check chain logs")

    except asyncio.TimeoutError:
        logger.error("set_weights timed out after 600 s")
    except Exception as exc:
        logger.error(f"set_weights error: {exc}", exc_info=True)
        raise

