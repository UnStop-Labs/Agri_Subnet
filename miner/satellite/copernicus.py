"""
miner/satellite/copernicus.py
Sentinel-2 L2A imagery retrieval via Copernicus Data Space.
Free tier — no credit card required.
Sign up at: https://dataspace.copernicus.eu
"""
from __future__ import annotations

import os
import requests
from typing import Tuple, List

from loguru import logger

from irrigation.constants import (
    COPERNICUS_TOKEN_URL,
    COPERNICUS_SEARCH_URL,
    COPERNICUS_DOWNLOAD_URL,
    SENTINEL2_MAX_CLOUD_PCT,
    SENTINEL2_FRESHNESS_DAYS,
)
from irrigation.utils.geo import BoundingBox


class CopernicusClient:
    """Handles auth + scene search + GeoTIFF download from Copernicus Data Space."""

    def __init__(self) -> None:
        self._token: str | None = None

    def get_token(self) -> str:
        """Fetch a fresh OAuth2 token. Tokens expire after 10 minutes."""
        resp = requests.post(
            COPERNICUS_TOKEN_URL,
            data={
                "grant_type": "password",
                "username": os.environ["COPERNICUS_USER"],
                "password": os.environ["COPERNICUS_PASS"],
                "client_id": "cdse-public",
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def search_sentinel2(
        self,
        bbox: BoundingBox,
        query_date: str,
        max_cloud_pct: int = SENTINEL2_MAX_CLOUD_PCT,
    ) -> List[dict]:
        """
        Search for Sentinel-2 L2A products covering bbox around query_date.
        Returns list of product metadata dicts, ordered newest-first.
        """
        from datetime import datetime, timedelta, timezone

        try:
            target = datetime.fromisoformat(query_date.replace("Z", "+00:00"))
        except ValueError:
            target = datetime.now(timezone.utc)

        # ±14 days window around query_date
        start = (target - timedelta(days=SENTINEL2_FRESHNESS_DAYS)).strftime(
            "%Y-%m-%dT00:00:00.000Z"
        )
        end = (target + timedelta(days=2)).strftime("%Y-%m-%dT23:59:59.000Z")

        odata_filter = (
            f"Collection/Name eq 'SENTINEL-2' and "
            f"Attributes/OData.CSC.DoubleAttribute/any("
            f"att:att/Name eq 'cloudCover' and "
            f"att/OData.CSC.DoubleAttribute/Value lt {max_cloud_pct}) and "
            f"ContentDate/Start gt {start} and "
            f"ContentDate/Start lt {end} and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;"
            f"{bbox.to_wkt_polygon()}')"
        )

        try:
            resp = requests.get(
                COPERNICUS_SEARCH_URL,
                params={
                    "$filter": odata_filter,
                    "$orderby": "ContentDate/Start desc",
                    "$top": 5,
                    "$expand": "Attributes",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("value", [])
        except requests.RequestException as exc:
            logger.warning(f"Copernicus search failed: {exc}")
            return []

    def download_geotiff(self, product_id: str) -> Tuple[bytes, str]:
        """
        Download a Sentinel-2 product GeoTIFF.
        Returns (raw_bytes, product_name).
        Refreshes token automatically.
        """
        if not self._token:
            self.get_token()

        url = f"{COPERNICUS_DOWNLOAD_URL}({product_id})/$value"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self._token}"},
                stream=True,
                timeout=120,
            )
            if resp.status_code == 401:
                # Token expired — refresh and retry
                logger.info("Copernicus token expired, refreshing")
                self.get_token()
                resp = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    stream=True,
                    timeout=120,
                )
            resp.raise_for_status()
            return b"".join(resp.iter_content(chunk_size=65536)), product_id
        except requests.RequestException as exc:
            raise RuntimeError(f"Copernicus download failed for {product_id}: {exc}") from exc

    def fetch_best_scene(
        self, bbox: BoundingBox, query_date: str
    ) -> Tuple[bytes, List[str]]:
        """
        High-level: find the best Sentinel-2 scene for a field + date,
        download it, return (geotiff_bytes, [scene_id]).

        Raises RuntimeError if no scene is available and Landsat fallback is
        not yet implemented (Phase 2).
        """
        products = self.search_sentinel2(bbox, query_date)
        if not products:
            raise RuntimeError(
                f"No Sentinel-2 scene found for bbox={bbox} date={query_date}. "
                "Consider increasing cloud threshold or widening the date window."
            )

        product = products[0]
        product_id   = product["Id"]
        product_name = product["Name"]
        logger.info(f"Downloading Sentinel-2 scene: {product_name}")

        geotiff_bytes, _ = self.download_geotiff(product_id)
        return geotiff_bytes, [product_name]
