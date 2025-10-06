"""
squelch.py
Signal squelch gate and measurement utilities.
"""

import numpy as np
import logging

log = logging.getLogger("SquelchGate")


class SquelchGate:
    """Power-based squelch controller with hysteresis."""

    def __init__(self, threshold_db: float = -45.0, hysteresis_db: float = 2.0):
        self.threshold_db = threshold_db
        self.hysteresis_db = hysteresis_db
        self.state_open = False

    def measure_power(self, samples: np.ndarray) -> float:
        """Return signal power in dBFS."""
        if samples.size == 0:
            return -120.0
        rms = np.sqrt(np.mean(samples ** 2))
        power = 20 * np.log10(rms + 1e-12)
        return float(power)

    def update(self, samples: np.ndarray) -> bool:
        """
        Evaluate signal power and update squelch state.
        Returns True if squelch is OPEN.
        """
        power_db = self.measure_power(samples)
        if not self.state_open and power_db > self.threshold_db:
            self.state_open = True
            log.debug("Squelch OPEN (%.2f dB > %.2f)", power_db, self.threshold_db)
        elif self.state_open and power_db < (self.threshold_db - self.hysteresis_db):
            self.state_open = False
            log.debug("Squelch CLOSE (%.2f dB < %.2f)", power_db, self.threshold_db)
        return self.state_open
