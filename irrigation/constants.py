"""
irrigation/constants.py — All magic numbers in one place.
"""

# Scoring weights (must sum to 1.0) — spec §5.1
SCORE_WEIGHTS = {
    "spatial":         0.35,
    "spectral":        0.20,
    "temporal":        0.20,
    "reproducibility": 0.15,
    "latency":         0.10,
}

# EMA aggregation — spec §5.2
EMA_ALPHA  = 0.3
EMA_WINDOW = 20   # epochs

# Quality floor — spec §7.1
QUALITY_FLOOR = 0.10

# Latency scoring thresholds (seconds) — spec §5.7
LATENCY_TOO_FAST_S     = 2.0
LATENCY_IDEAL_MAX_S    = 8.0
LATENCY_OK_MAX_S       = 30.0
LATENCY_MARGINAL_MAX_S = 90.0
LATENCY_SCORES = {
    "too_fast":  0.0,   # < 2s   — flagged anti-cheat
    "ideal":     1.0,   # 2–8s   — live satellite call
    "ok":        0.7,   # 8–30s  — slower pipeline
    "marginal":  0.4,   # 30–90s — near timeout
    "timeout":   0.0,   # > 90s  — rejected
}

# Temporal freshness — spec §5.5
SCENE_FRESHNESS_DAYS      = 14
SCENE_STALE_PENALTY_DAYS  = 30

# Spectral validity — spec §5.4
NDVI_RANGE = (-1.0, 1.0)
NDWI_RANGE = (-1.0, 1.0)
MAX_CLOUD_FRACTION_NO_PENALTY = 0.30

# Challenge security — spec §4.1
CHALLENGE_MAX_AGE_S = 90
NONCE_BITS = 256

# Moisture classification thresholds — spec Appendix 10.1
MOISTURE_THRESHOLDS = [
    (0.20, "CRITICAL_DRY"),
    (0.40, "DRY"),
    (0.70, "OPTIMAL"),
    (1.01, "WET"),
]

# Plagiarism detection — spec §6.5
PLAGIARISM_COSINE_THRESHOLD = 0.99

# Canary field injection rate — spec §6.3
CANARY_INJECTION_RATE = 0.12   # 12% of challenges are canary

# Synthetic benchmark spot-check rate — spec §5.3.2
SYNTHETIC_SPOTCHECK_RATE = 0.10   # 10% of challenge batch

# Satellite data
SENTINEL2_MAX_CLOUD_PCT  = 20
SENTINEL2_FRESHNESS_DAYS = 14
LANDSAT_MAX_CLOUD_PCT    = 30

# Grid
DEFAULT_GRID_RESOLUTION_M = 20
AREA_RAI_TO_M2            = 1600.0

# Copernicus API
COPERNICUS_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE"
    "/protocol/openid-connect/token"
)
COPERNICUS_SEARCH_URL = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
)
COPERNICUS_DOWNLOAD_URL = (
    "https://download.dataspace.copernicus.eu/odata/v1/Products"
)
