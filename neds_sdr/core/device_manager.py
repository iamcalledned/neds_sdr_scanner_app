import asyncio
import logging
from neds_sdr.core.receiver import SDRReceiver

log = logging.getLogger("DeviceManager")


class DeviceManager:
    """Manages all connected SDR dongles."""

    def __init__(self, config_manager, event_bus):
        self.config_manager = config_manager
        self.event_bus = event_bus
        self.dongles: dict[str, SDRReceiver] = {}

    async def initialize(self):
        """Initialize all dongles defined in config.yaml."""
        cfg = self.config_manager.load()
        for d in cfg.get("dongles", []):
            name = d["name"]
            log.info("Initializing dongle: %s", name)
            receiver = SDRReceiver(
                name=name,
                host=d.get("host", "127.0.0.1"),
                port=d.get("port", 1234),
                gain=d.get("gain", 30),
                event_bus=self.event_bus,
            )
            await receiver.connect()
            self.dongles[name] = receiver
            self.event_bus.emit("dongle_connected", {"name": name})

    async def add_dongle(self, name, host, port, gain=30):
        """Add a new dongle at runtime."""
        log.info("Adding dongle %s (%s:%s)", name, host, port)
        receiver = SDRReceiver(name, host, port, gain, self.event_bus)
        await receiver.connect()
        self.dongles[name] = receiver
        self.event_bus.emit("dongle_added", {"name": name})
        # persist
        cfg = self.config_manager.config
        cfg["dongles"].append({"name": name, "host": host, "port": port, "gain": gain})
        self.config_manager.save(cfg)

    async def stop_all(self):
        """Gracefully stop all receivers."""
        for name, r in self.dongles.items():
            await r.disconnect()
        self.event_bus.emit("system_stopped", {})
