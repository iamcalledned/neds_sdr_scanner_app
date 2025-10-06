"""
channel.py
Defines individual channel configurations and DSP logic.

Each Channel instance belongs to an SDRReceiver and represents
a single tuned frequency path with its own squelch, tone detector,
and audio output sink.

When squelch opens, demodulated audio is written to the sink (PulseAudio
or named pipe). When squelch closes, audio output stops immediately.
"""

import asyncio
import numpy as np
import logging
from neds_sdr.core.squelch import SquelchGate
from neds_sdr.core.tone_detector import ToneDetector
from neds_sdr.dsp.fm_demod import fm_demodulate
from neds_sdr.core.audio_output import AudioOutput

log = logging.getLogger("Channel")


class Channel:
    """Represents a single demodulated audio channel."""

    def __init__(self, id: str, frequency: float, squelch: float,
                 tone_type: str | None, tone_value: float | None,
                 sink: str, receiver, event_bus):
        """
        Args:
            id: Channel identifier (e.g., 'ch_0')
            frequency: Frequency in Hz
            squelch: Squelch threshold (dB)
            tone_type: 'PL', 'DPL', or None
            tone_value: Tone frequency (Hz) or code
            sink: PulseAudio sink or pipe name
            receiver: Parent SDRReceiver
            event_bus: Shared event bus for UI and backend
        """
        self.id = id
        self.frequency = frequency
        self.squelch_level = squelch
        self.tone_type = tone_type
        self.tone_value = tone_value
        self.sink = sink
        self.receiver = receiver
        self.event_bus = event_bus
        self.running = False

        # Signal processing
        self.squelch = SquelchGate(threshold_db=self.squelch_level)
        self.tone = ToneDetector(tone_type=self.tone_type,
                                 tone_value=self.tone_value,
                                 sample_rate=48000)
        self.audio = AudioOutput(self.sink, sample_rate=48000)
        self._last_phase = 0.0
        self._open = False

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def start(self):
        """Tune frequency and mark channel active."""
        self.running = True
        await self.receiver.client.set_frequency(self.frequency)
        log.info("[%s:%s] Channel started @ %.4f MHz",
                 self.receiver.name, self.id, self.frequency / 1e6)

    async def stop(self):
        """Stop channel processing."""
        self.running = False
        log.info("[%s:%s] Channel stopped.", self.receiver.name, self.id)

    # -------------------------------------------------------------------------
    # DSP Chain
    # -------------------------------------------------------------------------

    async def process_samples(self, iq: np.ndarray):
        """
        Demodulate and process IQ samples.
        Applies FM demod, squelch, and tone detection.
        """
        if not self.running or iq.size < 4:
            return

        # --- FM demodulation ---
        demod, self._last_phase = fm_demodulate(iq, self._last_phase)

        # --- Squelch + Tone Detection ---
        squelch_open = self.squelch.update(demod)
        tone_match = self.tone.match(demod)

        if squelch_open and tone_match:
            if not self._open:
                self._open = True
                self.event_bus.emit("squelch_open", {
                    "dongle": self.receiver.name,
                    "channel": self.id,
                    "freq": self.frequency
                })
                log.info("[%s:%s] Squelch OPEN @ %.4f MHz",
                         self.receiver.name, self.id, self.frequency / 1e6)

            # --- Route audio to sink ---
            self.audio.write(demod)

        elif self._open:
            # Transition: open -> closed
            self._open = False
            self.event_bus.emit("squelch_closed", {
                "dongle": self.receiver.name,
                "channel": self.id,
                "freq": self.frequency
            })
            log.info("[%s:%s] Squelch CLOSED @ %.4f MHz",
                     self.receiver.name, self.id, self.frequency / 1e6)

        # Give event loop a chance to breathe
        await asyncio.sleep(0.005)
