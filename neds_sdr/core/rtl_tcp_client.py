"""
rtl_tcp_client.py
Async TCP client for rtl_tcp protocol.
"""

import asyncio
import struct
import logging

log = logging.getLogger("RTL_TCP_Client")


class RTL_TCP_Client:
    """Handles connection and command protocol for rtl_tcp servers."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.connected = False

    # ----------------------------------------------------------------------
    # Connection management
    # ----------------------------------------------------------------------
    async def connect(self):
        """Establish TCP connection and initialize manual gain mode."""
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.connected = True
            log.info("Connected to rtl_tcp at %s:%s", self.host, self.port)
            # rtl_tcp expects gain mode set immediately
            await self._send_cmd(0x03, 1)  # SET_GAIN_MODE = manual
        except Exception as e:
            log.error("Failed to connect to %s:%s (%s)", self.host, self.port, e)
            self.connected = False

    async def close(self):
        """Close connection gracefully."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.connected = False
        log.info("Disconnected from rtl_tcp %s:%s", self.host, self.port)

    # ----------------------------------------------------------------------
    # Core command helpers
    # ----------------------------------------------------------------------
    async def _send_cmd(self, cmd_id: int, value: int):
        """Send 5-byte rtl_tcp command: 1-byte ID + 4-byte big-endian integer."""
        if not self.writer:
            return
        try:
            # Command payload: 1 byte ID (big-endian), 4 byte value (big-endian)
            packet = struct.pack(">BI", cmd_id, int(value))
            self.writer.write(packet)
            await self.writer.drain()
        except Exception as e:
            log.error("Failed to send cmd 0x%02X: %s", cmd_id, e)
            await self.close()

    # ----------------------------------------------------------------------
    # rtl_tcp protocol commands
    # ----------------------------------------------------------------------

    async def set_frequency(self, freq_hz: float):
        """Set tuner center frequency (Hz)."""
        if not self.writer:
            return
        await self._send_cmd(0x01, int(freq_hz))
        # FIX: Add a small delay to ensure rtl_tcp processes the command before others start.
        await asyncio.sleep(0.01) 
        log.debug("Set frequency to %.4f MHz", freq_hz / 1e6)

    async def set_sample_rate(self, sample_rate: int):
        """Set tuner sample rate (Hz)."""
        if not self.writer:
            return
        await self._send_cmd(0x02, int(sample_rate))
        log.debug("Set sample rate to %d Hz", sample_rate)

    async def set_gain(self, gain_db: float):
        """Set tuner RF gain (manual mode)."""
        if not self.writer:
            return
        # rtl_tcp expects tenths of a dB as a 32-bit signed int
        gain_val = int(round(gain_db * 10))
        await self._send_cmd(0x04, gain_val)
        log.debug("Set gain to %.1f dB (encoded %d)", gain_db, gain_val)

    async def set_ppm_correction(self, ppm: int):
        """Set frequency correction (ppm)."""
        if not self.writer:
            return
        await self._send_cmd(0x05, int(ppm))
        log.debug("Set PPM correction to %d ppm", ppm)

    # ----------------------------------------------------------------------
    # IQ reading
    # ----------------------------------------------------------------------
    async def read_iq(self, size: int = 16384) -> bytes:
        if not self.reader:
            return b""
        try:
            return await self.reader.readexactly(size)
        except asyncio.IncompleteReadError:
            # server closed or EOF
            self.connected = False
            log.warning("rtl_tcp EOF / incomplete read; marking disconnected.")
            return b""
        except (ConnectionResetError, BrokenPipeError) as e:
            self.connected = False
            log.warning("rtl_tcp socket error: %s; marking disconnected.", e)
            return b""
