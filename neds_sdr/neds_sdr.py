"""
Neds SDR Control System
Main entry point for configuration and runtime control.
"""

import asyncio
import os
from neds_sdr.core.logger import setup_logging
from neds_sdr.core.config_manager import ConfigManager
from neds_sdr.core.device_manager import DeviceManager
from neds_sdr.core.event_bus import EventBus
from neds_sdr.ui.app import UIController


async def main():
    # --- Setup Environment ---
    config_path = os.getenv("CONFIG_FILE", "./config.yaml")

    # --- Initialize Core Components ---
    setup_logging()
    event_bus = EventBus()
    config_manager = ConfigManager(config_path)
    device_manager = DeviceManager(config_manager, event_bus)

    # --- Initialize Runtime ---
    await device_manager.initialize()

    # --- Launch UI Controller ---
    ui = UIController(device_manager, config_manager, event_bus)
    ui.start()


if __name__ == "__main__":
    asyncio.run(main())
