"""
tests/conftest.py
Mock bittensor before any module imports it.

This lets the test suite run without a working Bittensor installation
(useful in CI and on Python 3.13 where websockets/substrate have
version conflicts).  All bittensor types are replaced with minimal
Pydantic / plain-object equivalents that satisfy the code-under-test.
"""
import sys
from unittest.mock import MagicMock
from pydantic import BaseModel


class _MockSynapse(BaseModel):
    """
    Pydantic BaseModel that stands in for bt.Synapse.
    extra="allow" mimics bt.Synapse's permissive field handling.
    """
    model_config = {"extra": "allow"}


class _MockNeuron:
    """Minimal base class for miner/validator neurons in tests."""
    def __init__(self, config=None):
        self.config = config or MagicMock()
        self.wallet = MagicMock()
        self.wallet.hotkey.ss58_address = "5MockHotkey000000000000000000000000000000000000"
        self.subtensor = MagicMock()
        self.metagraph  = MagicMock()
        self.dendrite   = MagicMock()


# ── Build the bt mock ──────────────────────────────────────────────────────────
_bt = MagicMock(name="bittensor")
_bt.Synapse            = _MockSynapse
_bt.BaseMinorNeuron    = _MockNeuron
_bt.BaseValidatorNeuron = _MockNeuron
_bt.Keypair            = MagicMock(name="Keypair")
_bt.config             = MagicMock(return_value=MagicMock())
_bt.wallet             = MagicMock(name="wallet")
_bt.subtensor          = MagicMock(name="subtensor")
_bt.dendrite           = MagicMock(name="dendrite")
_bt.AxonInfo           = MagicMock(name="AxonInfo")

# Inject BEFORE our modules are imported
sys.modules["bittensor"] = _bt
