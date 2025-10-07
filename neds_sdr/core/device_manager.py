"""
device_manager.py

DeviceManager for runtime (live) SDR detection and TCP management.

Features:
- detect_sdr_devices(): discover attached RTL-SDR USB devices (pyrtlsdr preferred,
  fallback to rtl_test parsing).
- tcp_scan(): scan localhost ports for listening rtl_tcp servers.
- start_rtl_tcp(device_index, port): start rtl_tcp subprocess for a device index.
- attach_tcp(port, name): create and register an SDRReceiver attached to a running rtl_tcp.
- keeps simple internal maps:
    self.usb_devices -> list of {index, description}
    self.tcp_servers -> dict port -> {'proc':Proc or None, 'device_index':int|None, 'status':str}
    self.receivers -> dict name -> SDRReceiver (attached receivers)
"""

import asyncio
import logging
import socket
import shutil
import re
import os
from typing import List, Dict, Optional

log = logging.getLogger("DeviceManager")

# Try to import pyrtlsdr for Python native detection (optional).
try:
    from rtlsdr import RtlSdr  # type: ignore
    _HAVE_PYRTLSDR = True
except Exception:
    _HAVE_PYRTLSDR = False

# Import receiver lazily to avoid circular imports
from neds_sdr.core.receiver import SDRReceiver  # noqa: E402


