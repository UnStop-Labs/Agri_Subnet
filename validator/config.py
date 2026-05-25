"""
validator/config.py
Validator-specific configuration helpers.

All values are read from environment variables (loaded via python-dotenv).
Call get_validator_config() to receive a validated dict.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from loguru import logger

from irrigation.constants import (
    DEFAULT_GRID_RESOLUTION_M,
    CHALLENGE_MAX_AGE_S,
    CANARY_INJECTION_RATE,
    SYNTHETIC_SPOTCHECK_RATE,
)


def get_validator_config() -> Dict[str, Any]:
    """
    Build and return the validator configuration from environment variables.

    Returns:
        Dict of validated configuration values.
    """
    config: Dict[str, Any] = {
        # Wallet
        "wallet_name":   os.environ.get("WALLET_NAME",   "default"),
        "wallet_hotkey": os.environ.get("WALLET_HOTKEY", "default"),
        # Bittensor network
        "subtensor_network": os.environ.get("SUBTENSOR_NETWORK", "finney"),
        "netuid":            int(os.environ.get("NETUID", "1")),
        # Challenge parameters
        "grid_resolution_m":     int(
            os.environ.get("GRID_RESOLUTION_M", str(DEFAULT_GRID_RESOLUTION_M))
        ),
        "max_response_timeout_s": float(
            os.environ.get("MAX_RESPONSE_TIMEOUT_S", str(CHALLENGE_MAX_AGE_S))
        ),
        # Canary / synthetic
        "canary_injection_rate":    CANARY_INJECTION_RATE,
        "synthetic_spotcheck_rate": SYNTHETIC_SPOTCHECK_RATE,
        "canary_rotation_hours":    int(os.environ.get("CANARY_ROTATION_HOURS", "24")),
        "synthetic_benchmark_path": os.environ.get("SYNTHETIC_BENCHMARK_PATH", ""),
        # Reproducibility
        "docker_rerun_enabled": (
            os.environ.get("DOCKER_RERUN_ENABLED", "false").lower() == "true"
        ),
    }

    logger.info(
        f"Validator config loaded | netuid={config['netuid']} "
        f"network={config['subtensor_network']} "
        f"timeout={config['max_response_timeout_s']}s "
        f"docker_rerun={config['docker_rerun_enabled']}"
    )
    return config
