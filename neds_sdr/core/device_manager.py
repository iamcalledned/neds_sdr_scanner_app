import asyncio
import logging
from neds_sdr.core.receiver import SDRReceiver

log = logging.getLogger("DeviceManager")


class DeviceManager:
    """Manages all SDR dongles and their channel configurations."""

    def __init__(self, config_manager, event_bus, autostart: bool = True):
        """
        Args:
            config_manager: ConfigManager instance
            event_bus: EventBus instance
            autostart: whether to auto-connect dongles on startup
        """
        self.config_manager = config_manager
        self.event_bus = event_bus
        self.dongles: dict[str, SDRReceiver] = {}
        self.autostart = autostart

        # Initialize all receivers
        asyncio.create_task(self.initialize())

    # ------------------------------------------------------------------
    async def initialize(self):
        """Load dongles from config and optionally connect them."""
        cfg = self.config_manager.config
        for d in cfg.get("dongles", []):
            name = d.get("name")
            host = d.get("host", "127.0.0.1")
            port = d.get("port", 1234)
            gain = d.get("gain", 30)
            receiver = SDRReceiver(name, host, port, gain, self.event_bus)
            self.dongles[name] = receiver
            log.info("Initializing dongle: %s", name)

            if self.autostart:
                await receiver.connect()

            # Create channels for this dongle
            for ch_cfg in d.get("channels", []):
                await receiver.add_channel(ch_cfg)

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


    async def set_gain(self, name: str, gain: float):
        """Set dongle gain live."""
        if name not in self.dongles:
            return
        r = self.dongles[name]
        r.gain = gain
        await r.client.set_gain(gain)
        self.event_bus.emit("dongle_gain_updated", {"dongle": name, "gain": gain})
        # persist
        for d in self.config_manager.config.get("dongles", []):
            if d["name"] == name:
                d["gain"] = gain
        self.config_manager.save(self.config_manager.config)

    async def retune_channel(self, dongle_name: str, channel_id: str, freq_mhz: float):
        """Change channel frequency live."""
        r = self.dongles.get(dongle_name)
        if not r:
            return
        ch = r.channels.get(channel_id)
        if not ch:
            return
        await ch.set_frequency(freq_mhz * 1e6)
        self.event_bus.emit("channel_retuned", {
            "dongle": dongle_name,
            "channel": channel_id,
            "frequency": freq_mhz
        })