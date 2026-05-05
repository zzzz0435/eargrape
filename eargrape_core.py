from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import keyboard
import numpy as np
import sounddevice as sd


StatusCallback = Callable[[str, str], None]

DEFAULT_CONFIG_DATA: dict[str, Any] = {
    "input_device": None,
    "output_device": "CABLE Input",
    "hostapi": "Windows WASAPI",
    "samplerate": 48000,
    "blocksize": 128,
    "latency": "low",
    "exclusive_wasapi": False,
    "hotkey": "f8",
    "start_enabled": False,
    "distortion_mode": "soft_clip",
    "drive": 18.0,
    "post_gain": 0.32,
    "mix": 1.0,
    "noise_gate": 0.0,
}


class ConfigError(RuntimeError):
    pass


@dataclass(slots=True)
class DeviceInfo:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float

    @property
    def can_input(self) -> bool:
        return self.max_input_channels > 0

    @property
    def can_output(self) -> bool:
        return self.max_output_channels > 0


@dataclass(slots=True)
class AppConfig:
    input_device: str | int | None
    output_device: str | int | None
    hostapi: str | None
    samplerate: int
    blocksize: int
    latency: str | float
    exclusive_wasapi: bool
    hotkey: str
    start_enabled: bool
    distortion_mode: str
    drive: float
    post_gain: float
    mix: float
    noise_gate: float


@dataclass(slots=True)
class ResolvedRuntime:
    input_device: DeviceInfo
    output_device: DeviceInfo
    output_channels: int
    extra_settings: tuple[Any, Any] | None


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        current_dir = Path.cwd().resolve()
        exe_dir: Path | None = None

        if sys.platform == "win32":
            try:
                import ctypes

                buffer = ctypes.create_unicode_buffer(32768)
                result = ctypes.windll.kernel32.GetModuleFileNameW(None, buffer, len(buffer))
                if result:
                    exe_dir = Path(buffer.value).resolve().parent
            except Exception:
                pass

        if exe_dir is None:
            launcher = (
                Path(sys.argv[0]).resolve()
                if sys.argv and sys.argv[0]
                else Path(sys.executable).resolve()
            )
            exe_dir = launcher.parent

        debug_path = os.environ.get("EARGRAPE_DEBUG_PATH")
        if debug_path:
            Path(debug_path).write_text(
                "\n".join(
                    [
                        f"cwd={current_dir}",
                        f"sys.argv0={sys.argv[0] if sys.argv else ''}",
                        f"sys.executable={sys.executable}",
                        f"exe_dir={exe_dir}",
                    ]
                ),
                encoding="utf-8",
            )

        if (current_dir / "config.json").exists():
            return current_dir
        if (exe_dir / "config.json").exists():
            return exe_dir
        if current_dir != exe_dir:
            return current_dir
        return exe_dir
    return Path(__file__).resolve().parent


def default_config_path() -> Path:
    return runtime_base_dir() / "config.json"


def default_config_data() -> dict[str, Any]:
    return dict(DEFAULT_CONFIG_DATA)


def create_default_config() -> AppConfig:
    return config_from_dict(default_config_data())


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    config = AppConfig(
        input_device=data.get("input_device"),
        output_device=data.get("output_device", DEFAULT_CONFIG_DATA["output_device"]),
        hostapi=data.get("hostapi", DEFAULT_CONFIG_DATA["hostapi"]),
        samplerate=int(data.get("samplerate", DEFAULT_CONFIG_DATA["samplerate"])),
        blocksize=int(data.get("blocksize", DEFAULT_CONFIG_DATA["blocksize"])),
        latency=data.get("latency", DEFAULT_CONFIG_DATA["latency"]),
        exclusive_wasapi=bool(
            data.get("exclusive_wasapi", DEFAULT_CONFIG_DATA["exclusive_wasapi"])
        ),
        hotkey=str(data.get("hotkey", DEFAULT_CONFIG_DATA["hotkey"])),
        start_enabled=bool(
            data.get("start_enabled", DEFAULT_CONFIG_DATA["start_enabled"])
        ),
        distortion_mode=str(
            data.get("distortion_mode", DEFAULT_CONFIG_DATA["distortion_mode"])
        )
        .strip()
        .lower(),
        drive=float(data.get("drive", DEFAULT_CONFIG_DATA["drive"])),
        post_gain=float(data.get("post_gain", DEFAULT_CONFIG_DATA["post_gain"])),
        mix=float(data.get("mix", DEFAULT_CONFIG_DATA["mix"])),
        noise_gate=float(data.get("noise_gate", DEFAULT_CONFIG_DATA["noise_gate"])),
    )
    validate_config(config)
    return config


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return asdict(config)


