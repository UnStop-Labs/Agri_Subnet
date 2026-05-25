"""neurons/validator.py — Entry point for running a validator neuron."""
import os

from dotenv import load_dotenv
load_dotenv()

import bittensor as bt
from validator.validator import IrrigationValidator
from irrigation.utils.logging import setup_logging


def main() -> None:
    setup_logging(level=os.environ.get("LOG_LEVEL", "INFO"))

    config = bt.config()
    config.wallet.name       = os.environ.get("WALLET_NAME",       "default")
    config.wallet.hotkey     = os.environ.get("WALLET_HOTKEY",     "default")
    config.subtensor.network = os.environ.get("SUBTENSOR_NETWORK", "finney")
    config.netuid            = int(os.environ.get("NETUID", "1"))

    validator = IrrigationValidator(config=config)
    validator.run()


if __name__ == "__main__":
    main()
