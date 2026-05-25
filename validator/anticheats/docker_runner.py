"""
validator/anticheats/docker_runner.py
Model reproducibility verification (§5.6, §6.4).
Re-runs the miner's submitted Docker container and compares outputs.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional, Tuple

from loguru import logger


def rerun_miner_container(
    docker_image_ref: str,
    challenge_dict: dict,
    declared_geojson: dict,
    timeout_s: int = 300,
) -> Tuple[float, bool]:
    """
    Pull and run the miner's Docker container with the original challenge inputs.
    Compare the output to the declared geojson_grid.

    Args:
        docker_image_ref: Docker image ref from the miner response.
        challenge_dict:   Serialised FieldAnalysisChallenge as a plain dict.
        declared_geojson: The geojson_grid the miner declared in its response.
        timeout_s:        Container execution timeout in seconds.

    Returns:
        (match_score, determinism_passed) where:
          match_score  — fraction of cells matching within 0.05 tolerance (0–1).
          determinism  — True if match_score > 0.95.

    Notes:
        Requires DOCKER_RERUN_ENABLED=true in environment and a running Docker daemon.

    Phase 2 — Async:
        This function currently blocks the validator tempo. Phase 2 must run it
        asynchronously (e.g. via asyncio or a worker thread) after on-chain weights
        have already been set, then update the miner's reproducibility score in the
        next tempo's EMA calculation.
        See: validator/anticheats/docker_runner.py _async_rerun_worker (Phase 2 stub).
    """
    if os.environ.get("DOCKER_RERUN_ENABLED", "false").lower() != "true":
        logger.info("Docker re-run disabled (DOCKER_RERUN_ENABLED != true) — neutral score")
        return 0.5, True

    try:
        import docker
        client = docker.from_env()
    except Exception as exc:
        logger.error(f"Docker client unavailable: {exc}")
        return 0.5, True

    with tempfile.TemporaryDirectory() as tmpdir:
        challenge_path = os.path.join(tmpdir, "challenge.json")
        output_path    = os.path.join(tmpdir, "output.json")

        with open(challenge_path, "w") as f:
            json.dump(challenge_dict, f)

        try:
            logger.info(f"Pulling Docker image: {docker_image_ref}")
            client.images.pull(docker_image_ref)

            logger.info("Running miner container for reproducibility check")
            client.containers.run(
                docker_image_ref,
                command="--challenge /data/challenge.json --output /data/output.json",
                volumes={tmpdir: {"bind": "/data", "mode": "rw"}},
                remove=True,
                timeout=timeout_s,
            )

            if not os.path.exists(output_path):
                logger.warning("Container produced no output file")
                return 0.0, False

            with open(output_path) as f:
                rerun_output = json.load(f)

            match = _compare_grids(declared_geojson, rerun_output)
            logger.info(f"Reproducibility match score: {match:.3f}")
            return match, match > 0.95

        except Exception as exc:
            logger.error(f"Docker re-run failed: {exc}")
            return 0.0, False


async def _async_rerun_worker(
    docker_image_ref: str,
    challenge_dict: dict,
    declared_geojson: dict,
    uid: int,
    scorer,
    timeout_s: int = 300,
) -> None:
    """
    Phase 2 — Async Docker re-run worker.

    Run this as an asyncio task after on-chain weights are set so reproducibility
    checks don't block the tempo. On completion, call scorer.update_reproducibility()
    (Phase 2 method) to apply the match score to the miner's next EMA cycle.

    Implementation required:
    - Move Docker execution to a ThreadPoolExecutor (docker-py is synchronous).
    - Emit the result via scorer.update_reproducibility(uid, match_score).
    - Handle cancellation gracefully on validator shutdown.
    """
    raise NotImplementedError(
        "Phase 2: implement async Docker re-run. "
        "Use asyncio.get_event_loop().run_in_executor(None, rerun_miner_container, ...) "
        "inside a background asyncio.Task started after set_weights() returns. "
        "Call scorer.update_reproducibility(uid, match_score) with the result."
    )


def _compare_grids(declared: dict, rerun: dict) -> float:
    """
    Compare two GeoJSON grids cell-by-cell on moisture_index.
    Returns fraction of cells matching within 0.05 tolerance.
    """
    declared_map = {
        f["properties"]["cell_id"]: f["properties"]["moisture_index"]
        for f in declared.get("features", [])
    }
    rerun_map = {
        f["properties"]["cell_id"]: f["properties"]["moisture_index"]
        for f in rerun.get("features", [])
    }
    if not declared_map or not rerun_map:
        return 0.0

    common_cells = set(declared_map) & set(rerun_map)
    if not common_cells:
        return 0.0

    matching = sum(
        1 for cid in common_cells
        if abs(declared_map[cid] - rerun_map[cid]) <= 0.05
    )
    return matching / len(common_cells)
