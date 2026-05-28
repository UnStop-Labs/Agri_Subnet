import ipaddress
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fiber.chain import fetch_nodes
from fiber.chain.chain_utils import load_hotkey_keypair
from fiber.chain.interface import get_substrate
from fiber.chain.models import Node
from fiber.logging_utils import get_logger

# ---------------------------------------------------------------------------
# Same monkey-patch as validator — handles fresh subnets with empty trust.
# Must run before any request hits metagraph.sync_nodes().
# ---------------------------------------------------------------------------
_orig_get_nodes = fetch_nodes.get_nodes_for_netuid


def _decode_account_id(raw) -> str:
    """Convert a raw AccountId (bytes tuple from runtime API) to SS58 address."""
    if isinstance(raw, str) and len(raw) > 10:
        return raw
    try:
        inner = raw
        # Unwrap outer 1-element tuple: ((bytes...,),) → (bytes...,)
        if isinstance(inner, (list, tuple)) and len(inner) == 1 and isinstance(inner[0], (list, tuple)):
            inner = inner[0]
        if isinstance(inner, (list, tuple)):
            from substrateinterface.utils.ss58 import ss58_encode
            return ss58_encode(bytes(inner), ss58_format=42)
    except Exception:
        pass
    return str(raw)


def _safe_get_nodes(substrate, netuid, block=None):
    try:
        return _orig_get_nodes(substrate=substrate, netuid=netuid, block=block)
    except Exception:
        try:
            result = substrate.runtime_call("NeuronInfoRuntimeApi", "get_neurons_lite", [netuid])
            neurons = (result.value or []) if result else []
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
                    tao_stake=total_stake / 1e9,
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
            return nodes
        except Exception:
            return []


fetch_nodes.get_nodes_for_netuid = _safe_get_nodes

from miner.core.models.config import Config
from miner.core.configuration import factory_config
from miner.dependencies import get_config
from miner.endpoints.irrigation import router as irrigation_router
from miner.endpoints.availability import router as availability_router

load_dotenv()
logger = get_logger(__name__)

app = FastAPI(title="Irrigation Subnet Miner")

app.dependency_overrides[Config] = get_config

app.include_router(irrigation_router, prefix="/irrigation", tags=["irrigation"])
app.include_router(availability_router, tags=["availability"])


@app.on_event("startup")
async def announce_axon():
    """Tell the chain our IP and port so the validator can find us."""
    external_ip = os.getenv("MINER_EXTERNAL_IP", "")
    port = int(os.getenv("MINER_PORT", "8001"))
    netuid = int(os.getenv("NETUID", "2"))
    wallet_name = os.getenv("WALLET_NAME", "default")
    hotkey_name = os.getenv("HOTKEY_NAME", "default")
    subtensor_network = os.getenv("SUBTENSOR_NETWORK")
    subtensor_address = os.getenv("SUBTENSOR_ADDRESS")

    if not external_ip:
        logger.warning("MINER_EXTERNAL_IP not set — skipping axon announcement")
        return

    try:
        substrate = get_substrate(
            subtensor_network=subtensor_network,
            subtensor_address=subtensor_address,
        )
        keypair = load_hotkey_keypair(wallet_name, hotkey_name)

        ip_int = int(ipaddress.ip_address(external_ip))
        call = substrate.compose_call(
            call_module="SubtensorModule",
            call_function="serve_axon",
            call_params={
                "version": 1,
                "ip": ip_int,
                "port": port,
                "ip_type": 4,
                "netuid": netuid,
                "protocol": 4,
                "placeholder1": 0,
                "placeholder2": 0,
            },
        )
        extrinsic = substrate.create_signed_extrinsic(call=call, keypair=keypair)
        result = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        logger.info(f"Axon announced: {external_ip}:{port} on netuid {netuid} — {result}")
    except Exception as e:
        logger.error(f"Axon announcement failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "miner.main:app",
        host="0.0.0.0",
        port=int(os.getenv("MINER_PORT", "8001")),
        reload=False,
    )

