"""
audio_output.py
Handles writing PCM audio to PulseAudio sinks or named pipes.
"""

import os
import wave
import logging
import numpy as np
import sounddevice as sd
import pulsectl

log = logging.getLogger("AudioOutput")


class AudioOutput:
    """Low-level audio routing for squelched audio frames."""

    def __init__(self, sink_name: str, sample_rate: int = 48000):
        self.sink_name = sink_name
        self.sample_rate = sample_rate
        self.pa = None
        self.stream = None
        self.pipe_path = f"/tmp/{sink_name}"
        self.ensure_sink()

    # ------------------------------------------------------------------
    def ensure_sink(self):
        """Verify PulseAudio sink or named pipe exists; create if missing."""
        try:
            self.pa = pulsectl.Pulse("neds-sdr")
            sinks = [s.name for s in self.pa.sink_list()]
            if self.sink_name not in sinks:
                log.warning("Sink %s not found; creating null sink.", self.sink_name)
                os.system(f"pactl load-module module-null-sink sink_name={self.sink_name}")
            log.info("Audio sink verified: %s", self.sink_name)
        except Exception:
            # Fallback: create named pipe if PulseAudio not running
            if not os.path.exists(self.pipe_path):
                os.mkfifo(self.pipe_path)
            log.warning("Using pipe output instead of PulseAudio: %s", self.pipe_path)

    # ------------------------------------------------------------------
    def write(self, audio: np.ndarray):
        """Send 16-bit PCM audio to sink or pipe."""
        if audio.size == 0:
            return
        pcm16 = np.int16(np.clip(audio * 32767.0, -32768, 32767))
        try:
            if self.pa:
                sd.play(pcm16, samplerate=self.sample_rate, blocking=False)
            else:
                # Write to named pipe
                with open(self.pipe_path, "ab", buffering=0) as f:
                    f.write(pcm16.tobytes())
        except Exception as e:
            log.error("Audio write failed: %s", e)

    # ------------------------------------------------------------------
    def close(self):
        if self.pa:
            self.pa.close()
        self.pa = None
