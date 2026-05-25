"""
irrigation/protocol.py
Protocol version metadata and network-level constants for the
Field Irrigation Intelligence Network subnet.
"""
from __future__ import annotations

# Bump this whenever the synapse schema changes in a breaking way.
PROTOCOL_VERSION: int = 1

# Human-readable release tag
PROTOCOL_VERSION_STR: str = "1.1.0"

# Minimum miner protocol version the validator will accept responses from.
MIN_MINER_PROTOCOL_VERSION: int = 1

# Axon request header injected by the validator so miners can gate on version.
PROTOCOL_HEADER: str = "X-Irrigation-Protocol-Version"

# Name registered in the Bittensor metagraph
SUBNET_NAME: str = "irrigation"

__all__ = [
    "PROTOCOL_VERSION",
    "PROTOCOL_VERSION_STR",
    "MIN_MINER_PROTOCOL_VERSION",
    "PROTOCOL_HEADER",
    "SUBNET_NAME",
]
