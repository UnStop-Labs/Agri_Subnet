<div align="center">

# 🌾 Field Irrigation Intelligence Network
### Bittensor Subnet · Precision Agriculture · Sentinel-2 Satellite Analysis

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Bittensor](https://img.shields.io/badge/bittensor-%E2%89%A56.9.0-orange.svg)](https://bittensor.com)
[![Tests](https://img.shields.io/badge/tests-79%20passed-brightgreen.svg)](#running-tests)

</div>

---

## Overview

The **Field Irrigation Intelligence Network** is a decentralised intelligence subnet on the [Bittensor](https://bittensor.com) network that delivers precision irrigation recommendations for agricultural fields in real time.

**Miners** fetch live Sentinel-2 L2A satellite imagery from the free [Copernicus Data Space](https://dataspace.copernicus.eu), compute NDVI and NDWI spectral indices, and return georeferenced GeoJSON moisture maps at 10–60 m grid resolution — signed with their Bittensor hotkey for cryptographic accountability.

**Validators** issue challenge requests with random nonces (preventing pre-computation), verify responses through a five-dimensional scoring framework, run four anti-cheat subsystems, and set on-chain weights proportional to spatial accuracy, spectral validity, data freshness, reproducibility, and response latency.

The subnet is purpose-built for smallholder farms in Thailand and Southeast Asia (field sizes measured in Rai), with canary fields at permanent water bodies, arid zones, dense forest, and urban surfaces providing a continuous, ground-truth-anchored quality signal.

---

## Table of Contents

- [Architecture](#architecture)
- [Protocol Flow](#protocol-flow)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Scoring System](#scoring-system)
- [Anti-Cheat Mechanisms](#anti-cheat-mechanisms)
- [Moisture Classification](#moisture-classification)
- [GeoJSON Output Format](#geojson-output-format)
- [Running Tests](#running-tests)
- [Docker](#docker)
- [Project Structure](#project-structure)
- [Phase 2 Gaps](#phase-2-gaps)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BITTENSOR NETWORK                        │
│                                                                 │
│  ┌─────────────────────┐          ┌──────────────────────────┐  │
│  │      VALIDATOR       │          │         MINER            │  │
│  │                     │          │                          │  │
│  │  ChallengeIssuer    │◄────────►│  IrrigationMiner         │  │
│  │  ├─ nonce (256-bit) │          │  ├─ validate challenge   │  │
│  │  ├─ canary inject   │          │  ├─ fetch Sentinel-2     │  │
│  │  └─ broadcast       │          │  ├─ compute NDVI/NDWI    │  │
│  │                     │          │  ├─ build GeoJSON grid   │  │
│  │  MinerScorer        │          │  └─ sign response        │  │
│  │  ├─ spatial  35%    │          │                          │  │
│  │  ├─ spectral 20%    │          │  CopernicusClient        │  │
│  │  ├─ temporal 20%    │          │  ├─ OAuth2 token         │  │
│  │  ├─ repro    15%    │          │  ├─ OData scene search   │  │
│  │  └─ latency  10%    │          │  └─ GeoTIFF download     │  │
│  │                     │          │                          │  │
│  │  Anti-Cheat Suite   │          │  Spectral Processing     │  │
│  │  ├─ nonce timing    │          │  ├─ NDVI (B04/B08)       │  │
│  │  ├─ scene audit     │          │  ├─ NDWI (B03/B08)       │  │
│  │  ├─ plagiarism      │          │  └─ moisture grid        │  │
│  │  └─ Docker rerun    │          │                          │  │
│  └─────────────────────┘          └──────────────────────────┘  │
│                │                                                │
│                └──── subtensor.set_weights() ───────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

| Component | File | Role |
|-----------|------|------|
| Challenge synapse | [`irrigation/synapse.py`](irrigation/synapse.py) | `FieldAnalysisChallenge` — validator→miner request with nonce |
| Response synapse | [`irrigation/synapse.py`](irrigation/synapse.py) | `FieldAnalysisResponse` — miner→validator GeoJSON + audit trail |
| Constants | [`irrigation/constants.py`](irrigation/constants.py) | All scoring weights, thresholds, and magic numbers |
| Geo utilities | [`irrigation/utils/geo.py`](irrigation/utils/geo.py) | BBox, grid cells, moisture classification |
| Copernicus client | [`miner/satellite/copernicus.py`](miner/satellite/copernicus.py) | OAuth2, OData search, streaming GeoTIFF download |
| NDVI/NDWI | [`miner/processing/`](miner/processing/) | Band extraction + moisture index computation |
| Grid builder | [`miner/processing/grid_builder.py`](miner/processing/grid_builder.py) | Assemble the per-cell GeoJSON FeatureCollection |
| Miner neuron | [`miner/miner.py`](miner/miner.py) | Full 5-step pipeline |
| Challenge issuer | [`validator/challenge.py`](validator/challenge.py) | Nonce generation, canary injection, broadcast |
| Scorer | [`validator/scorer.py`](validator/scorer.py) | 5-dimension scoring + EMA + weight normalisation |
| Anti-cheat | [`validator/anticheats/`](validator/anticheats/) | Nonce timing, scene audit, plagiarism, Docker rerun |
| Benchmarks | [`validator/benchmarks/`](validator/benchmarks/) | Canary fields + synthetic ground truth |
| Validator neuron | [`validator/validator.py`](validator/validator.py) | Tempo loop: issue → collect → check → score → set_weights |

---

## Protocol Flow

```
Validator                                      Miner
    │                                            │
    │  1. Create challenge                        │
    │     challenge_id = uuid4()                 │
    │     nonce        = secrets.token_hex(32)   │
    │     timestamp    = now()                   │
    │     [12% chance: inject canary field]      │
    │                                            │
    │──── FieldAnalysisChallenge ───────────────►│
    │     lat, lon, area_rai, query_date         │
    │     nonce, timestamp_utc                   │
    │                                            │
    │                    2. Validate challenge   │
    │                       age ≤ 90 s           │
    │                       nonce ≥ 32 bytes     │
    │                                            │
    │                    3. Fetch Sentinel-2     │
    │                       Copernicus OData API │
    │                       ±14-day window       │
    │                       cloud < 20%          │
    │                                            │
    │                    4. Compute NDVI/NDWI    │
    │                       B04/B08 / B03/B08    │
    │                                            │
    │                    5. Build GeoJSON grid   │
    │                       n×n cells @ res_m    │
    │                       moisture_class       │
    │                       confidence per cell  │
    │                                            │
    │                    6. Sign response        │
    │                       sign(id+nonce+hash)  │
    │                                            │
    │◄─── FieldAnalysisResponse ────────────────│
    │     geojson_grid, scene_ids               │
    │     model_hash, docker_image_ref          │
    │     signature                             │
    │                                            │
    │  7. Anti-cheat pass                        │
    │     nonce_timing, scene_audit             │
    │     plagiarism, [docker_rerun]            │
    │                                            │
    │  8. Score (5 dimensions)                  │
    │     EMA update                            │
    │                                            │
    │  9. set_weights() on-chain                │
```

---

## Quick Start

### Prerequisites

- Python ≥ 3.10
- A registered [Bittensor wallet](https://docs.bittensor.com/getting-started/wallets)
- Free [Copernicus Data Space](https://dataspace.copernicus.eu) account
- Docker (optional — for reproducibility verification)

### Installation

```bash
# Clone the repository
git clone https://github.com/UnStop-Labs/Agri_Subnet.git
cd Agri_Subnet

# Install (editable, includes dev dependencies)
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
nano .env   # fill in your credentials
```

### Run a Miner

```bash
# Ensure .env is filled in, then:
python neurons/miner.py

# Or with explicit flags (override .env):
python neurons/miner.py \
  --wallet.name my_wallet \
  --wallet.hotkey my_hotkey \
  --subtensor.network finney \
  --netuid 1
```

### Run a Validator

```bash
python neurons/validator.py
```

### Docker (recommended for production)

```bash
cd docker
docker-compose up --build
```

---

## Environment Variables

Copy [`.env.example`](.env.example) → `.env` and fill in the values below.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `WALLET_NAME` | `str` | `default` | Bittensor wallet name |
| `WALLET_HOTKEY` | `str` | `default` | Wallet hotkey name |
| `SUBTENSOR_NETWORK` | `str` | `finney` | `finney` \| `test` \| `local` |
| `NETUID` | `int` | `1` | Subnet UID on the Bittensor network |
| `COPERNICUS_USER` | `str` | *(required)* | Copernicus Data Space email — [register free](https://dataspace.copernicus.eu) |
| `COPERNICUS_PASS` | `str` | *(required)* | Copernicus Data Space password |
| `MODEL_PATH` | `path` | `model/weights.pt` | Path to miner model weights file |
| `MODEL_VERSION` | `str` | `v1.1.0` | Model version tag (embedded in responses) |
| `DOCKER_IMAGE_REF` | `str` | `ghcr.io/yourorg/irrigation-miner:v1.1.0` | Docker image reference for reproducibility verification |
| `GRID_RESOLUTION_M` | `int` | `20` | Output grid cell size in metres: `10`\|`20`\|`30`\|`60` |
| `SYNTHETIC_BENCHMARK_PATH` | `path` | *(optional)* | JSON file with synthetic benchmark dataset |
| `CANARY_ROTATION_HOURS` | `int` | `24` | How often canary field definitions rotate |
| `MAX_RESPONSE_TIMEOUT_S` | `float` | `90` | Seconds to wait for miner responses per challenge |
| `DOCKER_RERUN_ENABLED` | `bool` | `true` | Enable Docker container reproducibility re-runs |
| `LOG_LEVEL` | `str` | `INFO` | Loguru log level: `DEBUG`\|`INFO`\|`WARNING`\|`ERROR` |

---

## Scoring System

Each miner response is scored across **five independent dimensions** and aggregated with an Exponential Moving Average (EMA).

### Dimension Breakdown

| # | Dimension | Weight | Method |
|---|-----------|--------|--------|
| 1 | **Spatial** | **35%** | Moisture class accuracy vs. canary/synthetic ground truth *or* cross-miner consensus when no ground truth is available |
| 2 | **Spectral** | **20%** | Physics-bound NDVI ∈ [-1,1] and NDWI ∈ [-1,1] range validation; cloud fraction penalty above 30% |
| 3 | **Temporal** | **20%** | Scene acquisition date vs. challenge `query_date`; full score ≤14 days, linear decay to 60% at 30 days, zero beyond |
| 4 | **Reproducibility** | **15%** | Docker container re-run output match (50%) + determinism (30%) + environment artifact validity (20%) |
| 5 | **Latency** | **10%** | Response time: <2 s → 0.0 (flagged), 2–8 s → 1.0, 8–30 s → 0.7, 30–90 s → 0.4, >90 s → 0.0 |

### EMA Aggregation

```
EMA_t = α × score_t + (1 − α) × EMA_{t-1}
α = 0.3,  window = 20 epochs
```

Miners below the **quality floor** (0.10) receive zero on-chain weight regardless of their EMA.

### Weight Normalisation

```
weight_i = final_score_i / Σ final_score_j
```

Weights are corrected to sum to **exactly 1.000000** before `subtensor.set_weights()`.

---

## Anti-Cheat Mechanisms

### 1. Nonce Timing (§6.1)

Every challenge embeds a fresh 256-bit random nonce unknown until broadcast. Responses arriving in less than **2 seconds** cannot have made a live Copernicus API call — they are flagged for spectral and reproducibility auditing and receive a **latency score of 0.0**.

### 2. Scene ID Auditability (§6.2)

Miners must report the exact Sentinel-2 scene IDs used. Validators query the Copernicus STAC catalog to verify:
- The scene actually exists in the ESA archive
- Its bounding box covers the challenged lat/lon
- Its acquisition date falls within the query window

Scenes failing verification reduce the temporal score proportionally.

### 3. Canary Fields (§6.3)

**12% of challenges** are silently replaced with permanent landmark fields whose expected moisture class is deterministic:

| Canary | Location | Expected Class |
|--------|----------|---------------|
| Bhumibol Reservoir | 17.2456°N 99.0234°E | `WET` |
| Mae Wong arid scrubland | 15.8012°N 99.6543°E | `CRITICAL_DRY` |
| Doi Inthanon dense forest | 18.5893°N 98.4862°E | `OPTIMAL` |
| Bangkok urban impervious | 13.7563°N 100.5018°E | `CRITICAL_DRY` |

Miners that return incorrect classes on canary challenges are penalised in the spatial dimension.

### 4. Plagiarism & Sybil Detection (§6.5)

After collecting all responses for a challenge, validators compute pairwise **cosine similarity** on the flattened `moisture_index` vectors. Pairs exceeding the threshold (0.99) are flagged as a Sybil cluster. The entire cluster's combined weight is **capped to what a single honest miner would receive**, shared equally among members.

```
flagged if: cos(moisture_vec_A, moisture_vec_B) > 0.99
penalty:    each cluster member's weight = max_cluster_score / cluster_size
```

### 5. Docker Reproducibility Verification (§5.6 / §6.4)

Validators pull the miner's declared Docker image, re-run it with the original challenge inputs, and compare the output `moisture_index` values cell by cell (tolerance ±0.05). A match score of 1.0 (all cells within tolerance) yields full reproducibility credit. Determinism is inferred from the match score.

---

## Moisture Classification

All output cells carry a `moisture_class` derived from the 0–1 `moisture_index`:

| Class | Moisture Index Range | Agronomic Meaning |
|-------|---------------------|-------------------|
| `CRITICAL_DRY` | 0.00 – 0.20 | Severe water deficit — **irrigate immediately** |
| `DRY` | 0.21 – 0.40 | Below optimal — irrigation recommended |
| `OPTIMAL` | 0.41 – 0.70 | Good soil moisture balance |
| `WET` | 0.71 – 1.00 | Saturated or flooded — no irrigation needed |

The moisture index is a weighted blend:
```
moisture_index = 0.6 × ndvi_moisture + 0.4 × ndwi_moisture
ndvi_moisture  = 1 − (NDVI + 1) / 2     # low NDVI → high need
ndwi_moisture  = 1 − (NDWI + 1) / 2     # low NDWI → high need
```

---

## GeoJSON Output Format

Each miner response contains a `geojson_grid` — a standard **GeoJSON FeatureCollection** where every Feature represents one grid cell:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[100.130, 14.470], [100.131, 14.470],
                          [100.131, 14.471], [100.130, 14.471],
                          [100.130, 14.470]]]
      },
      "properties": {
        "cell_id":               0,
        "moisture_class":        "OPTIMAL",
        "moisture_index":        0.5231,
        "ndvi":                  0.4120,
        "ndwi":                  0.1850,
        "evapotranspiration_mm": 4.2,
        "cloud_masked":          false,
        "data_source":           "Sentinel-2 L2A",
        "cell_confidence":       0.873
      }
    }
  ]
}
```

| Property | Type | Description |
|----------|------|-------------|
| `cell_id` | `int` | Row-major cell index (unique within response) |
| `moisture_class` | `str` | `CRITICAL_DRY` \| `DRY` \| `OPTIMAL` \| `WET` |
| `moisture_index` | `float [0,1]` | Continuous soil moisture proxy |
| `ndvi` | `float [-1,1]` | Normalized Difference Vegetation Index |
| `ndwi` | `float [-1,1]` | Normalized Difference Water Index |
| `evapotranspiration_mm` | `float` | Estimated ET (mm/day); ERA5 in Phase 2 |
| `cloud_masked` | `bool` | True if this cell was obscured by cloud |
| `data_source` | `str` | Satellite product identifier |
| `cell_confidence` | `float [0,1]` | Agreement between NDVI and NDWI signals |

---

## Running Tests

The full test suite runs **without a Bittensor wallet or network connection** — bittensor is mocked via [`tests/conftest.py`](tests/conftest.py).

```bash
# Run all 79 tests
pytest tests/ -v

# Run a specific module
pytest tests/test_scorer.py -v

# Run a single test
pytest tests/test_anticheats.py::TestPlagiarismDetection::test_identical_responses_flagged -v
```

### Test Coverage

| Module | Tests | Covers |
|--------|-------|--------|
| [`test_synapse.py`](tests/test_synapse.py) | 11 | Pydantic validators, serialisation, field access |
| [`test_scorer.py`](tests/test_scorer.py) | 21 | All 5 scoring dimensions, EMA, quality floor, weight normalisation |
| [`test_grid_builder.py`](tests/test_grid_builder.py) | 16 | Bbox maths, grid cell generation, moisture classification |
| [`test_anticheats.py`](tests/test_anticheats.py) | 18 | Nonce timing, plagiarism, Sybil penalty, cosine similarity, grid comparison |

---

## Docker

### Build & Run Both

```bash
cd docker
docker-compose up --build
```

### Miner Only

```bash
docker-compose up --build miner
```

### Validator Only

```bash
docker-compose up --build validator
```

The **validator container** mounts `/var/run/docker.sock` so it can pull and re-run miner Docker images for reproducibility verification.

The **miner container** expects model weights at `/app/model/weights.pt` (mount a volume or bake them into a custom image).

---

## Project Structure

```
Agri_Subnet/
├── README.md                          # This file
├── pyproject.toml                     # Build system + dependencies
├── setup.py                           # pip install -e . support
├── .env.example                       # Environment variable template
├── .gitignore
│
├── irrigation/                        # Core shared package
│   ├── __init__.py
│   ├── synapse.py                     # FieldAnalysisChallenge + FieldAnalysisResponse
│   ├── protocol.py                    # Protocol version constants
│   ├── constants.py                   # All magic numbers (weights, thresholds)
│   └── utils/
│       ├── geo.py                     # BoundingBox, grid builder, classify_moisture
│       ├── signing.py                 # Nonce, SHA-256, sign/verify
│       └── logging.py                 # Loguru setup
│
├── miner/                             # Miner neuron
│   ├── miner.py                       # IrrigationMiner — main 5-step pipeline
│   ├── config.py                      # Environment-driven config
│   ├── satellite/
│   │   ├── copernicus.py              # Sentinel-2 retrieval (Copernicus Data Space)
│   │   └── landsat.py                 # Landsat-8/9 fallback — Phase 2 stub
│   └── processing/
│       ├── ndvi.py                    # NDVI computation (B04/B08)
│       ├── ndwi.py                    # NDWI computation (B03/B08)
│       └── grid_builder.py            # GeoJSON FeatureCollection assembly
│
├── validator/                         # Validator neuron
│   ├── validator.py                   # IrrigationValidator — tempo loop
│   ├── challenge.py                   # ChallengeIssuer (nonce + canary injection)
│   ├── scorer.py                      # MinerScorer — 5 dimensions + EMA
│   ├── config.py                      # Environment-driven config
│   ├── anticheats/
│   │   ├── nonce_checker.py           # §6.1 timing check
│   │   ├── scene_auditor.py           # §6.2 STAC catalog verification
│   │   ├── plagiarism.py              # §6.5 cosine similarity + Sybil penalty
│   │   └── docker_runner.py           # §5.6/§6.4 container reproducibility
│   └── benchmarks/
│       ├── canary_fields.py           # 4 permanent landmark canary fields
│       └── synthetic.py               # Synthetic benchmark loader
│
├── neurons/                           # Entry points
│   ├── miner.py                       # python neurons/miner.py
│   └── validator.py                   # python neurons/validator.py
│
├── docker/
│   ├── Dockerfile.miner
│   ├── Dockerfile.validator
│   └── docker-compose.yml
│
└── tests/
    ├── conftest.py                    # Bittensor mock (no wallet needed)
    ├── test_synapse.py
    ├── test_scorer.py
    ├── test_grid_builder.py
    ├── test_anticheats.py
    └── fixtures/
        ├── sample_challenge.json
        └── sample_response.json
```

---

## Phase 2 Gaps

The following features are intentionally stubbed for Phase 2. Each stub raises `NotImplementedError` with detailed implementation instructions.

| Gap | Location | What's Needed |
|-----|----------|---------------|
| **ERA5 evapotranspiration** | `miner/processing/grid_builder.py` | ERA5 CDSAPI integration for Penman-Monteith ET per cell |
| **On-chain hotkey verification** | `miner/miner.py::_validate_challenge` | Verify `validator_hotkey` against subnet metagraph before processing |
| **Phase 1 qualification gate** | `validator/validator.py::_filter_to_qualified_miners` | State machine: UNQUALIFIED → QUALIFYING → QUALIFIED → BANNED |
| **Landsat-8/9 fallback** | `miner/satellite/landsat.py` | USGS M2M API for cloud-heavy periods |
| **Farm job queue** | `validator/validator.py::_get_next_farm_location` | Replace hardcoded lat/lon with a real API or database queue |
| **Confidence calibration (ECE)** | `validator/scorer.py::track_calibration_error` | Expected Calibration Error bucketing and per-miner penalty |
| **Async Docker re-run** | `validator/anticheats/docker_runner.py::_async_rerun_worker` | Non-blocking reproducibility check via asyncio + ThreadPoolExecutor |

---

## Roadmap

| Phase | Milestone | Status |
|-------|-----------|--------|
| **Phase 1** | Sentinel-2 NDVI/NDWI grid · 5-dimension scoring · 4 anti-cheat mechanisms · 79 unit tests | ✅ **Complete** |
| **Phase 2** | ERA5 ET · on-chain hotkey verification · Landsat fallback | 🔄 Stubbed |
| **Phase 3** | Farm job queue API · per-farm history and personalised recommendations | 📋 Planned |
| **Phase 4** | Phase 1 qualification gate · confidence calibration (ECE) | 📋 Planned |
| **Phase 5** | Async Docker reproducibility re-runs · non-blocking tempo | 📋 Planned |
| **Phase 6** | Multi-season historical analysis · crop-type-specific NDVI thresholds | 📋 Planned |
| **Phase 7** | Mobile farmer interface · SMS/LINE irrigation alerts | 📋 Planned |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Run tests before committing: `pytest tests/ -v`
5. Submit a pull request with a clear description

Please keep **all magic numbers in [`irrigation/constants.py`](irrigation/constants.py)**, use **absolute imports**, and write **loguru** log statements (no `print()`).

---

## License

MIT © 2024 [UnStop Labs](https://github.com/UnStop-Labs)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software.
