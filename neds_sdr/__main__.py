"""
__main__.py — Entry point for Neds SDR app
Fully async-safe version: allows TCP connect + GUI to stay alive.
"""

import sys
import asyncio
import logging
from PyQt6 import QtWidgets
from qasync import QEventLoop, asyncSlot, run as qasync_run

from neds_sdr.core.event_bus import EventBus
from neds_sdr.core.device_manager import DeviceManager
from neds_sdr.ui.app import UIController
from neds_sdr.ui.startup import StartupDialog


async def main():
    """Async startup and main UI logic."""
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("Main")

    event_bus = EventBus()
    device_manager = DeviceManager(event_bus)

    # Create the startup dialog
    startup = StartupDialog(device_manager)

    # Show the startup dialog asynchronously
    fut = asyncio.get_event_loop().create_future()

    def on_done(result):
        if not fut.done():
            fut.set_result(result)

    startup.finished.connect(on_done)
    startup.show()

    # Wait for the dialog to finish (non-blocking)
    result = await fut

    if result == QtWidgets.QDialog.DialogCode.Accepted:
        ui = UIController(device_manager, None, event_bus)
        ui.show()
        log.info("Neds SDR Control UI launched and running.")
    else:
        log.info("Startup canceled. Exiting app.")
        QtWidgets.QApplication.quit()


def main_entry():
    """Start Qt+async event loop together (no blocking)."""
    app = QtWidgets.QApplication(sys.argv)

    # Use qasync to manage the event loop
    qasync_run(main())


if __name__ == "__main__":
    main_entry()
