"""
validator — IrrigationValidator neuron and supporting modules.

IrrigationValidator is not imported at package level to avoid pulling in
bittensor on import. Use: from validator.validator import IrrigationValidator
"""
__all__ = ["IrrigationValidator"]

def __getattr__(name):
    if name == "IrrigationValidator":
        from validator.validator import IrrigationValidator
        return IrrigationValidator
    raise AttributeError(f"module 'validator' has no attribute {name!r}")
