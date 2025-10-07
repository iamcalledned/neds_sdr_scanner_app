"""
device_manager.py

DeviceManager for runtime (live) SDR detection and TCP management.

Features:
- detect_sdr_devices(): discover attached RTL-SDR USB devices (pyrtlsdr preferred,
  fallback to rtl_test parsing).
- tcp_scan(): scan localhost ports for listening rtl_tcp servers.
- start_rtl_tcp(device_index, port): start rtl_tcp subprocess for a device index.
- attach_tcp(port, name): create and register an SDRReceiver attached to a running rtl_tcp.
- maintains:
    self.usb_devices -> list of {index, description}
    self.tcp_servers -> dict port -> {'proc':Proc or None, 'device_index':int|None, 'status':str}
    self.receivers -> dict name -> SDRReceiver
"""

import asyncio
import logging
import socket
import shutil
import re
from typing import List, Dict, Optional

log = logging.getLogger("DeviceManager")

try:
    from rtlsdr import RtlSdr  # type: ignore
    _HAVE_PYRTLSDR = True
except Exception:
    _HAVE_PYRTLSDR = False

from neds_sdr.core.receiver import SDRReceiver  # noqa: E402


class DeviceManager:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.usb_devices: List[Dict] = []
        self.tcp_servers: Dict[int, Dict] = {}
        self.receivers: Dict[str, SDRReceiver] = {}
        self.tcp_scan_ports = list(range(1234, 1240))
        self._started_procs: Dict[int, asyncio.subprocess.Process] = {}

    # -------------------------------------------------------------------------
    # USB Detection
    # -------------------------------------------------------------------------
    def detect_sdr_devices(self) -> List[Dict]:
        devices = []
        if _HAVE_PYRTLSDR:
            try:
                serials = RtlSdr.get_device_serial_addresses()
                for idx, serial in enumerate(serials):
                    devices.append({"index": idx, "description": f"RTL-SDR (serial={serial})"})
                self.usb_devices = devices
                log.info("DeviceManager: Found %d device(s) via pyrtlsdr.", len(devices))
                return devices
            except Exception as e:
                log.warning("DeviceManager: pyrtlsdr detection failed: %s", e)

        rtl_test_path = shutil.which("rtl_test")
        if not rtl_test_path:
            log.warning("DeviceManager: rtl_test not found.")
            return []

        try:
            proc = asyncio.run(self._run_blocking_cmd([rtl_test_path, "-t"], timeout=6))
            out = proc.stdout or ""
            lines = out.splitlines()
            for line in lines:
                m = re.match(r"^(\d+):\s*(.+)$", line.strip())
                if m:
                    idx, desc = int(m.group(1)), m.group(2)
                    devices.append({"index": idx, "description": desc})
            self.usb_devices = devices
            log.info("DeviceManager: Detected %d SDR device(s).", len(devices))
        except Exception as e:
            log.error("DeviceManager: error while running rtl_test: %s", e)
        return devices

    async def _run_shell_cmd(self, argv: List[str], timeout: int = 6) -> asyncio.subprocess.Process:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        proc.stdout = stdout.decode(errors="ignore")
        proc.stderr = stderr.decode(errors="ignore")
        return proc

    def _run_blocking_cmd(self, argv: List[str], timeout: int = 6):
        async def _coro():
            return await self._run_shell_cmd(argv, timeout=timeout)
        return asyncio.run(_coro())

    # -------------------------------------------------------------------------
    # TCP Scanning
    # -------------------------------------------------------------------------
    def tcp_scan(self, ports: Optional[List[int]] = None, host: str = "127.0.0.1", timeout: float = 0.25) -> List[int]:
        if ports is None:
            ports = self.tcp_scan_ports
        open_ports = []
        for p in ports:
            try:
                with socket.create_connection((host, p), timeout=timeout) as s:
                    banner = ""
                    try:
                        s.settimeout(0.1)
                        banner = s.recv(128).decode(errors="ignore")
                    except Exception:
                        pass
                    if "rtl" in banner.lower() or banner == "":
                        open_ports.append(p)
                        if p not in self.tcp_servers:
                            self.tcp_servers[p] = {"proc": None, "device_index": None, "status": "found"}
            except Exception:
                continue
        log.info("DeviceManager: tcp_scan found %d open rtl_tcp port(s): %s", len(open_ports), open_ports)
        return open_ports

    # -------------------------------------------------------------------------
    # Start and Attach
    # -------------------------------------------------------------------------
    async def start_rtl_tcp(self, device_index: int, port: int):
        rtl_tcp_path = shutil.which("rtl_tcp")
        if not rtl_tcp_path:
            log.error("DeviceManager: rtl_tcp not found on PATH.")
            return None
        argv = [rtl_tcp_path, "-a", "127.0.0.1", "-p", str(port), "-d", str(device_index)]
        proc = await asyncio.create_subprocess_exec(*argv)
        await asyncio.sleep(0.3)
        self.tcp_servers[port] = {"proc": proc, "device_index": device_index, "status": "running"}
        log.info("DeviceManager: rtl_tcp started on port %d", port)
        return proc

    def attach_tcp(self, host: str, port: int, name: Optional[str] = None, gain: float = 30.0):
        hostname = host or "127.0.0.1"
        port = int(port)
        if not name:
            name = f"tcp_{hostname.replace('.', '_')}_{port}"
        if name in self.receivers:
            return self.receivers[name]
        try:
            receiver = SDRReceiver(name, hostname, port, gain, self.event_bus)
            self.receivers[name] = receiver
            log.info("DeviceManager: created receiver %s -> %s:%d", name, hostname, port)
            return receiver
        except Exception as e:
            log.error("DeviceManager.attach_tcp failed: %s", e)
            return None

    # -------------------------------------------------------------------------
    # UI Convenience / Compatibility
    # -------------------------------------------------------------------------
    @property
    def dongles(self):
        """Return a dict for UI (name -> SDRReceiver or device info)."""
        result = {}
        for name, recv in self.receivers.items():
            result[name] = recv
        for dev in self.usb_devices:
            name = f"usb_{dev['index']}"
            result[name] = {"index": dev["index"], "description": dev.get("description", ""), "type": "usb"}
        return result

    async def add_dongle(self, name: str, host: str, port: int, gain: float):
        """Add and attach new SDRReceiver by host:port."""
        if name in self.receivers:
            log.warning("DeviceManager.add_dongle: %s already exists", name)
            return self.receivers[name]
        recv = self.attach_tcp(host, port, name=name, gain=gain)
        if recv:
            await recv.connect()
            log.info("DeviceManager: Added dongle %s (%s:%d)", name, host, port)
        return recv

    async def set_gain(self, name: str, gain: float):
        """Set gain live for a receiver."""
        recv = self.receivers.get(name)
        if not recv:
            return
        recv.gain = gain
        try:
            await recv.client.set_gain(gain)
            log.info("[%s] gain -> %.1f dB", name, gain)
        except Exception as e:
            log.error("DeviceManager.set_gain error: %s", e)

    # -------------------------------------------------------------------------
    # Shutdown
    # -------------------------------------------------------------------------
    async def shutdown(self):
        """Cleanly shut down all receivers and processes."""
        for r in list(self.receivers.values()):
            try:
                await r.disconnect()
            except Exception:
                pass
        for dev_idx, proc in list(self._started_procs.items()):
            if proc and proc.returncode is None:
                proc.terminate()
                await proc.wait()
        self.receivers.clear()
        self.usb_devices.clear()
        self.tcp_servers.clear()
        log.info("DeviceManager: shutdown complete.")
