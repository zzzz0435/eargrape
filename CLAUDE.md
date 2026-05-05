# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Eargrape is a Windows microphone router: capture mic → apply distortion → route to a virtual cable device (e.g. VB-CABLE). The virtual cable's output is then set as the microphone in Discord or a game. A global hotkey toggles the distortion effect on/off.

## Commands

```powershell
# Install dependencies
python -m pip install -r requirements.txt

# Run the GUI (primary entry point)
python eargrape_gui.py

# CLI: list audio devices
python eargrape.py --list-devices

# CLI: validate config without starting the stream
python eargrape.py --validate-config

# CLI: start the router (Ctrl+C to stop)
python eargrape.py

# Build single-file exe (requires .venv and PowerShell)
.\build.ps1
```

No test suite exists. The machine used for development has no input-capable audio device, so end-to-end testing requires real hardware.

## Architecture

All business logic lives in **`eargrape_core.py`**. The other two files are thin entry points.

```
eargrape_core.py      ← config, device resolution, audio engine, distortion
eargrape_gui.py       ← Tkinter GUI wrapping EargrapeEngine
eargrape.py           ← CLI wrapping EargrapeEngine
config.json           ← user settings (auto-created on first run)
eargrape.spec         ← PyInstaller build spec (entry point: eargrape_gui.py)
build.ps1             ← calls PyInstaller via .venv/Scripts/python.exe
```

### Core data flow

1. `AppConfig` (dataclass) holds all user settings.
2. `resolve_runtime(config)` → `ResolvedRuntime`: resolves device names/indices to `DeviceInfo` objects and determines WASAPI settings.
3. `EargrapeRouter` owns the PortAudio callback. It reads mono input, optionally applies noise gate, applies distortion (`soft_clip` = `tanh`, `hard_clip` = `np.clip`), and writes to `outdata`. Thread-safe toggle via `threading.Lock`.
4. `EargrapeEngine` manages the stream lifecycle on a daemon thread (`EargrapeAudioThread`), registers the global hotkey via the `keyboard` library, and calls a `StatusCallback(kind: str, message: str)` for status updates.

### Thread safety

The audio callback runs on a PortAudio thread. `EargrapeRouter.effect_enabled` is guarded by a lock. The GUI uses `queue.Queue` + `root.after(120, ...)` polling to relay `StatusCallback` events back to the Tkinter main thread — never update Tkinter widgets directly from the callback.

### Config file location

`runtime_base_dir()` handles both script mode (`Path(__file__).parent`) and PyInstaller frozen mode (resolves the real exe path via `GetModuleFileNameW`, prefers the directory that already contains `config.json`). Always use `default_config_path()` rather than hardcoding paths.

### Device resolution

`resolve_device()` supports `null` (system default), integer index, or substring name match. Ambiguous substring matches raise `ConfigError`. Always use `filter_devices()` + `resolve_device()` rather than calling `sd.query_devices()` directly.

## Key constraints

- The audio callback (`EargrapeRouter.callback`) must never block or allocate. Only numpy operations are safe there.
- Input stream is always mono (`channels=1`). Output can be 1 or 2 channels depending on the device.
- Both devices should use the same host API (ideally WASAPI) to avoid resampling and reduce latency.
- `blocksize=128` is the default. Lower values reduce latency but increase dropout risk. `256` is the safe fallback.
- `exclusive_wasapi=True` can reduce latency but prevents other apps from using the device simultaneously.