def ensure_config_exists(path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    if not config_path.exists():
        config_path.write_text(
            json.dumps(default_config_data(), indent=2),
            encoding="utf-8",
        )
    return config_path


def load_config(path: Path | None = None) -> AppConfig:
    config_path = ensure_config_exists(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return config_from_dict(data)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    validate_config(config)
    config_path = path or default_config_path()
    config_path.write_text(
        json.dumps(config_to_dict(config), indent=2),
        encoding="utf-8",
    )
    return config_path


def validate_config(config: AppConfig) -> None:
    if config.blocksize <= 0:
        raise ConfigError("blocksize must be greater than 0")
    if config.samplerate <= 0:
        raise ConfigError("samplerate must be greater than 0")
    if config.distortion_mode not in {"soft_clip", "hard_clip"}:
        raise ConfigError("distortion_mode must be 'soft_clip' or 'hard_clip'")
    if config.drive <= 0:
        raise ConfigError("drive must be greater than 0")
    if config.post_gain <= 0:
        raise ConfigError("post_gain must be greater than 0")
    if not 0.0 <= config.mix <= 1.0:
        raise ConfigError("mix must be between 0.0 and 1.0")
    if config.noise_gate < 0.0:
        raise ConfigError("noise_gate must be greater than or equal to 0.0")
    if not config.hotkey.strip():
        raise ConfigError("hotkey cannot be empty")
    for key, value in {
        "input_device": config.input_device,
        "output_device": config.output_device,
    }.items():
        if value is not None and not isinstance(value, (str, int)):
            raise ConfigError(f"{key} must be null, a string, or an integer index")


def enumerate_devices() -> list[DeviceInfo]:
    hostapis = sd.query_hostapis()
    devices = sd.query_devices()
    resolved: list[DeviceInfo] = []

    for index, device in enumerate(devices):
        hostapi_name = hostapis[device["hostapi"]]["name"]
        resolved.append(
            DeviceInfo(
                index=index,
                name=str(device["name"]),
                hostapi=hostapi_name,
                max_input_channels=int(device["max_input_channels"]),
                max_output_channels=int(device["max_output_channels"]),
                default_samplerate=float(device["default_samplerate"]),
            )
        )

    return resolved


def available_hostapis(devices: list[DeviceInfo] | None = None) -> list[str]:
    resolved_devices = devices or enumerate_devices()
    return sorted({device.hostapi for device in resolved_devices})


def filter_devices(
    devices: list[DeviceInfo],
    direction: str,
    hostapi: str | None,
) -> list[DeviceInfo]:
    capability = "can_input" if direction == "input" else "can_output"
    return [
        device
        for device in devices
        if getattr(device, capability) and hostapi_matches(device, hostapi)
    ]


def default_device_index(direction: str) -> int | None:
    defaults = sd.default.device
    if defaults is None:
        return None

    index = defaults[0] if direction == "input" else defaults[1]
    if index is None:
        return None

    index = int(index)
    return index if index >= 0 else None


def hostapi_matches(device: DeviceInfo, wanted: str | None) -> bool:
    if not wanted:
        return True
    return wanted.casefold() in device.hostapi.casefold()


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def resolve_device(
    spec: str | int | None,
    direction: str,
    hostapi: str | None,
    devices: list[DeviceInfo],
) -> DeviceInfo:
    candidates = filter_devices(devices, direction, hostapi)
    if not candidates:
        raise ConfigError(
            f"No {direction} device supports host API filter: {hostapi or 'any'}"
        )

    if spec is None:
        default_index = default_device_index(direction)
        if default_index is not None:
            for candidate in candidates:
                if candidate.index == default_index:
                    return candidate

            default_name = next(
                (device.name for device in devices if device.index == default_index),
                None,
            )
            if default_name is not None:
                default_name_normalized = normalize_text(default_name)
                for candidate in candidates:
                    if normalize_text(candidate.name) == default_name_normalized:
                        return candidate

        return candidates[0]

    if isinstance(spec, int) or (isinstance(spec, str) and spec.strip().isdigit()):
        wanted_index = int(spec)
        for candidate in candidates:
            if candidate.index == wanted_index:
                return candidate
        raise ConfigError(
            f"Configured {direction}_device index {wanted_index} was not found in host API {hostapi or 'any'}"
        )

    token = normalize_text(str(spec))
    exact = [device for device in candidates if normalize_text(device.name) == token]
    if len(exact) == 1:
        return exact[0]

    matches = [device for device in candidates if token in normalize_text(device.name)]
    if len(matches) == 1:
        return matches[0]

    if not matches:
        raise ConfigError(
            f"No {direction} device matched '{spec}' under host API {hostapi or 'any'}"
        )

    options = ", ".join(f"[{device.index}] {device.name}" for device in matches)
    raise ConfigError(f"Ambiguous {direction} device '{spec}'. Matches: {options}")


def choose_output_channels(device: DeviceInfo) -> int:
    if device.max_output_channels >= 2:
        return 2
    if device.max_output_channels >= 1:
        return 1
    raise ConfigError(f"Output device has no output channels: {device.name}")


def wasapi_settings_for(
    config: AppConfig,
    input_device: DeviceInfo,
    output_device: DeviceInfo,
) -> tuple[Any, Any] | None:
    if "wasapi" not in input_device.hostapi.casefold():
        return None
    if "wasapi" not in output_device.hostapi.casefold():
        return None

    return (
        sd.WasapiSettings(
            exclusive=config.exclusive_wasapi,
            auto_convert=not config.exclusive_wasapi,
        ),
        sd.WasapiSettings(
            exclusive=config.exclusive_wasapi,
            auto_convert=not config.exclusive_wasapi,
        ),
    )


def resolve_runtime(config: AppConfig, devices: list[DeviceInfo] | None = None) -> ResolvedRuntime:
    resolved_devices = devices or enumerate_devices()
    input_device = resolve_device(
        config.input_device,
        "input",
        config.hostapi,
        resolved_devices,
    )
    output_device = resolve_device(
        config.output_device,
        "output",
        config.hostapi,
        resolved_devices,
    )
    output_channels = choose_output_channels(output_device)
    extra_settings = wasapi_settings_for(config, input_device, output_device)
    return ResolvedRuntime(
        input_device=input_device,
        output_device=output_device,
        output_channels=output_channels,
        extra_settings=extra_settings,
    )


def validate_runtime(config: AppConfig, runtime: ResolvedRuntime | None = None) -> ResolvedRuntime:
    resolved_runtime = runtime or resolve_runtime(config)
    sd.check_input_settings(
        device=resolved_runtime.input_device.index,
        channels=1,
        dtype="float32",
        extra_settings=(
            resolved_runtime.extra_settings[0] if resolved_runtime.extra_settings else None
        ),
        samplerate=config.samplerate,
    )
    sd.check_output_settings(
        device=resolved_runtime.output_device.index,
        channels=resolved_runtime.output_channels,
        dtype="float32",
        extra_settings=(
            resolved_runtime.extra_settings[1] if resolved_runtime.extra_settings else None
        ),
        samplerate=config.samplerate,
    )
    return resolved_runtime


def device_display_label(device: DeviceInfo) -> str:
    return f"[{device.index}] {device.name}"


def list_devices_text() -> str:
    devices = enumerate_devices()
    default_input = default_device_index("input")
    default_output = default_device_index("output")

    if not devices:
        return "No audio devices were found."

    lines = [
        "Index  Dir  Host API            Name",
        "-----  ---  ------------------  ----",
    ]
    for device in devices:
        directions = []
        if device.can_input:
            directions.append("I")
        if device.can_output:
            directions.append("O")

        markers = []
        if device.index == default_input:
            markers.append("default-in")
        if device.index == default_output:
            markers.append("default-out")

        suffix = f" [{', '.join(markers)}]" if markers else ""
        lines.append(
            f"{device.index:>5}  {''.join(directions):<3}  "
            f"{device.hostapi[:18]:<18}  {device.name}{suffix}"
        )
    return "\n".join(lines)


class EargrapeRouter:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.effect_enabled = config.start_enabled
        self.lock = threading.Lock()
        self.last_status: str | None = None
        self.soft_clip_normalizer = 1.0 / np.tanh(config.drive)

    def toggle(self) -> bool:
        with self.lock:
            self.effect_enabled = not self.effect_enabled
            return self.effect_enabled

    def is_enabled(self) -> bool:
        with self.lock:
            return self.effect_enabled

    def callback(
        self,
        indata: np.ndarray,
        outdata: np.ndarray,
        frames: int,
        time: Any,
        status: sd.CallbackFlags,
    ) -> None:
        del frames, time

        if status:
            self.last_status = str(status)

        if indata.shape[1] == 1:
            mono = indata[:, 0]
        else:
            mono = np.mean(indata, axis=1, dtype=np.float32)

        if self.config.noise_gate > 0.0:
            mono = mono.copy()
            mono[np.abs(mono) < self.config.noise_gate] = 0.0

        if self.is_enabled():
            wet = self.apply_distortion(mono)
            processed = (mono * (1.0 - self.config.mix)) + (wet * self.config.mix)
            processed = np.clip(processed * self.config.post_gain, -1.0, 1.0)
        else:
            processed = np.clip(mono, -1.0, 1.0)

        outdata[:] = processed[:, None]

    def apply_distortion(self, mono: np.ndarray) -> np.ndarray:
        driven = mono * self.config.drive
        if self.config.distortion_mode == "hard_clip":
            return np.clip(driven, -1.0, 1.0)
        return np.tanh(driven) * self.soft_clip_normalizer


class EargrapeEngine:
    def __init__(
        self,
        config: AppConfig,
        status_callback: StatusCallback | None = None,
    ) -> None:
        self.config = config
        self.status_callback = status_callback
        self.lock = threading.Lock()
        self.router: EargrapeRouter | None = None
        self.runtime: ResolvedRuntime | None = None
        self.stream_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.startup_event = threading.Event()
        self.startup_error: Exception | None = None
        self.hotkey_handle: int | None = None
        self.running = False

    def _emit(self, kind: str, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(kind, message)

    def is_running(self) -> bool:
        with self.lock:
            return self.running

    def is_effect_enabled(self) -> bool:
        with self.lock:
            if self.router is None:
                return self.config.start_enabled
            return self.router.is_enabled()

    def toggle_effect(self) -> bool:
        with self.lock:
            if self.router is None:
                raise RuntimeError("Engine is not running.")
            enabled = self.router.toggle()
        self._emit("effect", "ON" if enabled else "OFF")
        return enabled

    def validate(self) -> ResolvedRuntime:
        runtime = resolve_runtime(self.config)
        return validate_runtime(self.config, runtime)

    def start(self) -> None:
        if self.is_running():
            return

        self.runtime = self.validate()
        self.router = EargrapeRouter(self.config)
        self.startup_event.clear()
        self.startup_error = None
        self.stop_event.clear()

        try:
            self.hotkey_handle = keyboard.add_hotkey(
                self.config.hotkey,
                self.toggle_effect,
                suppress=False,
            )
        except Exception:
            self.hotkey_handle = None
            raise

        self.stream_thread = threading.Thread(
            target=self._run_stream,
            name="EargrapeAudioThread",
            daemon=True,
        )
        self.stream_thread.start()

        if not self.startup_event.wait(5.0):
            self.stop()
            raise RuntimeError("Timed out while starting the audio stream.")

        if self.startup_error is not None:
            error = self.startup_error
            self.stop()
            raise error

    def _run_stream(self) -> None:
        runtime = self.runtime
        router = self.router
        if runtime is None or router is None:
            self.startup_error = RuntimeError("Audio runtime was not prepared.")
            self.startup_event.set()
            return

        try:
            with sd.Stream(
                samplerate=self.config.samplerate,
                blocksize=self.config.blocksize,
                device=(runtime.input_device.index, runtime.output_device.index),
                channels=(1, runtime.output_channels),
                dtype=("float32", "float32"),
                latency=self.config.latency,
                extra_settings=runtime.extra_settings,
                callback=router.callback,
                clip_off=True,
                dither_off=True,
                never_drop_input=True,
                prime_output_buffers_using_stream_callback=True,
            ):
                with self.lock:
                    self.running = True
                self._emit(
                    "engine",
                    (
                        f"Running | hotkey={self.config.hotkey} | "
                        f"input=[{runtime.input_device.index}] {runtime.input_device.name} | "
                        f"output=[{runtime.output_device.index}] {runtime.output_device.name}"
                    ),
                )
                self._emit("effect", "ON" if router.is_enabled() else "OFF")
                self.startup_event.set()

                while not self.stop_event.wait(0.25):
                    if router.last_status:
                        self._emit("audio", router.last_status)
                        router.last_status = None
        except Exception as exc:
            self.startup_error = exc
            if not self.startup_event.is_set():
                self.startup_event.set()
            self._emit("error", str(exc))
        finally:
            with self.lock:
                self.running = False
            self._emit("engine", "Stopped")

    def stop(self) -> None:
        self.stop_event.set()
        if self.hotkey_handle is not None:
            keyboard.remove_hotkey(self.hotkey_handle)
            self.hotkey_handle = None

        if self.stream_thread is not None:
            self.stream_thread.join(timeout=2.0)
            self.stream_thread = None

        with self.lock:
            self.running = False
            self.router = None
            self.runtime = None
