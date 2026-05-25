"""
miner/satellite — satellite data retrieval clients.

Primary export:
    CopernicusClient — Sentinel-2 L2A retrieval via Copernicus Data Space (Phase 1).
    LandsatClient    — Landsat-8/9 fallback via USGS M2M API (Phase 2 stub).
"""
from miner.satellite.copernicus import CopernicusClient

__all__ = ["CopernicusClient"]
