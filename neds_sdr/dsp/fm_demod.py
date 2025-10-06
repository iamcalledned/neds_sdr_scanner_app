"""
fm_demod.py
Wideband / narrowband FM demodulation utilities.
"""

import numpy as np


def fm_demodulate(iq: np.ndarray, prev_phase: float = 0.0):
    """
    Perform narrowband FM demodulation.

    Args:
        iq: complex64 or float32 interleaved IQ samples normalized to ±1
        prev_phase: last phase value from previous block

    Returns:
        demod (np.ndarray): demodulated mono audio (float32)
        last_phase (float): last phase for continuity
    """
    if iq.size < 4:
        return np.zeros(0, np.float32), prev_phase

    # If input is interleaved I/Q bytes, convert
    if iq.ndim == 1 and iq.dtype != np.complex64:
        i = iq[::2]
        q = iq[1::2]
        iq = i + 1j * q

    # Compute phase difference
    phase = np.angle(iq)
    dphase = np.diff(np.unwrap(phase))
    # Normalize and clip to audio range
    demod = np.clip(dphase, -np.pi, np.pi).astype(np.float32)
    return demod, phase[-1]
