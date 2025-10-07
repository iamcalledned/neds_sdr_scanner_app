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
#from neds_sdr.core.channel import Channel # Kept commented out as in original
from neds_sdr.core.channels_manager import ChannelsManager

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
        self.channels: dict[str, 'Channel'] = {} # Forward declaration of Channel type
        self._rx_task: asyncio.Task | None = None

        # Per-dongle preset manager
        self.presets = ChannelsManager(self, event_bus)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def connect(self):
        """Connect to TCP server and initialize base configuration."""
        await self.client.connect()
        if not self.client.connected:
            log.error("[%s] Connection to rtl_tcp failed.", self.name)
            return

        # Configure the dongle
        await self.client.set_sample_rate(self.sample_rate)
        await asyncio.sleep(0.05)
        await self.client.set_gain(self.gain)
        await asyncio.sleep(0.05)

        # Mark running and start persistent reader loop
        self.running = True
        log.info("[%s] Connected to %s:%d (gain=%.1f)", self.name, self.host, self.port, self.gain)
        self._rx_task = asyncio.create_task(self._rx_loop())

    async def disconnect(self):
        """Stop all channels and close TCP connection."""
        log.info("[%s] Shutting down receiver.", self.name)
        self.running = False

        # stop channels
        for ch in list(self.channels.values()):
            try:
                await ch.stop()
            except Exception:
                pass

        # close TCP client
        try:
            await self.client.close()
        except Exception:
            pass

        # cancel rx loop if still active
        if self._rx_task and not self._rx_task.done():
            self._rx_task.cancel()
            try:
                await self._rx_task
            except asyncio.CancelledError:
                pass

        self.event_bus.emit("dongle_disconnected", {"dongle": self.name})
        log.info("[%s] Receiver disconnected.", self.name)

    # -------------------------------------------------------------------------
    # Channel Management
    # -------------------------------------------------------------------------

    async def add_channel(self, channel_config: dict):
        """Create and start a new logical channel for this dongle."""
        from neds_sdr.core.channel import Channel  # ← move it here

        ch_id = channel_config.get("id", f"ch_{len(self.channels)}")
        if ch_id in self.channels:
            log.warning("[%s] Channel %s already exists.", self.name, ch_id)
            return

        # 1. Create the Channel instance, linking it to this receiver (self).
        channel = Channel(**channel_config, receiver=self, event_bus=self.event_bus)
        self.channels[ch_id] = channel
        
        # 2. Start the channel. This is where the call to set_frequency() now happens, 
        # using the Channel's known frequency and its receiver's client.
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

    async def set_channel(self, preset_name: str):
        """
        Use ChannelsManager to stop current channels and start a preset channel.
        """
        if not self.running:
            log.warning("[%s] Receiver not running.", self.name)
            return
        await self.presets.set_channel(preset_name)

    # -------------------------------------------------------------------------
    # Persistent RX Loop
    # -------------------------------------------------------------------------

    async def _rx_loop(self):
        log.info("[%s] Receiver loop started.", self.name)
        buffer_size = 16384
        try:
            while self.running and self.client.connected:
                iq_bytes = await self.client.read_iq(buffer_size)
                if not iq_bytes:
                    await asyncio.sleep(0.05)
                    continue
                iq = np.frombuffer(iq_bytes, dtype=np.uint8).astype(np.float32)
                iq = (iq - 127.5) / 127.5

                # Emit signal power
                power_db = 10 * np.log10(np.mean(iq ** 2) + 1e-12)
                self.event_bus.emit("signal_update", {"dongle": self.name, "power": power_db})

                # Feed samples to channels
                for ch in list(self.channels.values()):
                    try:
                        await ch.process_samples(iq)
                    except Exception as e:
                        log.error("[%s] Channel %s processing error: %s", self.name, ch.id, e)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("[%s] Receiver loop error: %s", self.name, e)
        finally:
            self.running = False
            await self.client.close()
            log.info("[%s] Receiver loop exited.", self.name)
