"""
Validator main entry point.

Spawns three long-running processes/tasks:
  1. challenge_proc  – sends field challenges to miners (multiprocessing.Process)
  2. evaluation_proc – evaluates miner responses and stores scores
  3. weights_task    – periodically sets on-chain weights (asyncio task)
"""

import asyncio
import ipaddress
import os
import sys
from multiprocessing import Process

import httpx
from dotenv import load_dotenv
from fiber.chain import fetch_nodes
from fiber.chain.chain_utils import load_coldkeypub_keypair, load_hotkey_keypair
from fiber.chain.interface import get_substrate
from fiber.chain.models import Node
from loguru import logger

# ---------------------------------------------------------------------------
# Patch fiber's fetch_nodes to handle fresh subnets with empty trust arrays.
#
# On a brand new subnet, metagraph["trust"] is an empty tuple ().
# fiber crashes with IndexError when it tries to read trust[uid].
# We replace fiber's function with a safe version that falls back to the
# runtime API and uses 0.0 for any missing values.
# ---------------------------------------------------------------------------
_original_get_nodes = fetch_nodes.get_nodes_for_netuid


def _decode_account_id(raw) -> str:
    """Convert a raw AccountId (bytes tuple from runtime API) to SS58 address."""
    if isinstance(raw, str) and len(raw) > 10:
        return raw
    try:
        inner = raw
        if isinstance(inner, (list, tuple)) and len(inner) == 1 and isinstance(inner[0], (list, tuple)):
            inner = inner[0]
        if isinstance(inner, (list, tuple)):
            from substrateinterface.utils.ss58 import ss58_encode
            return ss58_encode(bytes(inner), ss58_format=42)
    except Exception:
        pass
    return str(raw)


def _safe_get_nodes_for_netuid(substrate, netuid, block=None):
    try:
        return _original_get_nodes(substrate=substrate, netuid=netuid, block=block)
    except Exception as first_exc:
        logger.warning(f"fiber get_nodes failed ({first_exc}) — trying runtime API fallback")

        for api_fn in ["get_neurons_lite", "get_neurons"]:
            try:
                result = substrate.runtime_call("NeuronInfoRuntimeApi", api_fn, [netuid])
                neurons = (result.value or []) if result else []
                if not neurons:
                    continue

                nodes = []
                for neuron in neurons:
                    if not isinstance(neuron, dict):
                        continue
                    axon = neuron.get("axon_info") or {}
                    total_stake = float(neuron.get("total_stake", 0))

                    raw_ip = axon.get("ip", 0)
                    try:
                        ip_str = str(ipaddress.ip_address(int(raw_ip)))
                    except Exception:
                        ip_str = "0.0.0.1"

                    nodes.append(Node(
                        node_id=int(neuron.get("uid", 0)),
                        netuid=netuid,
                        hotkey=_decode_account_id(neuron.get("hotkey", "")),
                        coldkey=_decode_account_id(neuron.get("coldkey", "")),
                        stake=total_stake / 1e9,
                        alpha_stake=total_stake / 1e9,
                        tao_stake=0.0,
                        trust=float(neuron.get("trust", 0)) / 65535.0,
                        consensus=float(neuron.get("consensus", 0)) / 65535.0,
                        incentive=float(neuron.get("incentive", 0)) / 65535.0,
                        dividends=float(neuron.get("dividends", 0)) / 65535.0,
                        emission=float(neuron.get("emission", 0)),
                        vtrust=float(neuron.get("validator_trust", 0)) / 65535.0,
                        rank=float(neuron.get("rank", 0)) / 65535.0,
                        last_updated=int(neuron.get("last_update", 0)),
                        ip=ip_str,
                        port=int(axon.get("port", 0)),
                        ip_type=int(axon.get("ip_type", 4)),
                        protocol=int(axon.get("version", 0)),
                    ))

                logger.info(f"Runtime API fallback ({api_fn}) returned {len(nodes)} nodes")
                return nodes
            except Exception as api_exc:
                logger.debug(f"Runtime API {api_fn} failed: {api_exc}")
                continue

        logger.error("All node fetch methods failed, returning empty list")
        return []


# Swap fiber's function with our safe version
fetch_nodes.get_nodes_for_netuid = _safe_get_nodes_for_netuid

