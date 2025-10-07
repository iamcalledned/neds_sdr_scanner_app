# __main__.py
"""
Entry: run a single qasync loop; show Startup non-blocking; then show main UI.
"""

import sys
import asyncio
import logging
from PyQt6 import QtWidgets
from qasync import QEventLoop, run, wait_signal

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

    # Show StartupDialog *non-blocking*
    startup = StartupDialog(device_manager)
    startup.setModal(True)
    startup.show()

    # Let all async tasks (like receiver.connect()) run while dialog is open.
    await wait_signal(startup.finished)

    # Now show the main UI
    ui = UIController(device_manager, None, event_bus)
    ui.show()
    log.info("Neds SDR Control UI launched and running.")

    # Keep the app alive forever; Ctrl+C or window close will exit.
    await asyncio.Future()


if __name__ == "__main__":
    run(main())
