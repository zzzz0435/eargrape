from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk

from eargrape_core import (
    AppConfig,
    DeviceInfo,
    EargrapeEngine,
    available_hostapis,
    config_to_dict,
    create_default_config,
    default_config_path,
    device_display_label,
    enumerate_devices,
    filter_devices,
    load_config,
    save_config,
    validate_runtime,
)


class EargrapeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Eargrape")
        self.root.geometry("560x420")
        self.root.minsize(560, 420)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.config_path = default_config_path()
        self.message_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.engine: EargrapeEngine | None = None
        self.devices: list[DeviceInfo] = []
        self.input_device_map: dict[str, int] = {}
        self.output_device_map: dict[str, int] = {}
        self.preferred_input_spec: str | int | None = None
        self.preferred_output_spec: str | int | None = None

        self.status_var = tk.StringVar(value="Idle")
        self.effect_var = tk.StringVar(value="OFF")
        self.hotkey_status_var = tk.StringVar(value="-")

        self.hostapi_var = tk.StringVar()
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.hotkey_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.blocksize_var = tk.StringVar()
        self.drive_var = tk.DoubleVar()
        self.post_gain_var = tk.DoubleVar()
        self.start_enabled_var = tk.BooleanVar()

        self.build_ui()
        self.load_initial_config()
        self.refresh_devices(preserve_selection=False)
        self.root.after(120, self.process_messages)

    def build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)

        title = ttk.Label(
            container,
            text="Eargrape",
            font=("Segoe UI", 15, "bold"),
        )
        title.grid(row=0, column=0, columnspan=3, sticky="w")

        hint = ttk.Label(
            container,
            text="Mic -> Eargrape -> VB-CABLE -> Discord / game",
        )
        hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 14))

        row = 2
        self._add_label(container, row, "Input mic")
        self.input_combo = ttk.Combobox(
            container,
            textvariable=self.input_var,
            state="readonly",
        )
        self.input_combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)

        row += 1
        self._add_label(container, row, "Output target")
        self.output_combo = ttk.Combobox(
            container,
            textvariable=self.output_var,
            state="readonly",
        )
        self.output_combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)

        row += 1
        self._add_label(container, row, "Host API")
        self.hostapi_combo = ttk.Combobox(
            container,
            textvariable=self.hostapi_var,
            state="readonly",
        )
        self.hostapi_combo.grid(row=row, column=1, sticky="ew", pady=4)
        self.hostapi_combo.bind("<<ComboboxSelected>>", self.on_hostapi_changed)

        self.refresh_button = ttk.Button(
            container,
            text="Refresh Devices",
            command=self.refresh_devices,
        )
        self.refresh_button.grid(row=row, column=2, sticky="e", padx=(12, 0))

        row += 1
        self._add_label(container, row, "Hotkey")
        self.hotkey_entry = ttk.Entry(container, textvariable=self.hotkey_var)
        self.hotkey_entry.grid(row=row, column=1, sticky="ew", pady=4)
        hotkey_hint = ttk.Label(container, text="Example: f8 or ctrl+shift+z")
        hotkey_hint.grid(row=row, column=2, sticky="w", padx=(12, 0))

        row += 1
        self._add_label(container, row, "Distortion")
        self.mode_combo = ttk.Combobox(
            container,
            textvariable=self.mode_var,
            state="readonly",
            values=["soft_clip", "hard_clip"],
        )
        self.mode_combo.grid(row=row, column=1, sticky="ew", pady=4)

        self.start_check = ttk.Checkbutton(
            container,
            text="Start effect ON",
            variable=self.start_enabled_var,
        )
        self.start_check.grid(row=row, column=2, sticky="w", padx=(12, 0))

        row += 1
        self._add_label(container, row, "Drive")
        drive_frame = ttk.Frame(container)
        drive_frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        drive_frame.columnconfigure(0, weight=1)
        self.drive_scale = ttk.Scale(
            drive_frame,
            from_=1.0,
            to=30.0,
            variable=self.drive_var,
            orient="horizontal",
            command=self.on_drive_changed,
        )
        self.drive_scale.grid(row=0, column=0, sticky="ew")
        self.drive_value_label = ttk.Label(drive_frame, width=6, anchor="e")
        self.drive_value_label.grid(row=0, column=1, padx=(10, 0))

        row += 1
        self._add_label(container, row, "Output gain")
        gain_frame = ttk.Frame(container)
        gain_frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        gain_frame.columnconfigure(0, weight=1)
        self.gain_scale = ttk.Scale(
            gain_frame,
            from_=0.05,
            to=1.0,
            variable=self.post_gain_var,
            orient="horizontal",
            command=self.on_post_gain_changed,
        )
        self.gain_scale.grid(row=0, column=0, sticky="ew")
        self.gain_value_label = ttk.Label(gain_frame, width=6, anchor="e")
        self.gain_value_label.grid(row=0, column=1, padx=(10, 0))

        row += 1
        self._add_label(container, row, "Block size")
        self.blocksize_combo = ttk.Combobox(
            container,
            textvariable=self.blocksize_var,
            state="readonly",
            values=["64", "128", "256", "512"],
        )
        self.blocksize_combo.grid(row=row, column=1, sticky="ew", pady=4)
        block_hint = ttk.Label(container, text="Smaller = lower latency, less stable")
        block_hint.grid(row=row, column=2, sticky="w", padx=(12, 0))

        row += 1
        button_frame = ttk.Frame(container)
        button_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(16, 14))
        button_frame.columnconfigure(5, weight=1)

        self.save_button = ttk.Button(button_frame, text="Save", command=self.save_current_config)
        self.save_button.grid(row=0, column=0, padx=(0, 8))

        self.validate_button = ttk.Button(
            button_frame,
            text="Validate",
            command=self.validate_current_config,
        )
        self.validate_button.grid(row=0, column=1, padx=8)

        self.start_button = ttk.Button(button_frame, text="Start", command=self.start_engine)
        self.start_button.grid(row=0, column=2, padx=8)

        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_engine)
        self.stop_button.grid(row=0, column=3, padx=8)

        self.toggle_button = ttk.Button(
            button_frame,
            text="Toggle Effect",
            command=self.toggle_effect,
        )
        self.toggle_button.grid(row=0, column=4, padx=8)

        row += 1
        status_group = ttk.LabelFrame(container, text="Status", padding=12)
        status_group.grid(row=row, column=0, columnspan=3, sticky="nsew")
        container.rowconfigure(row, weight=1)
        status_group.columnconfigure(1, weight=1)

        ttk.Label(status_group, text="Engine").grid(row=0, column=0, sticky="w")
        ttk.Label(status_group, textvariable=self.status_var).grid(row=0, column=1, sticky="w")

        ttk.Label(status_group, text="Effect").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(status_group, textvariable=self.effect_var).grid(row=1, column=1, sticky="w", pady=(8, 0))

        ttk.Label(status_group, text="Hotkey").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(status_group, textvariable=self.hotkey_status_var).grid(row=2, column=1, sticky="w", pady=(8, 0))

        ttk.Label(
            status_group,
            text=f"Config path: {self.config_path}",
            wraplength=490,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.update_drive_label()
        self.update_gain_label()
        self.update_button_state()

    def _add_label(self, parent: ttk.Frame, row: int, text: str) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 16))

    def load_initial_config(self) -> None:
        try:
            config = load_config(self.config_path)
        except Exception as exc:
            messagebox.showwarning("Eargrape", f"Failed to load config. Using defaults.\n\n{exc}")
            config = create_default_config()
            save_config(config, self.config_path)
        self.apply_config_to_form(config)

    def apply_config_to_form(self, config: AppConfig) -> None:
        self.preferred_input_spec = config.input_device
        self.preferred_output_spec = config.output_device
        self.hostapi_var.set(config.hostapi or "")
        self.hotkey_var.set(config.hotkey)
        self.mode_var.set(config.distortion_mode)
        self.blocksize_var.set(str(config.blocksize))
        self.drive_var.set(config.drive)
        self.post_gain_var.set(config.post_gain)
        self.start_enabled_var.set(config.start_enabled)
        self.hotkey_status_var.set(config.hotkey)
        self.update_drive_label()
        self.update_gain_label()

    def current_device_index(self, direction: str) -> int | None:
        mapping = self.input_device_map if direction == "input" else self.output_device_map
        value = self.input_var.get() if direction == "input" else self.output_var.get()
        return mapping.get(value)

    def build_config_from_form(self) -> AppConfig:
        data = config_to_dict(create_default_config())
        data["input_device"] = self.current_device_index("input")
        data["output_device"] = self.current_device_index("output")
        data["hostapi"] = self.hostapi_var.get() or None
        data["hotkey"] = self.hotkey_var.get().strip()
        data["distortion_mode"] = self.mode_var.get().strip()
        data["blocksize"] = int(self.blocksize_var.get())
        data["drive"] = float(self.drive_var.get())
        data["post_gain"] = float(self.post_gain_var.get())
        data["start_enabled"] = bool(self.start_enabled_var.get())
        return AppConfig(**data)

    def refresh_devices(self, preserve_selection: bool = True) -> None:
        previous_input = (
            self.current_device_index("input")
            if preserve_selection
            else self.preferred_input_spec
        )
        previous_output = (
            self.current_device_index("output")
            if preserve_selection
            else self.preferred_output_spec
        )

        try:
            self.devices = enumerate_devices()
        except Exception as exc:
            messagebox.showerror("Eargrape", f"Failed to enumerate audio devices.\n\n{exc}")
            return

        hostapis = available_hostapis(self.devices)
        current_hostapi = self.hostapi_var.get().strip()
        if not current_hostapi:
            current_hostapi = "Windows WASAPI" if "Windows WASAPI" in hostapis else (hostapis[0] if hostapis else "")
            self.hostapi_var.set(current_hostapi)
        elif current_hostapi not in hostapis and hostapis:
            self.hostapi_var.set(hostapis[0])
            current_hostapi = hostapis[0]

        self.hostapi_combo["values"] = hostapis
        filtered_inputs = filter_devices(self.devices, "input", self.hostapi_var.get() or None)
        filtered_outputs = filter_devices(self.devices, "output", self.hostapi_var.get() or None)

        self.input_device_map = {
            device_display_label(device): device.index for device in filtered_inputs
        }
        self.output_device_map = {
            device_display_label(device): device.index for device in filtered_outputs
        }

        self.input_combo["values"] = list(self.input_device_map.keys())
        self.output_combo["values"] = list(self.output_device_map.keys())

        self._restore_device_selection("input", previous_input)
        self._restore_device_selection("output", previous_output)
        self.update_button_state()

    def _restore_device_selection(
        self,
        direction: str,
        preferred_spec: str | int | None,
    ) -> None:
        mapping = self.input_device_map if direction == "input" else self.output_device_map
        var = self.input_var if direction == "input" else self.output_var

        if preferred_spec is not None:
            if isinstance(preferred_spec, int) or (
                isinstance(preferred_spec, str) and preferred_spec.strip().isdigit()
            ):
                preferred_index = int(preferred_spec)
                for label, device_index in mapping.items():
                    if device_index == preferred_index:
                        var.set(label)
                        return

            if isinstance(preferred_spec, str) and preferred_spec.strip():
                token = preferred_spec.casefold()
                for label in mapping:
                    if token in label.casefold():
                        var.set(label)
                        return

        if not var.get() and mapping:
            first_label = next(iter(mapping))
            var.set(first_label)
        elif var.get() not in mapping:
            var.set(next(iter(mapping), ""))

    def on_hostapi_changed(self, event: object | None = None) -> None:
        del event
        self.refresh_devices()

    def on_drive_changed(self, value: str) -> None:
        del value
        self.update_drive_label()

    def on_post_gain_changed(self, value: str) -> None:
        del value
        self.update_gain_label()

    def update_drive_label(self) -> None:
        self.drive_value_label.config(text=f"{self.drive_var.get():.1f}")

    def update_gain_label(self) -> None:
        self.gain_value_label.config(text=f"{self.post_gain_var.get():.2f}")

    def save_current_config(self) -> None:
        try:
            config = self.build_config_from_form()
            save_config(config, self.config_path)
        except Exception as exc:
            messagebox.showerror("Eargrape", f"Failed to save config.\n\n{exc}")
            return

        self.preferred_input_spec = config.input_device
        self.preferred_output_spec = config.output_device
        self.status_var.set("Config saved")
        self.hotkey_status_var.set(config.hotkey)

    def validate_current_config(self) -> None:
        try:
            config = self.build_config_from_form()
            runtime = validate_runtime(config)
        except Exception as exc:
            messagebox.showerror("Eargrape", f"Validation failed.\n\n{exc}")
            return

        self.status_var.set(
            f"Valid | [{runtime.input_device.index}] -> [{runtime.output_device.index}]"
        )
        messagebox.showinfo(
            "Eargrape",
            (
                "Validation succeeded.\n\n"
                f"Input:  [{runtime.input_device.index}] {runtime.input_device.name}\n"
                f"Output: [{runtime.output_device.index}] {runtime.output_device.name}"
            ),
        )

    def start_engine(self) -> None:
        if self.engine is not None and self.engine.is_running():
            return

        try:
            config = self.build_config_from_form()
            save_config(config, self.config_path)
            self.preferred_input_spec = config.input_device
            self.preferred_output_spec = config.output_device
            self.engine = EargrapeEngine(config, self.enqueue_message)
            self.engine.start()
        except Exception as exc:
            self.engine = None
            messagebox.showerror("Eargrape", f"Failed to start audio engine.\n\n{exc}")
            self.status_var.set("Start failed")
            self.update_button_state()
            return

        self.status_var.set("Starting...")
        self.hotkey_status_var.set(config.hotkey)
        self.update_button_state()

    def stop_engine(self) -> None:
        if self.engine is not None:
            self.engine.stop()
            self.engine = None
        self.status_var.set("Stopped")
        self.effect_var.set("OFF")
        self.update_button_state()

    def toggle_effect(self) -> None:
        if self.engine is None or not self.engine.is_running():
            messagebox.showwarning("Eargrape", "Start the audio engine first.")
            return

        try:
            enabled = self.engine.toggle_effect()
        except Exception as exc:
            messagebox.showerror("Eargrape", str(exc))
            return

        self.effect_var.set("ON" if enabled else "OFF")

    def enqueue_message(self, kind: str, message: str) -> None:
        self.message_queue.put((kind, message))

    def process_messages(self) -> None:
        while True:
            try:
                kind, message = self.message_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "engine":
                self.status_var.set(message)
                if message == "Stopped":
                    self.effect_var.set("OFF")
                    self.update_button_state()
            elif kind == "effect":
                self.effect_var.set(message)
            elif kind == "audio":
                self.status_var.set(f"Audio warning: {message}")
            elif kind == "error":
                self.status_var.set(f"Error: {message}")

        self.update_button_state()
        self.root.after(120, self.process_messages)

    def update_button_state(self) -> None:
        running = self.engine is not None and self.engine.is_running()
        combo_state = "disabled" if running else "readonly"
        scalar_state = "disabled" if running else "normal"

        self.start_button.config(state="disabled" if running else "normal")
        self.stop_button.config(state="normal" if running else "disabled")
        self.toggle_button.config(state="normal" if running else "disabled")
        self.save_button.config(state="disabled" if running else "normal")
        self.validate_button.config(state="disabled" if running else "normal")
        self.refresh_button.config(state="disabled" if running else "normal")

        self.input_combo.config(state=combo_state)
        self.output_combo.config(state=combo_state)
        self.hostapi_combo.config(state=combo_state)
        self.mode_combo.config(state=combo_state)
        self.blocksize_combo.config(state=combo_state)
        self.hotkey_entry.config(state=scalar_state)
        self.start_check.config(state=scalar_state)
        self.drive_scale.config(state=scalar_state)
        self.gain_scale.config(state=scalar_state)

    def on_close(self) -> None:
        if self.engine is not None:
            self.engine.stop()
            self.engine = None
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    EargrapeApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
