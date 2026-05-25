"""
miner — IrrigationMiner neuron and supporting modules.

IrrigationMiner is not imported at package level to avoid pulling in
bittensor on import. Use: from miner.miner import IrrigationMiner
"""
__all__ = ["IrrigationMiner"]

def __getattr__(name):
    if name == "IrrigationMiner":
        from miner.miner import IrrigationMiner
        return IrrigationMiner
    raise AttributeError(f"module 'miner' has no attribute {name!r}")