class DeviceManager:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.usb_devices: List[Dict] = []
        self.tcp_servers: Dict[int, Dict] = {}
        self.receivers: Dict[str, SDRReceiver] = {}
        self.tcp_scan_ports = list(range(1234, 1237))
        self._started_procs: Dict[int, asyncio.subprocess.Process] = {}

    # -------------------------
    # USB Detection
    # -------------------------
    def detect_sdr_devices(self) -> List[Dict]:
        devices = []
        if _HAVE_PYRTLSDR:
            try:
                serials = RtlSdr.get_device_serial_addresses()
                for idx, serial in enumerate(serials):
                    desc = f"RTL-SDR (serial={serial})"
                    devices.append({"index": idx, "description": desc})
                log.info("DeviceManager: Found %d device(s) via pyrtlsdr.", len(devices))
                self.usb_devices = devices
                return devices
            except Exception as e:
                log.debug("DeviceManager: pyrtlsdr detection failed: %s", e)

        rtl_test_path = shutil.which("rtl_test")
        if not rtl_test_path:
            log.warning("DeviceManager: rtl_test not found on PATH and pyrtlsdr not available.")
            self.usb_devices = []
            return []

        try:
            proc = asyncio.run(self._run_blocking_cmd([rtl_test_path, "-t"], timeout=6))
            out = proc.stdout or ""
            lines = out.splitlines()
            dev_lines = [l.strip() for l in lines if re.match(r"^\s*\d+:\s+", l)]
            for line in dev_lines:
                m = re.match(r"^(\d+):\s*(.+)$", line.strip())
                if m:
                    idx = int(m.group(1))
                    desc = m.group(2).strip()
                    devices.append({"index": idx, "description": desc})
            log.info("DeviceManager: Detected %d SDR device(s).", len(devices))
            self.usb_devices = devices
            return devices
        except Exception as e:
            log.error("DeviceManager: error while running rtl_test: %s", e)
            self.usb_devices = []
            return []

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

    def _run_blocking_cmd(self, argv: List[str], timeout: int = 6) -> asyncio.subprocess.Process:
        async def _coro():
            p = await self._run_shell_cmd(argv, timeout=timeout)
            return p

        return asyncio.run(_coro())

    # -------------------------
    # TCP scanning
    # -------------------------
    def tcp_scan(self, ports: Optional[List[int]] = None, host: str = "127.0.0.1", timeout: float = 0.5) -> List[int]:
        if ports is None:
            ports = self.tcp_scan_ports
        open_ports = []
        for p in ports:
            is_open = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(timeout)
                    s.connect((host, p))
                    try:
                        banner = s.recv(128).decode(errors="ignore")
                        if "rtl" in banner.lower():
                            log.debug("DeviceManager: Found rtl_tcp banner on port %d", p)
                    except Exception:
                        pass
                    is_open = True
            except Exception:
                try:
                    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s6:
                        s6.settimeout(timeout)
                        s6.connect(("::1", p))
                        is_open = True
                except Exception:
                    pass
            if is_open:
                open_ports.append(p)
                if p not in self.tcp_servers:
                    self.tcp_servers[p] = {"proc": None, "device_index": None, "status": "found"}
        log.info("DeviceManager: tcp_scan found %d open rtl_tcp port(s): %s", len(open_ports), open_ports)
        return open_ports

    # -------------------------
    # Start rtl_tcp for a USB device
    # -------------------------
    async def start_rtl_tcp(self, device_index: int, port: int) -> Optional[asyncio.subprocess.Process]:
        rtl_tcp_path = shutil.which("rtl_tcp")
        if not rtl_tcp_path:
            log.error("DeviceManager: rtl_tcp binary not found on PATH.")
            return None

        try:
            dev_idx = int(device_index)
        except Exception:
            log.error("DeviceManager: invalid device index: %s", device_index)
            return None

        argv = [rtl_tcp_path, "-a", "127.0.0.1", "-p", str(port), "-d", str(dev_idx)]
        log.info("DeviceManager: launching rtl_tcp: %s", " ".join(argv))
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        self.tcp_servers[port] = {"proc": proc, "device_index": dev_idx, "status": "starting"}
        self._started_procs[dev_idx] = proc

        await asyncio.sleep(0.5)
        if proc.returncode is not None:
            stdout, stderr = await proc.communicate()
            log.error("DeviceManager: rtl_tcp exited early. stdout=%s stderr=%s", stdout, stderr)
            self.tcp_servers[port]["status"] = "exited"
            return None

        self.tcp_servers[port]["status"] = "running"
        log.info("DeviceManager: rtl_tcp launched on port %d (device %d).", port, dev_idx)
        return proc

    # -------------------------
    # Attach to an existing rtl_tcp server
    # -------------------------
    def attach_tcp(
        self,
        host: str,
        port: int,
        name: Optional[str] = None,
        gain: float = 29.7,
        auto_connect: bool = False,
    ) -> Optional[SDRReceiver]:
        """
        Attach a new SDRReceiver instance to a running rtl_tcp server.

        Args:
            host: hostname or IP of rtl_tcp server
            port: TCP port number
            name: optional receiver name; defaults to "tcp_<host>_<port>"
            gain: initial tuner gain (in dB)
            auto_connect: if True, automatically connect() the receiver

        Returns:
            SDRReceiver instance, or None on failure
        """
        hostname = host or "127.0.0.1"

        try:
            port = int(port)
        except Exception:
            log.error("DeviceManager.attach_tcp invalid port: %s", port)
            return None

        # default name if not provided
        if not name:
            name = f"tcp_{hostname.replace('.', '_')}_{port}"

        # prevent duplicate receiver names
        if name in self.receivers:
            log.warning("DeviceManager.attach_tcp: receiver name already exists: %s", name)
            return self.receivers[name]

        try:
            # Create a receiver (no hardcoding; fully dynamic)
            receiver = SDRReceiver(
                name=name,
                host=hostname,
                port=port,
                gain=gain,
                event_bus=self.event_bus,
            )

            # register it
            self.receivers[name] = receiver
            self.tcp_servers.setdefault(
                port, {"proc": None, "device_index": None, "status": "found"}
            )

            log.info("DeviceManager: created receiver %s -> %s:%d", name, hostname, port)

            # Notify UI or backend listeners
            self.event_bus.emit(
                "receiver_created",
                {"name": name, "host": hostname, "port": port, "gain": gain},
            )

            # Auto-connect if requested
            if auto_connect:
                async def _try_connect():
                    try:
                        await receiver.connect()
                        self.tcp_servers[port]["status"] = "connected"
                        self.event_bus.emit(
                            "receiver_connected",
                            {"name": name, "port": port},
                        )
                        log.info(
                            "DeviceManager: receiver %s connected to %s:%d",
                            name,
                            hostname,
                            port,
                        )

                        # also emit initial channel preset update to UI
                        self.event_bus.emit(
                            "channel_presets_updated",
                            {
                                "dongle": receiver.name,
                                "presets": receiver.presets.list_presets(),
                            },
                        )
                    except Exception as e:
                        log.error(
                            "DeviceManager: auto-connect failed for %s:%d: %s",
                            hostname,
                            port,
                            e,
                        )
                        self.tcp_servers[port]["status"] = "connect_failed"
                        self.event_bus.emit(
                            "receiver_connect_failed",
                            {"name": name, "port": port, "error": str(e)},
                        )

                try:
                    asyncio.get_event_loop().create_task(_try_connect())
                except RuntimeError:
                    log.warning(
                        "DeviceManager.attach_tcp: No running asyncio loop; cannot schedule auto_connect task."
                    )

            return receiver

        except Exception as e:
            log.error("DeviceManager.attach_tcp failed: %s", e)
            return None

    # -------------------------
    # UI / Runtime Accessors
    # -------------------------
    @property
    def dongles(self) -> Dict[str, "SDRReceiver"]:
        """Return only active SDRReceiver objects (for live tabs)."""
        return dict(self.receivers)

    @property
    def usb_devices_info(self) -> List[Dict]:
        """Return raw USB hardware info separately for startup UI."""
        return list(self.usb_devices)


    # -------------------------
    # UI Helper Methods
    # -------------------------
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

    async def retune_channel(self, dongle: str, channel: str, freq_mhz: float):
        """Retune a channel by dongle/channel name."""
        recv = self.receivers.get(dongle)
        if not recv:
            log.error("No receiver %s for retune", dongle)
            return
        ch = recv.channels.get(channel)
        if not ch:
            log.error("No channel %s on %s", channel, dongle)
            return
        await ch.set_frequency(freq_mhz * 1e6)
        log.info("Retuned %s/%s → %.4f MHz", dongle, channel, freq_mhz)



    # -------------------------
    # Shutdown helpers
    # -------------------------
    async def shutdown(self):
        for rname, r in list(self.receivers.items()):
            try:
                await r.disconnect()
            except Exception:
                pass

        for dev_idx, proc in list(self._started_procs.items()):
            try:
                if proc.returncode is None:
                    proc.terminate()
                    await proc.wait()
                    log.info("DeviceManager: terminated rtl_tcp for device %d", dev_idx)
            except Exception:
                pass

        self._started_procs.clear()
        self.tcp_servers.clear()
        self.usb_devices.clear()
        self.receivers.clear()
        log.info("DeviceManager: shutdown complete.")
