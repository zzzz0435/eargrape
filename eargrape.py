from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from eargrape_core import (
    ConfigError,
    EargrapeEngine,
    default_config_path,
    list_devices_text,
    load_config,
    resolve_runtime,
    validate_runtime,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Low-latency hotkey-triggered microphone distortion router."
    )
    parser.add_argument(
        "--config",
        default=str(default_config_path()),
        help="Path to config.json",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio devices and exit",
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Resolve devices and validate audio settings without starting the stream",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()

    if args.list_devices:
        print(list_devices_text())
        return 0

    config = load_config(Path(args.config).resolve())
    runtime = resolve_runtime(config)
    validate_runtime(config, runtime)

    if args.validate_config:
        print("Config validation succeeded.")
        print(
            f"Input:  [{runtime.input_device.index}] {runtime.input_device.name} ({runtime.input_device.hostapi})"
        )
        print(
            f"Output: [{runtime.output_device.index}] {runtime.output_device.name} ({runtime.output_device.hostapi})"
        )
        print(f"Sample rate: {config.samplerate}")
        print(f"Block size:  {config.blocksize}")
        return 0

    stop_event = threading.Event()

    def handle_status(kind: str, message: str) -> None:
        if kind == "error":
            print(f"[ERROR] {message}", file=sys.stderr)
        elif kind == "effect":
            print(f"[HOTKEY] distortion {message}")
        elif kind == "audio":
            print(f"[AUDIO] {message}")
        else:
            print(f"[{kind.upper()}] {message}")

    def stop_handler(signum: int, frame: object) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGINT, stop_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_handler)

    engine = EargrapeEngine(config, handle_status)
    engine.start()
    print("Press Ctrl+C to stop.")

    try:
        while not stop_event.wait(0.25):
            pass
    finally:
        engine.stop()

    return 0


def main() -> int:
    try:
        return run()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
