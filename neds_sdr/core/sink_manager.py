"""
sink_manager.py
Manages PulseAudio sinks for audio routing.
"""

import subprocess
import logging
import os

log = logging.getLogger("SinkManager")


class SinkManager:
    """Check and manage PulseAudio sinks."""

    def __init__(self):
        self.sinks = self.list_sinks()

    def list_sinks(self) -> list[str]:
        """Return a list of current PulseAudio sinks."""
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True, text=True, check=True
            )
            return [line.split("\t")[1] for line in result.stdout.splitlines()]
        except Exception as e:
            log.error("Failed to list sinks: %s", e)
            return []

    def ensure_sink(self, name: str):
        """Create a sink if missing."""
        if name not in self.list_sinks():
            try:
                subprocess.run(
                    ["pactl", "load-module", "module-null-sink", f"sink_name={name}"],
                    check=True
                )
                log.info("Created PulseAudio sink: %s", name)
            except Exception as e:
                log.error("Failed to create sink %s: %s", name, e)
        else:
            log.debug("Sink %s already exists", name)

    def route_audio(self, sink_name: str, pcm_data: bytes):
        """Stub: send PCM to sink (future audio handling)."""
        # For now, just placeholder
        if sink_name not in self.list_sinks():
            log.warning("Sink %s not found; cannot route audio.", sink_name)
        else:
            # Later we’ll implement PulseAudio stream writer here
            pass
