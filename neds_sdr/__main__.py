# neds_sdr/__main__.py
"""
Entry point for Neds SDR Control.
This only starts the UI — no dongles auto-connect.
"""

import sys
import asyncio
import logging
from PyQt6 import QtWidgets
import qasync

from neds_sdr.core.config_manager import ConfigManager
from neds_sdr.core.device_manager import DeviceManager
from neds_sdr.core.event_bus import EventBus
from neds_sdr.ui.app import UIController


async def main():
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("Main")

    # Backend setup
    event_bus = EventBus()
    config = ConfigManager()
    device_manager = DeviceManager(config, event_bus, autostart=False)  # no auto-start

    # Qt / asyncio integration
    app = QtWidgets.QApplication(sys.argv)
    qloop = qasync.QEventLoop(app)
    asyncio.set_event_loop(qloop)

    ui = UIController(device_manager, config, event_bus)
    ui.show()

    log.info("Neds SDR Control UI launched.")
    with qloop:
        qloop.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
