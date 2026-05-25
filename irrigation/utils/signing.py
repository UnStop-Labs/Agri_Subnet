"""
irrigation/utils/signing.py
Cryptographic signing utilities for miner responses.
"""
from __future__ import annotations

import hashlib
import json
import secrets

from irrigation.constants import NONCE_BITS


def generate_nonce() -> str:
    """Generate a fresh 256-bit hex nonce for a challenge."""
    return secrets.token_hex(NONCE_BITS // 8)


def compute_grid_hash(geojson_grid: dict) -> str:
    """SHA-256 of the canonical JSON representation of the grid."""
    canonical = json.dumps(geojson_grid, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def compute_model_hash(model_path: str) -> str:
    """SHA-256 of a model artifact file on disk."""
    import os

    if not os.path.exists(model_path):
        return "no-artifact"
    h = hashlib.sha256()
    with open(model_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_response(wallet, challenge_id: str, nonce: str, grid_hash: str) -> str:
    """
    Sign: challenge_id + nonce + grid_hash using the miner's hotkey.
    Returns hex-encoded signature.
    """
    payload = f"{challenge_id}{nonce}{grid_hash}".encode()
    return wallet.hotkey.sign(payload).hex()


def verify_signature(
    hotkey_ss58: str,
    challenge_id: str,
    nonce: str,
    grid_hash: str,
    signature_hex: str,
) -> bool:
    """Verify a miner's response signature. Returns True if valid."""
    import bittensor as bt

    try:
        keypair = bt.Keypair(ss58_address=hotkey_ss58)
        payload = f"{challenge_id}{nonce}{grid_hash}".encode()
        return keypair.verify(payload, bytes.fromhex(signature_hex))
    except Exception:
        return False
