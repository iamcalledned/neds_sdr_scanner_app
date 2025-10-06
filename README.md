# 🚨 Neds SDR Control System

**A full-featured Python SDR controller and runtime management tool**  
for multi-dongle, multi-channel radio monitoring systems.

This application both **configures and runs** your SDR environment.  
It replaces sdr++ and external scripts with a unified control system that manages
`rtl_tcp` receivers, audio routing, squelch/tone logic, and backend services.

---

## ⚙️ Key Features

- 🎛️ **Multi-Dongle Control**
  - Connect to any number of `rtl_tcp` servers
  - Start, stop, and configure live receivers
  - Assign logical names and save configs automatically

- 📡 **Multi-Channel Per Dongle**
  - Each dongle can host multiple tuned channels
  - Independent squelch, tone, and audio routing per channel

- 🔊 **Signal + Tone Squelch**
  - Power-based squelch with hysteresis
  - PL (CTCSS) and DPL (DCS) tone decoding via Goertzel filters

- 🎧 **PulseAudio Sink Routing**
  - Check, create, and manage sinks automatically
  - Sends audio only when squelch is open (no static)
  - Recorder integration unchanged

- 🧠 **Config + Runtime in One App**
  - Tabbed Python UI (PyQt/Textual) for full control
  - Adjust frequency, gain, tone, or squelch live
  - Immediate runtime reconfiguration — no restart required

- 🔌 **API Ready**
  - Built-in FastAPI REST + WebSocket server
  - Your existing PWA can subscribe to events and control it remotely

- 🧾 **Persistent Configuration**
  - All dongle, channel, and sink settings saved to `config.yaml`
  - Auto-saves after any change, reloads cleanly at startup

---

## 🧰 Tech Stack

| Component | Technology |
|------------|-------------|
| SDR I/O | `rtl_tcp` protocol (client mode only) |
| DSP | `numpy`, `scipy.signal` |
| Audio | `sounddevice`, `pulsectl`, `pyaudio` |
| Backend | Python 3.11+, `asyncio`, `FastAPI` |
| UI | `PyQt6` (desktop) or `Textual` (terminal) |
| Config | YAML (`ruamel.yaml`), `.env` via `python-dotenv` |
| Logging | `structlog`, rotating file logs |
| OS | Ubuntu Linux |

---

## 🗂️ Repository Structure

