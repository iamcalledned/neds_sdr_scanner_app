"""
receiver.py
High-level per-dongle SDR receiver runtime.

Each SDRReceiver instance manages one rtl_tcp connection and
multiple logical channels. Each channel can have its own
frequency, squelch, tone, and sink routing.
"""

import asyncio
import logging
import numpy as np
from neds_sdr.core.rtl_tcp_client import RTL_TCP_Client
from neds_sdr.core.channel import Channel

log = logging.getLogger("SDRReceiver")


class SDRReceiver:
    """Manages a single rtl_tcp dongle and its associated channels."""

    def __init__(self, name: str, host: str, port: int, gain: float, event_bus):
        self.name = name
        self.host = host
        self.port = port
        self.gain = gain
        self.client = RTL_TCP_Client(host, port)
        self.event_bus = event_bus
        self.sample_rate = 2_048_000  # default sample rate
        self.running = False
        self.channels: dict[str, Channel] = {}

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def connect(self):
        """Connect to TCP server and initialize base configuration."""
        await self.client.connect()
        if not self.client.connected:
            log.error("[%s] Connection to rtl_tcp failed.", self.name)
            return

        await self.client.set_sample_rate(self.sample_rate)
        await self.client.set_gain(self.gain)

        self.running = True
        log.info("[%s] Connected to %s:%d (gain=%.1f)", self.name, self.host, self.port, self.gain)
        asyncio.create_task(self.run())

    async def disconnect(self):
        """Stop all channels and close TCP connection."""
        log.info("[%s] Shutting down receiver.", self.name)
        self.running = False
        for ch in list(self.channels.values()):
            await ch.stop()
        await self.client.close()
        self.event_bus.emit("dongle_disconnected", {"dongle": self.name})

    # -------------------------------------------------------------------------
    # Channel Management
    # -------------------------------------------------------------------------

    async def add_channel(self, channel_config: dict):
        """
        Create a new channel for this dongle.
        channel_config example:
        {
            "id": "ch_0",
            "frequency": 158.9925e6,
            "squelch": -45.0,
            "tone_type": "DPL",
            "tone_value": 223,
            "sink": "pd_sink"
        }
        """
        ch_id = channel_config.get("id", f"ch_{len(self.channels)}")
        if ch_id in self.channels:
            log.warning("[%s] Channel %s already exists.", self.name, ch_id)
            return

        channel = Channel(**channel_config, receiver=self, event_bus=self.event_bus)
        self.channels[ch_id] = channel
        await channel.start()
        self.event_bus.emit("channel_added", {"dongle": self.name, "channel": ch_id})
        log.info("[%s] Added channel %s @ %.4f MHz", self.name, ch_id, channel.frequency / 1e6)

    async def remove_channel(self, ch_id: str):
        """Stop and remove a channel."""
        if ch_id not in self.channels:
            return
        await self.channels[ch_id].stop()
        del self.channels[ch_id]
        self.event_bus.emit("channel_removed", {"dongle": self.name, "channel": ch_id})
        log.info("[%s] Removed channel %s", self.name, ch_id)

    # -------------------------------------------------------------------------
    # Runtime Loop
    # -------------------------------------------------------------------------

    async def run(self):
        """Main IQ data acquisition loop."""
        log.info("[%s] Receiver loop started.", self.name)
        buffer_size = 16384

        while self.running and self.client.connected:
            try:
                iq_bytes = await self.client.read_iq(buffer_size)
                if not iq_bytes:
                    await asyncio.sleep(0.05)
                    continue

                iq = np.frombuffer(iq_bytes, dtype=np.uint8).astype(np.float32)
                iq = (iq - 127.5) / 127.5

                # Emit per-dongle signal power
                power_db = 10 * np.log10(np.mean(iq ** 2) + 1e-12)
                self.event_bus.emit("signal_update", {"dongle": self.name, "power": power_db})

                # Feed IQ samples to all active channels
                for ch in list(self.channels.values()):
                    await ch.process_samples(iq)

            except Exception as e:
                log.error("[%s] Error in receiver loop: %s", self.name, e)
                await asyncio.sleep(0.2)

        log.info("[%s] Receiver loop exited.", self.name)