from validator.challenge.challenge_process import start_challenge_sender
from validator.config import (
    DB_PATH,
    HOTKEY_NAME,
    MAX_MINERS,
    NETUID,
    SUBTENSOR_ADDRESS,
    SUBTENSOR_NETWORK,
    WALLET_NAME,
    WEIGHTS_INTERVAL,
)
from validator.db.operations import DatabaseManager
from validator.db.schema import init_db
from validator.evaluation.evaluation_process import start_evaluation
from validator.evaluation.set_weights import set_weights


# ---------------------------------------------------------------------------
# Node helpers (used by challenge_process via import)
# ---------------------------------------------------------------------------

def get_active_nodes() -> list:
    try:
        substrate = get_substrate(
            subtensor_network=SUBTENSOR_NETWORK,
            subtensor_address=SUBTENSOR_ADDRESS,
        )
        nodes = fetch_nodes.get_nodes_for_netuid(substrate, NETUID)
        MAX_STAKE = 999
        active = [n for n in nodes if n.stake < MAX_STAKE]
        logger.info(f"Active nodes: {len(active)}/{len(nodes)}")
        return active
    except Exception as exc:
        logger.error(f"get_active_nodes failed: {exc}")
        return []


def construct_server_address(node: Node) -> str:
    if node.ip == "0.0.0.1":
        return f"http://127.0.0.1:{node.port}"
    return f"http://{node.ip}:{node.port}"


# ---------------------------------------------------------------------------
# Weight-setting loop
# ---------------------------------------------------------------------------

async def weights_update_loop(db_manager: DatabaseManager) -> None:
    logger.info("Weight update loop starting")
    failures = 0
    while True:
        try:
            await set_weights(db_manager)
            failures = 0
            await asyncio.sleep(WEIGHTS_INTERVAL.total_seconds())
        except Exception as exc:
            failures += 1
            logger.error(f"Weight update error #{failures}: {exc}")
            wait = WEIGHTS_INTERVAL.total_seconds() * (2 if failures >= 3 else 1)
            await asyncio.sleep(wait)
            if failures >= 3:
                failures = 0


# ---------------------------------------------------------------------------
# Periodic cleanup
# ---------------------------------------------------------------------------

async def periodic_cleanup(db_manager: DatabaseManager, interval_hours: int = 24) -> None:
    while True:
        try:
            db_manager.cleanup_old_data(days=7)
            logger.info("Database cleanup done")
        except Exception as exc:
            logger.error(f"Cleanup error: {exc}")
        await asyncio.sleep(interval_hours * 3600)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    load_dotenv()

    hotkey = load_hotkey_keypair(WALLET_NAME, HOTKEY_NAME)
    logger.info(f"Validator hotkey: {hotkey.ss58_address}")

    init_db(str(DB_PATH))
    db_manager = DatabaseManager(DB_PATH)

    # Pass env vars to sub-processes
    os.environ["DB_PATH"] = str(DB_PATH)
    os.environ["VALIDATOR_HOTKEY"] = hotkey.ss58_address

    evaluation_proc = Process(target=start_evaluation)
    evaluation_proc.start()
    logger.info(f"Evaluation subprocess PID {evaluation_proc.pid}")

    challenge_proc = Process(target=start_challenge_sender)
    challenge_proc.start()
    logger.info(f"Challenge subprocess PID {challenge_proc.pid}")

    weights_task = asyncio.create_task(weights_update_loop(db_manager))
    cleanup_task = asyncio.create_task(periodic_cleanup(db_manager))

    try:
        iteration = 0
        while True:
            iteration += 1
            logger.debug(f"Main loop iteration {iteration}")

            if weights_task.done():
                logger.warning("Restarting weights task")
                weights_task = asyncio.create_task(weights_update_loop(db_manager))
            if cleanup_task.done():
                logger.warning("Restarting cleanup task")
                cleanup_task = asyncio.create_task(periodic_cleanup(db_manager))

            await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info("Shutting down…")
    finally:
        weights_task.cancel()
        cleanup_task.cancel()
        await asyncio.gather(weights_task, cleanup_task, return_exceptions=True)

        for proc in (evaluation_proc, challenge_proc):
            if proc.is_alive():
                proc.terminate()
                proc.join()

        db_manager.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

