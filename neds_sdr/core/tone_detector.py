"""
tone_detector.py
Tone squelch (PL / DPL) detection utilities.
"""

import numpy as np
import logging

log = logging.getLogger("ToneDetector")


class ToneDetector:
    """Detects continuous subaudible (PL) or digital (DPL) tones."""

    def __init__(self, tone_type: str | None = None, tone_value: float | None = None,
                 sample_rate: int = 48000):
        self.tone_type = tone_type      # "PL", "DPL", or None
        self.tone_value = tone_value
        self.sample_rate = sample_rate
        self._threshold = 0.01          # detection threshold (normalized)

    def detect_ctcss(self, audio: np.ndarray) -> bool:
        """Goertzel-based detection for analog CTCSS tones."""
        if audio.size == 0 or self.tone_value is None:
            return False

        # window length ~0.5 s for tone detection
        window = int(self.sample_rate * 0.5)
        if audio.size < window:
            return False
        buf = audio[-window:]

        # Goertzel filter
        k = int(0.5 + (window * self.tone_value / self.sample_rate))
        w = (2.0 * np.pi / window) * k
        cosine = np.cos(w)
        sine = np.sin(w)
        coeff = 2.0 * cosine

        q0 = q1 = q2 = 0.0
        for sample in buf:
            q0 = coeff * q1 - q2 + sample
            q2, q1 = q1, q0

        magnitude = np.sqrt(q1 ** 2 + q2 ** 2 - q1 * q2 * coeff)
        detected = magnitude > self._threshold
        return detected

    def detect_dcs(self, audio: np.ndarray) -> bool:
        """Stub: digital DCS tone detection (future bit correlation)."""
        # Placeholder logic; always True for now
        return True

    def match(self, audio: np.ndarray) -> bool:
        """Return True if configured tone is present."""
        if self.tone_type == "PL":
            return self.detect_ctcss(audio)
        elif self.tone_type == "DPL":
            return self.detect_dcs(audio)
        return True  # no tone squelch configured
