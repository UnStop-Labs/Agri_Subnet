"""
validator/anticheats/plagiarism.py
Cross-miner plagiarism and Sybil detection (§6.5).
Uses cosine similarity on response moisture_index vectors.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
from loguru import logger

from irrigation.constants import PLAGIARISM_COSINE_THRESHOLD
from irrigation.synapse import FieldAnalysisResponse


def extract_moisture_vector(response: FieldAnalysisResponse) -> np.ndarray:
    """Flatten moisture_index values into a 1D vector, ordered by cell_id."""
    features = response.geojson_grid.get("features", [])
    if not features:
        return np.array([])
    sorted_features = sorted(features, key=lambda f: f["properties"]["cell_id"])
    return np.array([f["properties"]["moisture_index"] for f in sorted_features])


def detect_plagiarism(
    uid_responses: Dict[int, FieldAnalysisResponse],
) -> List[Tuple[int, int, float]]:
    """
    Compare all pairs of miner responses.

    Args:
        uid_responses: Mapping from miner UID to their FieldAnalysisResponse.

    Returns:
        List of (uid_a, uid_b, cosine_similarity) tuples for suspicious pairs
        where cosine_similarity > PLAGIARISM_COSINE_THRESHOLD.
    """
    uids    = list(uid_responses.keys())
    vectors = {uid: extract_moisture_vector(r) for uid, r in uid_responses.items()}

    flagged: List[Tuple[int, int, float]] = []
    for i, uid_a in enumerate(uids):
        for uid_b in uids[i + 1:]:
            va, vb = vectors[uid_a], vectors[uid_b]
            if len(va) == 0 or len(vb) == 0 or len(va) != len(vb):
                continue
            sim = _cosine_similarity(va, vb)
            if sim > PLAGIARISM_COSINE_THRESHOLD:
                logger.warning(
                    f"ANTI-CHEAT: plagiarism detected uid={uid_a} uid={uid_b} "
                    f"cosine={sim:.4f}"
                )
                flagged.append((uid_a, uid_b, sim))

    return flagged


def penalise_sybil_cluster(
    flagged_pairs: List[Tuple[int, int, float]],
    scores: Dict[int, float],
) -> Dict[int, float]:
    """
    For each plagiarism cluster, cap combined weight to what one miner would get.
    All cluster members share the single-miner score equally (§6.5).

    Args:
        flagged_pairs: Output of detect_plagiarism().
        scores:        {uid: weight} dict from MinerScorer.compute_weights().

    Returns:
        Updated {uid: weight} dict with Sybil penalties applied.
    """
    if not flagged_pairs:
        return scores

    # Build adjacency list and find connected components
    adjacency: Dict[int, set] = defaultdict(set)
    for uid_a, uid_b, _ in flagged_pairs:
        adjacency[uid_a].add(uid_b)
        adjacency[uid_b].add(uid_a)

    visited: set = set()
    clusters: List[set] = []
    for uid in adjacency:
        if uid not in visited:
            cluster: set = set()
            stack = [uid]
            while stack:
                node = stack.pop()
                if node not in visited:
                    visited.add(node)
                    cluster.add(node)
                    stack.extend(adjacency[node] - visited)
            clusters.append(cluster)

    penalised = dict(scores)
    for cluster in clusters:
        cluster_score = max(scores.get(uid, 0.0) for uid in cluster)
        per_uid = cluster_score / len(cluster)
        for uid in cluster:
            penalised[uid] = per_uid
            logger.warning(
                f"Sybil penalty: uid={uid} score {scores.get(uid, 0.0):.3f} "
                f"→ {per_uid:.3f}"
            )

    return penalised


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
