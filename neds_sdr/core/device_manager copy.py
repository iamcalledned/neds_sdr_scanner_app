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

# Import receiver lazily to avoid circular imports in some run paths
from neds_sdr.core.receiver import SDRReceiver  # noqa: E402


class DeviceManager:
    def __init__(self, event_bus):
        self.event_bus = event_bus

        # usb_devices: list of dicts: {'index': int, 'description': str}
        self.usb_devices: List[Dict] = []

        # tcp_servers: map port -> dict {proc: Process|None, device_index: Optional[int], status: str}
        # If we started the server ourselves, proc is the process handle and device_index is the hardware index.
        # If the server was found via tcp_scan, proc is None and device_index may be None (unknown).
        self.tcp_servers: Dict[int, Dict] = {}

        # receivers: active SDRReceiver objects created by 'attach_tcp' or 'create_receiver'
        self.receivers: Dict[str, SDRReceiver] = {}

        # default tcp scan port range (inclusive)
        self.tcp_scan_ports = list(range(1234, 1237))

        # process bookkeeping: map device_index -> process handle (if started by us)
        self._started_procs: Dict[int, asyncio.subprocess.Process] = {}

    # -------------------------
    # USB Detection
    # -------------------------
    def detect_sdr_devices(self) -> List[Dict]:
        """
        Return a list of attached RTL-SDR devices as dicts:
            [{'index': 0, 'description': 'RTL-SDR Blog V4 ...'}, ...]
        Tries pyrtlsdr first, falls back to parsing `rtl_test -t` output.
        """
        devices = []
        # Option A: pyrtlsdr
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

        # Option B: rtl_test -t fallback
        rtl_test_path = shutil.which("rtl_test")
        if not rtl_test_path:
            log.warning("DeviceManager: rtl_test not found on PATH and pyrtlsdr not available.")
            self.usb_devices = []
            return []

        try:
            proc = asyncio.run(self._run_blocking_cmd([rtl_test_path, "-t"], timeout=6))
            out = proc.stdout or ""
            # parse "Found N device(s):" and each device line that contains index and description
            # rtl_test's output varies; attempt to extract indices and descriptions robustly.
            # Example lines:
            #   Found 1 device(s):
            #     0:  Realtek, RTL2838UHIDIR, SN: 00000001
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
        """Async helper to run a subprocess and return the Process handle (with stdout/stderr pipes)."""
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        # Attach decoded output to proc attributes for synchronous fallback compatibility
        proc.stdout = stdout.decode(errors="ignore") if isinstance(stdout, bytes) else str(stdout)
        proc.stderr = stderr.decode(errors="ignore") if isinstance(stderr, bytes) else str(stderr)
        return proc

    def _run_blocking_cmd(self, argv: List[str], timeout: int = 6) -> asyncio.subprocess.Process:
        """
        Blocking wrapper using asyncio.run for simple commands from sync code paths.
        Returns a dummy Process-like object with .stdout and .stderr (decoded strings).
        """
        # small wrapper to call the async routine
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
        """
        Start rtl_tcp for the given device index on the given port.
        Returns the Process handle on success, or None on failure.
        """
        rtl_tcp_path = shutil.which("rtl_tcp")
        if not rtl_tcp_path:
            log.error("DeviceManager: rtl_tcp binary not found on PATH.")
            return None

        # Make sure device_index is a valid int
        try:
            dev_idx = int(device_index)
        except Exception:
            log.error("DeviceManager: invalid device index: %s", device_index)
            return None

        # Launch rtl_tcp as an async subprocess
        argv = [rtl_tcp_path, "-a", "127.0.0.1", "-p", str(port), "-d", str(dev_idx)]
        log.info("DeviceManager: launching rtl_tcp: %s", " ".join(argv))
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # store bookkeeping (proc may not be immediately ready to accept connections)
        self.tcp_servers[port] = {"proc": proc, "device_index": dev_idx, "status": "starting"}
        self._started_procs[dev_idx] = proc

        # wait briefly and check if the process is still running
        await asyncio.sleep(0.5)
        if proc.returncode is not None:
            # process finished quickly (error)
            stdout, stderr = await proc.communicate()
            log.error("DeviceManager: rtl_tcp exited early. stdout=%s stderr=%s", stdout, stderr)
            self.tcp_servers[port]["status"] = "exited"
            return None

        # mark running; higher-level UI will probe port to ensure connectivity
        self.tcp_servers[port]["status"] = "running"
        log.info("DeviceManager: rtl_tcp launched on port %d (device %d).", port, dev_idx)
        return proc

    # -------------------------
    # Attach to an existing rtl_tcp server (create receiver)
    # -------------------------
    def attach_tcp(self, host: str, port: int, name: Optional[str] = None, gain: float = 30.0) -> Optional[SDRReceiver]:
        """
        Attach a new SDRReceiver to an existing rtl_tcp server at host:port.
        Registers the receiver in self.receivers with the provided or autogenerated name.
        Returns the SDRReceiver instance or None on failure.
        """
        hostname = host or "127.0.0.1"
        try:
            port = int(port)
        except Exception:
            log.error("DeviceManager.attach_tcp invalid port: %s", port)
            return None

        # name generation
        if not name:
            name = f"tcp_{hostname.replace('.', '_')}_{port}"

        if name in self.receivers:
            log.warning("DeviceManager.attach_tcp: receiver name already exists: %s", name)
            return self.receivers[name]

        try:
            receiver = SDRReceiver(name=name, host=hostname, port=port, gain=gain, event_bus=self.event_bus)
            # do not call connect here (async) — caller should call connect() (UI will)
            self.receivers[name] = receiver
            log.info("DeviceManager: created receiver placeholder %s -> %s:%d", name, hostname, port)
            return receiver
        except Exception as e:
            log.error("DeviceManager.attach_tcp failed: %s", e)
            return None

    # -------------------------
    # Shutdown helpers
    # -------------------------
    async def shutdown(self):
        """Shutdown any started rtl_tcp processes and disconnect receivers."""
        # First stop receivers
        for rname, r in list(self.receivers.items()):
            try:
                await r.disconnect()
            except Exception:
                pass

        # Kill processes we started
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
