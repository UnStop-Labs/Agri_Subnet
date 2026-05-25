"""
irrigation — core package for the Field Irrigation Intelligence Network.

Lazy imports: bittensor is only pulled in when the synapse classes are
explicitly requested, so test modules that don't need it stay fast.
"""
from irrigation.protocol import PROTOCOL_VERSION, SUBNET_NAME
from irrigation.constants import SCORE_WEIGHTS, MOISTURE_THRESHOLDS

__version__ = "1.1.0"

__all__ = [
    "PROTOCOL_VERSION",
    "SUBNET_NAME",
    "SCORE_WEIGHTS",
    "MOISTURE_THRESHOLDS",
    "__version__",
]
