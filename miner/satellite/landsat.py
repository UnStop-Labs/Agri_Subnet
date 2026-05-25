"""
miner/satellite/landsat.py
Landsat-8/9 retrieval fallback for cloud-heavy periods.

Phase 2 — not yet implemented.
This module will use the USGS M2M API (https://m2m.cr.usgs.gov/) to search
and download Landsat Collection-2 Level-2 surface reflectance products.

Bands:
  Landsat-8/9  Red = Band 4 (0.64–0.67 µm)
               NIR = Band 5 (0.85–0.88 µm)
               Green = Band 3 (0.53–0.59 µm)
"""
from __future__ import annotations

from typing import Tuple, List

from loguru import logger

from irrigation.utils.geo import BoundingBox


class LandsatClient:
    """
    Retrieves Landsat-8/9 Collection-2 Level-2 surface reflectance products
    from USGS Earth Explorer / M2M API.

    Phase 2 implementation required:
    - Register at https://ers.cr.usgs.gov/ for USGS credentials.
    - Use the M2M JSON API (https://m2m.cr.usgs.gov/api/docs/json/).
    - Authenticate with username + token.
    - Search dataset 'landsat_ot_c2_l2' with spatial/temporal filters.
    - Download the scene bundle and extract the required bands.
    """

    def __init__(self) -> None:
        # Phase 2: read USGS_USER and USGS_TOKEN from environment.
        raise NotImplementedError(
            "LandsatClient is a Phase 2 feature. "
            "Implement USGS M2M API authentication and scene search. "
            "See https://m2m.cr.usgs.gov/api/docs/json/ for the API reference."
        )

    def search_landsat(
        self,
        bbox: BoundingBox,
        query_date: str,
        max_cloud_pct: int = 30,
    ) -> List[dict]:
        """
        Search for Landsat-8/9 scenes covering bbox around query_date.

        Phase 2: query the USGS M2M 'scene-search' endpoint with
        spatialFilter (mbr or geojson) and acquisitionFilter (start/end dates).
        """
        raise NotImplementedError(
            "Phase 2: implement USGS M2M scene-search. "
            "POST to https://m2m.cr.usgs.gov/api/api/json/v1.5/scene-search "
            "with datasetName='landsat_ot_c2_l2' and spatialFilter."
        )

    def download_scene(self, entity_id: str, product_id: str) -> Tuple[bytes, str]:
        """
        Download a Landsat scene bundle and extract bands 3, 4, 5 as GeoTIFF.

        Phase 2: use the M2M 'download-request' + 'download-retrieve' flow,
        then extract individual band files from the downloaded .tar.
        """
        raise NotImplementedError(
            "Phase 2: implement USGS M2M download-request / download-retrieve flow. "
            "Extract Band 3 (Green), Band 4 (Red), Band 5 (NIR) GeoTIFFs from the .tar bundle."
        )

    def fetch_best_scene(
        self, bbox: BoundingBox, query_date: str
    ) -> Tuple[bytes, List[str]]:
        """
        High-level: find the best Landsat scene, download it,
        return (multi_band_geotiff_bytes, [scene_id]).

        Phase 2: called by miner.miner.IrrigationMiner when Sentinel-2
        returns no results (heavy cloud cover periods).
        """
        raise NotImplementedError(
            "Phase 2: wire fetch_best_scene to search_landsat → download_scene. "
            "Return bytes compatible with miner/processing/ndvi.py and ndwi.py "
            "(bands must map: 3=Green, 4=Red, 5=NIR when opened with rasterio)."
        )
