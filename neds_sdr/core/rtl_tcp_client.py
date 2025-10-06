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

    async def connect(self):
        """Establish TCP connection."""
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.connected = True
            log.info("Connected to rtl_tcp at %s:%s", self.host, self.port)
        except Exception as e:
            log.error("Failed to connect to %s:%s (%s)", self.host, self.port, e)
            self.connected = False

    async def close(self):
        """Close connection gracefully."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.connected = False
        log.info("Disconnected from rtl_tcp %s:%s", self.host, self.port)

    async def set_frequency(self, freq_hz: float):
        """Send set frequency command."""
        if not self.writer:
            return
        cmd = struct.pack(">BI", 0x01, int(freq_hz))
        self.writer.write(cmd)
        await self.writer.drain()
        log.debug("Set frequency to %.4f MHz", freq_hz / 1e6)

    async def set_sample_rate(self, sample_rate: int):
        """Send set sample rate command."""
        if not self.writer:
            return
        cmd = struct.pack(">BI", 0x02, sample_rate)
        self.writer.write(cmd)
        await self.writer.drain()
        log.debug("Set sample rate to %d Hz", sample_rate)

    async def set_gain(self, gain_db: float):
        """Send set gain command."""
        if not self.writer:
            return
        cmd = struct.pack(">BB", 0x04, int(gain_db))
        self.writer.write(cmd)
        await self.writer.drain()
        log.debug("Set gain to %.1f dB", gain_db)

    async def read_iq(self, size: int = 16384) -> bytes:
        """Read IQ samples."""
        if not self.reader:
            return b""
        try:
            return await self.reader.readexactly(size)
        except asyncio.IncompleteReadError:
            log.warning("rtl_tcp read incomplete.")
            return b""
