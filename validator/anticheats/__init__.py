"""
validator/anticheats — anti-cheat and Sybil-detection subsystems.

Primary exports:
    check_nonce_timing   — §6.1 pre-computation prevention
    verify_scene_ids     — §6.2 satellite scene auditability
    detect_plagiarism    — §6.5 cross-miner similarity detection
    penalise_sybil_cluster — §6.5 score capping for clone clusters
    rerun_miner_container  — §5.6/§6.4 Docker reproducibility check
"""
from validator.anticheats.nonce_checker import check_nonce_timing
from validator.anticheats.scene_auditor import verify_scene_ids
from validator.anticheats.plagiarism import detect_plagiarism, penalise_sybil_cluster
from validator.anticheats.docker_runner import rerun_miner_container

__all__ = [
    "check_nonce_timing",
    "verify_scene_ids",
    "detect_plagiarism",
    "penalise_sybil_cluster",
    "rerun_miner_container",
]
