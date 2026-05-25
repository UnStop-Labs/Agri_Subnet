"""
miner/config.py
Miner-specific configuration helpers.

All values are read from environment variables (loaded via python-dotenv).
Import and call get_miner_config() to receive a validated dict.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from loguru import logger

from irrigation.constants import DEFAULT_GRID_RESOLUTION_M, CHALLENGE_MAX_AGE_S


def get_miner_config() -> Dict[str, Any]:
    """
    Build and return the miner configuration from environment variables.

    Raises:
        EnvironmentError: If any mandatory environment variable is missing.
    """
    required = {
        "COPERNICUS_USER": "Copernicus Data Space username (email)",
        "COPERNICUS_PASS": "Copernicus Data Space password",
    }
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        details = "; ".join(f"{k} ({required[k]})" for k in missing)
        raise EnvironmentError(
            f"Missing required environment variables: {details}. "
            "Copy .env.example → .env and fill in your credentials."
        )

    config: Dict[str, Any] = {
        # Wallet
        "wallet_name":    os.environ.get("WALLET_NAME",   "default"),
        "wallet_hotkey":  os.environ.get("WALLET_HOTKEY", "default"),
        # Bittensor network
        "subtensor_network": os.environ.get("SUBTENSOR_NETWORK", "finney"),
        "netuid":            int(os.environ.get("NETUID", "1")),
        # Satellite
        "copernicus_user": os.environ["COPERNICUS_USER"],
        "copernicus_pass": os.environ["COPERNICUS_PASS"],
        # Processing
        "grid_resolution_m": int(
            os.environ.get("GRID_RESOLUTION_M", str(DEFAULT_GRID_RESOLUTION_M))
        ),
        # Reproducibility
        "model_path":       os.environ.get("MODEL_PATH", "model/weights.pt"),
        "model_version":    os.environ.get("MODEL_VERSION", "v1.1.0"),
        "docker_image_ref": os.environ.get(
            "DOCKER_IMAGE_REF", "ghcr.io/yourorg/irrigation-miner:v1.1.0"
        ),
        # Security
        "challenge_max_age_s": CHALLENGE_MAX_AGE_S,
    }

    logger.info(
        f"Miner config loaded | netuid={config['netuid']} "
        f"network={config['subtensor_network']} "
        f"resolution={config['grid_resolution_m']}m"
    )
    return config
