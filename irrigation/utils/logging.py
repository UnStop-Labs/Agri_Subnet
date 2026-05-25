"""
irrigation/utils/logging.py
Shared loguru configuration for the irrigation subnet.

Usage:
    from irrigation.utils.logging import setup_logging
    setup_logging(level="INFO")
"""
from __future__ import annotations

import sys
from loguru import logger


def setup_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """
    Configure loguru with a consistent format for all subnet components.

    Args:
        level:     Minimum log level (DEBUG | INFO | WARNING | ERROR | CRITICAL).
        json_logs: Emit structured JSON instead of coloured text (useful for log aggregators).
    """
    logger.remove()  # remove default handler

    if json_logs:
        logger.add(
            sys.stdout,
            level=level,
            serialize=True,  # JSON output
        )
    else:
        logger.add(
            sys.stdout,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    logger.info(f"Logging initialised at level={level}, json={json_logs}")


__all__ = ["setup_logging", "logger"]
