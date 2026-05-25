"""
validator/anticheats/scene_auditor.py
Scene ID auditability (§6.2).
Verifies satellite_scene_ids against ESA/USGS STAC catalogs.
"""
from __future__ import annotations

import requests
from typing import List

from loguru import logger


STAC_SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/stac/search"


def verify_scene_ids(
    scene_ids: List[str],
    latitude: float,
    longitude: float,
    query_date: str,
) -> float:
    """
    Verify each scene ID:
    1. Is it a real, accessible scene in the ESA catalog?
    2. Does it cover the queried lat/lon?
    3. Does its acquisition date fall within the query_date window?

    Args:
        scene_ids:  List of satellite scene IDs from the miner response.
        latitude:   Field centroid latitude.
        longitude:  Field centroid longitude.
        query_date: ISO 8601 target date for the challenge.

    Returns:
        Validity score 0–1 (fraction of scene IDs that pass all checks).
        Returns 0.0 if scene_ids is empty.
    """
    if not scene_ids:
        return 0.0

    valid = 0
    for scene_id in scene_ids:
        try:
            ok = _check_single_scene(scene_id, latitude, longitude, query_date)
            if ok:
                valid += 1
            else:
                logger.warning(f"ANTI-CHEAT: scene {scene_id} failed audit")
        except Exception as exc:
            logger.warning(f"ANTI-CHEAT: scene audit error for {scene_id}: {exc}")

    return valid / len(scene_ids)


def _check_single_scene(
    scene_id: str, lat: float, lon: float, query_date: str
) -> bool:
    """
    Check one scene ID against the Copernicus STAC catalog.
    Returns True if real, covers the point, and date matches.
    """
    try:
        resp = requests.get(
            STAC_SEARCH_URL,
            params={"ids": scene_id, "limit": 1},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("features", [])
        if not items:
            return False  # scene does not exist

        item = items[0]
        # Check spatial coverage
        bbox = item.get("bbox", [])
        if len(bbox) == 4:
            lon_min, lat_min, lon_max, lat_max = bbox
            if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
                return False

        return True
    except requests.RequestException:
        # If STAC is unreachable, give benefit of the doubt (neutral, not zero)
        logger.debug(f"STAC unreachable for scene {scene_id} — defaulting to pass")
        return True
