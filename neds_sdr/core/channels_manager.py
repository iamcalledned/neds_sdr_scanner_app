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
        self.channels: dict[str, Channel] = {}
        self.presets: dict[str, dict] = {}

        self.load_presets()

    # -------------------------------------------------------------------------
    # Preset persistence
    # -------------------------------------------------------------------------
    def load_presets(self):
        """Load channel presets from disk."""
        if self.preset_file.exists():
            try:
                self.presets = json.loads(self.preset_file.read_text())
                log.info("Loaded %d channel presets", len(self.presets))
            except Exception as e:
                log.error("Failed to load channel presets: %s", e)
                self.presets = {}
        else:
            self.presets = {}

    def save_presets(self):
        """Save current presets to disk."""
        try:
            self.preset_file.write_text(json.dumps(self.presets, indent=2))
            log.info("Saved %d channel presets", len(self.presets))
        except Exception as e:
            log.error("Error saving presets: %s", e)

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
        log.info("Preset added: %s @ %.4f MHz", name, frequency / 1e6)

    def remove_preset(self, name: str):
        """Delete a preset by name."""
        if name in self.presets:
            del self.presets[name]
            self.save_presets()
            log.info("Preset removed: %s", name)

    def list_presets(self):
        """Return a list of preset names."""
        return list(self.presets.keys())

    async def set_channel(self, name: str):
        """Stop all active channels and start the one matching the preset name."""
        if name not in self.presets:
            log.warning("No such channel preset: %s", name)
            return

        # Stop existing channels
        for ch in self.channels.values():
            await ch.stop()
        self.channels.clear()

        # ✅ local import breaks circular dependency
        from neds_sdr.core.channel import Channel

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
        self.channels[name] = channel
        await channel.start()
        log.info("Tuned to preset: %s @ %.4f MHz", name, cfg["frequency"] / 1e6)
