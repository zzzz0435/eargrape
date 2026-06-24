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

# Build single-file exe locally (requires .venv and PowerShell)
.\build.ps1
```

Pure-logic tests (config migration/validation, distortion clip math, A/B profile switching) live in `tests/` and run without audio hardware:

```powershell
python -m pip install -r requirements-dev.txt   # pytest
python -m pytest                                 # run all
python -m pytest tests/test_router.py -v         # one file
```

The audio stream path itself still needs real hardware for end-to-end testing.

Releases are not built locally for distribution: pushing a `v*` git tag (or running the `Build And Publish Release` workflow manually) builds `eargrape.spec` on `windows-latest` (Python 3.12) and uploads `Eargrape-<tag>-windows-x64.exe` to a GitHub Release. `dist/` is gitignored — never commit the exe. See `RELEASING.md`.

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

1. `AppConfig` (dataclass) holds shared stream settings plus two `EffectProfile`s — `profile_a` (released/normal) and `profile_b` (pressed/eargrape) — and `start_pressed` (which profile is live at startup). The hotkey **toggles between A and B**, it does not enable/disable a single effect.
2. `resolve_runtime(config)` → `ResolvedRuntime`: resolves device names/indices to `DeviceInfo` objects and determines WASAPI settings.
3. `EargrapeRouter` owns the PortAudio callback. `__init__` pre-computes a `_ProfileRuntime` for **both** A and B (drive, `1/tanh(drive)` normalizer, `needs_distort = mix > 0`, etc.). Each block it picks the active profile's runtime via `_effect_event`, downmixes to mono, optionally applies that profile's noise gate, runs distortion only if `needs_distort` (`soft_clip` = `tanh`-normalized, `hard_clip` = `np.clip`) and blends dry/wet by `mix` (or just applies `post_gain` when clean), then applies `mic_gain` and a final `np.clip` to ±1.0. The wet/out buffers are pre-allocated to `blocksize`, so changing blocksize requires a fresh router.
4. `EargrapeEngine` manages the stream lifecycle on a daemon thread (`EargrapeAudioThread`), registers the global hotkey (bound to `toggle_profile`) via the `keyboard` library, and calls a `StatusCallback(kind: str, message: str)` for status updates. `kind` is one of `engine` / `profile` / `audio` / `error` (the GUI adds `hotkey_captured` / `hotkey_capture_error`); the `profile` payload is the active profile's `name`.

### Compatibility fallback (important)

Devices vary, so a single resolved runtime is rarely used directly. `iter_runtime_candidates()` expands the base runtime into an **ordered list** of fallbacks: base → WASAPI extras disabled (prime off) → high latency → then re-resolve under `Windows DirectSound` and `MME`, each with a low-latency/high-latency variant. `select_compatible_runtime()` (used by `validate_runtime`/`validate()`) calls `probe_runtime_stream()` to actually open+close each candidate stream until one succeeds. At stream start, `EargrapeEngine._run_stream` walks the same candidate list and keeps the first stream that opens; the chosen candidate's `note` (e.g. "Compatibility mode: high latency") is surfaced in the `engine` status line. When everything fails, the raised error aggregates which host APIs were tried.

### Thread safety

The audio callback runs on a PortAudio thread. The A/B profile toggle uses a `threading.Event` (`EargrapeRouter._effect_event`; set = profile B active), **not** a Lock — `Event.is_set()` reads a plain bool without acquiring a lock, which is why it is preferred in the callback hot path (see the comment in `EargrapeRouter.__init__`). The `threading.Lock` lives on `EargrapeEngine` and guards lifecycle state (`running`, `router`, `runtime`). The GUI uses `queue.Queue` + `root.after(120, ...)` polling to relay `StatusCallback` events back to the Tkinter main thread — never update Tkinter widgets directly from the callback.

### Config file location

`runtime_base_dir()` handles both script mode (`Path(__file__).parent`) and PyInstaller frozen mode (resolves the real exe path via `GetModuleFileNameW`, prefers the directory that already contains `config.json`). Always use `default_config_path()` rather than hardcoding paths.

`config_from_dict()` accepts both the new nested format (`profile_a`/`profile_b`/`start_pressed`) and the legacy flat format (top-level `drive`/`distortion_mode`/`start_enabled`/…), auto-migrating the latter: legacy effect fields → `profile_b`, a clean `profile_a` that keeps the legacy `mic_gain`, and `start_enabled` → `start_pressed`. Missing `mic_gain` defaults to `1.0`. Saving always writes the new format.

### Device resolution

`resolve_device()` supports `null` (system default), integer index, or substring name match. Ambiguous substring matches raise `ConfigError`. Always use `filter_devices()` + `resolve_device()` rather than calling `sd.query_devices()` directly.

`validate_device_route()` rejects configs where input and output are the two ends of the *same* VB-CABLE (matched via `vb_route_signature()`), which would feed the cable back into itself. Preserve this guard when touching device resolution.

## Key constraints

- The audio callback (`EargrapeRouter.callback`) must never block or allocate. Only numpy operations are safe there.
- Input stream is always mono (`channels=1`). Output can be 1 or 2 channels depending on the device.
- Both devices should use the same host API (ideally WASAPI) to avoid resampling and reduce latency.
- `blocksize=128` is the default. Lower values reduce latency but increase dropout risk. `256` is the safe fallback.
- `exclusive_wasapi=True` can reduce latency but prevents other apps from using the device simultaneously.
- `EargrapeAudioThread` raises itself to `THREAD_PRIORITY_TIME_CRITICAL` on Windows (best-effort, failures ignored) — keep stream open/close on that thread, not the GUI/main thread.
- `config.json` is read via `dict.get()` with `DEFAULT_CONFIG_DATA` fallbacks, so a missing key (the checked-in `config.json` omits `mic_gain`) is not an error; don't assume every key is present on disk.
