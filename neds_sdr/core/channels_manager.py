"""
channels_manager.py
Handles storage, retrieval, and switching of channel presets.
"""

import json
import logging
from pathlib import Path


log = logging.getLogger("ChannelsManager")


class ChannelsManager:
    """
    Manages channel presets and active channel instances per receiver.
    """

    def __init__(self, receiver, event_bus, preset_file: str = "channels.json"):
        self.receiver = receiver
        self.event_bus = event_bus
        self.preset_file = Path(preset_file)
        self.presets: dict[str, dict] = {} # only stores configuration
        
        self.load_presets()

    # -------------------------------------------------------------------------
    # Preset persistence
    # -------------------------------------------------------------------------
    def load_presets(self):
        """Load channel presets from disk."""
        # NOTE: This implementation loads from a generic 'channels.json'.
        # For a multi-dongle system, you might want to load/save based on dongle name.
        if self.preset_file.exists():
            try:
                self.presets = json.loads(self.preset_file.read_text())
                log.info("[%s] Loaded %d channel presets", self.receiver.name, len(self.presets))
            except Exception as e:
                log.error("[%s] Failed to load channel presets: %s", self.receiver.name, e)
                self.presets = {}
        else:
            self.presets = {}

    def save_presets(self):
        """Save current presets to disk."""
        try:
            self.preset_file.write_text(json.dumps(self.presets, indent=2))
            log.info("[%s] Saved %d channel presets", self.receiver.name, len(self.presets))
        except Exception as e:
            log.error("[%s] Error saving presets: %s", self.receiver.name, e)

    # -------------------------------------------------------------------------
    # Preset management
    # -------------------------------------------------------------------------
    def add_preset(self, name: str, frequency: float, squelch: float = -50,
                   tone_type: str | None = None, tone_value: float | None = None,
                   sink: str = "default"):
        """Add a new preset."""
        self.presets[name] = {
            "frequency": frequency,
            "squelch": squelch,
            "tone_type": tone_type,
            "tone_value": tone_value,
            "sink": sink
        }
        self.save_presets()
        log.info("[%s] Preset added: %s @ %.4f MHz", self.receiver.name, name, frequency / 1e6)

    def remove_preset(self, name: str):
        """Delete a preset by name."""
        if name in self.presets:
            del self.presets[name]
            self.save_presets()
            log.info("[%s] Preset removed: %s", self.receiver.name, name)

    def list_presets(self):
        """Return a list of preset names."""
        return list(self.presets.keys())

    async def set_channel(self, name: str):
        """Stop all active channels and start the one matching the preset name."""
        if name not in self.presets:
            log.warning("[%s] No such channel preset: %s", self.receiver.name, name)
            return

        # 1. Stop existing channels associated with the SDRReceiver
        for ch_id, ch in list(self.receiver.channels.items()):
            await ch.stop()
            del self.receiver.channels[ch_id] # Must remove from the receiver's live dict

        # 2. Local import of Channel (necessary to break circular dependency)
        from neds_sdr.core.channel import Channel 

        # 3. Create new Channel instance
        cfg = self.presets[name]
        channel = Channel(
            id=name,
            frequency=cfg["frequency"],
            squelch=cfg["squelch"],
            tone_type=cfg["tone_type"],
            tone_value=cfg["tone_value"],
            sink=cfg["sink"],
            receiver=self.receiver,
            event_bus=self.event_bus,
        )
        
        # 4. CRITICAL: Register the new channel instance in the SDRReceiver's live channel map.
        # This ensures the RX loop (_rx_loop in SDRReceiver) sees it and feeds it samples.
        self.receiver.channels[name] = channel

        # 5. Start the channel (which handles the set_frequency call)
        await channel.start()
        
        log.info("[%s] Tuned to preset: %s @ %.4f MHz. Active channels: %d", 
                 self.receiver.name, name, cfg["frequency"] / 1e6, len(self.receiver.channels))
