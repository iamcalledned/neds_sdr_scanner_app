"""
__main__.py — Entry point for Neds SDR Control.
Runs startup dialog non-blocking, then launches main UI.
"""

import sys
import asyncio
import logging
from PyQt6 import QtWidgets
from qasync import QEventLoop, asyncSlot, run

from neds_sdr.core.event_bus import EventBus
from neds_sdr.core.device_manager import DeviceManager
from neds_sdr.ui.app import UIController
from neds_sdr.ui.startup import StartupDialog


async def main():
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("Main")

    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    event_bus = EventBus()
    device_manager = DeviceManager(event_bus)

    # --- show startup dialog ---
    startup = StartupDialog(device_manager)

    done_future = asyncio.get_event_loop().create_future()

    @asyncSlot()
    async def on_finished(result):
        """Called when startup dialog closes."""
        if not done_future.done():
            done_future.set_result(result)

    startup.finished.connect(on_finished)
    startup.show()

    # Wait for dialog to finish
    await done_future

    # --- show main UI ---
    ui = UIController(device_manager, None, event_bus)
    ui.show()
    log.info("Neds SDR Control UI launched and running.")

    await asyncio.Future()  # keep running forever


if __name__ == "__main__":
    run(main())
