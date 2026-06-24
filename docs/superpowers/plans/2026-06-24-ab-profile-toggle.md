# A/B 雙設定檔切換 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 hotkey 從「啟用/關閉單一效果」改成「在兩套完整參數設定檔 A↔B 之間即時切換」。

**Architecture:** `eargrape_core.py` 新增 `EffectProfile` 與兩個 profile 的 `AppConfig`；`EargrapeRouter` 預先把 A、B 兩套參數各算成一份 `_ProfileRuntime`，callback 依 `threading.Event` 選用其一跑同一條 pipeline。GUI 以「A/B 切換編輯」共用單組滑桿。舊扁平 `config.json` 於載入時自動遷移。

**Tech Stack:** Python 3.12、numpy、sounddevice、keyboard、Tkinter、pytest（純邏輯測試）。

## Global Constraints

- 音訊 callback（`EargrapeRouter.callback`）絕不可阻塞或配置記憶體；只用 numpy 就地運算，緩衝依 `blocksize` 預配置。
- 熱路徑的 A/B 切換用 `threading.Event.is_set()`（免鎖讀 bool），不可改用 Lock。
- `distortion_mode` 僅允許 `soft_clip` | `hard_clip`。
- 載入需同時相容「新巢狀格式」與「舊扁平格式」；遷移時缺 `mic_gain` 一律補 `1.0`。
- 所有面向使用者的字串／註解以繁體中文為主。
- 開發機無可錄音裝置：自動化測試僅限不碰音訊硬體的純邏輯。

---

### Task 1: 專案設定 + `EffectProfile` + `validate_profile`

純加法，不更動既有行為。

**Files:**
- Modify: `eargrape_core.py`（新增 dataclass、預設 dict、`validate_profile`；緊接在 `ConfigError` / `DeviceInfo` 之後）
- Create: `tests/test_config.py`
- Create: `requirements-dev.txt`

**Interfaces:**
- Produces:
  - `EffectProfile(name: str, distortion_mode: str, drive: float, mic_gain: float, post_gain: float, mix: float, noise_gate: float)`（`@dataclass(slots=True)`）
  - `validate_profile(profile: EffectProfile) -> None`（不合法 raise `ConfigError`）
  - `DEFAULT_PROFILE_A: dict`、`DEFAULT_PROFILE_B: dict`

- [ ] **Step 1: 環境準備**

```bash
git init                       # 若此資料夾尚未是 git repo；已是則略過
python -m pip install pytest
```

建立 `requirements-dev.txt`：

```
pytest==8.3.3
```

- [ ] **Step 2: 寫失敗測試** — `tests/test_config.py`

```python
import pytest

from eargrape_core import ConfigError, EffectProfile, validate_profile


def _profile(**overrides):
    base = dict(
        name="x",
        distortion_mode="soft_clip",
        drive=1.0,
        mic_gain=1.0,
        post_gain=1.0,
        mix=0.0,
        noise_gate=0.0,
    )
    base.update(overrides)
    return EffectProfile(**base)


def test_validate_profile_accepts_valid():
    validate_profile(_profile())  # 不應 raise


def test_validate_profile_rejects_bad_mix():
    with pytest.raises(ConfigError):
        validate_profile(_profile(mix=1.5))


def test_validate_profile_rejects_unknown_mode():
    with pytest.raises(ConfigError):
        validate_profile(_profile(distortion_mode="fuzz"))


def test_validate_profile_rejects_empty_name():
    with pytest.raises(ConfigError):
        validate_profile(_profile(name="  "))
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL（`ImportError: cannot import name 'EffectProfile'`）

- [ ] **Step 4: 實作** — 在 `eargrape_core.py` 的 `DeviceInfo` 之後加入

```python
@dataclass(slots=True)
class EffectProfile:
    name: str
    distortion_mode: str
    drive: float
    mic_gain: float
    post_gain: float
    mix: float
    noise_gate: float


DEFAULT_PROFILE_A: dict[str, Any] = {
    "name": "普通",
    "distortion_mode": "soft_clip",
    "drive": 1.0,
    "mic_gain": 1.0,
    "post_gain": 1.0,
    "mix": 0.0,
    "noise_gate": 0.0,
}

DEFAULT_PROFILE_B: dict[str, Any] = {
    "name": "爆麥",
    "distortion_mode": "soft_clip",
    "drive": 18.0,
    "mic_gain": 1.0,
    "post_gain": 0.32,
    "mix": 1.0,
    "noise_gate": 0.0,
}


def validate_profile(profile: EffectProfile) -> None:
    if not profile.name.strip():
        raise ConfigError("profile name cannot be empty")
    if profile.distortion_mode not in {"soft_clip", "hard_clip"}:
        raise ConfigError("distortion_mode must be 'soft_clip' or 'hard_clip'")
    if profile.drive <= 0:
        raise ConfigError("drive must be greater than 0")
    if profile.mic_gain <= 0:
        raise ConfigError("mic_gain must be greater than 0")
    if profile.post_gain <= 0:
        raise ConfigError("post_gain must be greater than 0")
    if not 0.0 <= profile.mix <= 1.0:
        raise ConfigError("mix must be between 0.0 and 1.0")
    if profile.noise_gate < 0.0:
        raise ConfigError("noise_gate must be greater than or equal to 0.0")
```

- [ ] **Step 5: 跑測試確認通過**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: Commit**

```bash
git add eargrape_core.py tests/test_config.py requirements-dev.txt
git commit -m "feat: add EffectProfile dataclass and validate_profile"
```

---

### Task 2: 設定層改造（`AppConfig` + 遷移 + 驗證）

把單一效果設定換成兩套 profile，並保留新舊格式相容。此 Task 後，`EargrapeRouter`／GUI／CLI 暫時無法執行（後續 Task 修），但模組仍可 import、設定函式可測。

**Files:**
- Modify: `eargrape_core.py`（`DEFAULT_CONFIG_DATA`、`AppConfig`、`config_from_dict`、`validate_config`；新增 `profile_from_dict`；`create_default_config` / `config_to_dict` / `default_config_data` 維持簽章）
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: `EffectProfile`、`validate_profile`、`DEFAULT_PROFILE_A/B`（Task 1）
- Produces:
  - `AppConfig` 欄位：共用 `input_device, output_device, hostapi, samplerate, blocksize, latency, exclusive_wasapi, hotkey` + `start_pressed: bool` + `profile_a: EffectProfile` + `profile_b: EffectProfile`
  - `profile_from_dict(data: dict, defaults: dict) -> EffectProfile`
  - `config_from_dict(data: dict) -> AppConfig`（新舊格式皆可）

- [ ] **Step 1: 寫失敗測試** — 追加到 `tests/test_config.py`

```python
from eargrape_core import (
    config_from_dict,
    config_to_dict,
    create_default_config,
)


def test_default_config_has_two_profiles():
    config = create_default_config()
    assert config.profile_a.name == "普通"
    assert config.profile_a.drive == 1.0
    assert config.profile_a.mix == 0.0
    assert config.profile_b.name == "爆麥"
    assert config.profile_b.drive == 18.0
    assert config.start_pressed is False


def test_migration_from_legacy_flat_config():
    legacy = {
        "hotkey": "f8",
        "start_enabled": True,
        "distortion_mode": "hard_clip",
        "drive": 20.0,
        "mic_gain": 3.0,
        "post_gain": 0.4,
        "mix": 1.0,
        "noise_gate": 0.01,
    }
    config = config_from_dict(legacy)
    assert config.start_pressed is True
    assert config.profile_b.distortion_mode == "hard_clip"
    assert config.profile_b.drive == 20.0
    assert config.profile_b.mic_gain == 3.0
    assert config.profile_b.post_gain == 0.4
    assert config.profile_a.drive == 1.0
    assert config.profile_a.mix == 0.0
    assert config.profile_a.mic_gain == 3.0  # 沿用舊 boost


def test_migration_missing_mic_gain_defaults_to_one():
    legacy = {"hotkey": "f8", "drive": 18.0, "post_gain": 0.32, "mix": 1.0}
    config = config_from_dict(legacy)
    assert config.profile_a.mic_gain == 1.0
    assert config.profile_b.mic_gain == 1.0


def test_new_format_roundtrip():
    config = create_default_config()
    data = config_to_dict(config)
    again = config_from_dict(data)
    assert config_to_dict(again) == data
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL（`create_default_config` 仍是舊扁平 AppConfig，`profile_a` 屬性不存在）

- [ ] **Step 3: 實作 — 替換 `DEFAULT_CONFIG_DATA`**

把舊的 `DEFAULT_CONFIG_DATA`（含 `start_enabled / distortion_mode / drive / mic_gain / post_gain / mix / noise_gate` 等扁平鍵）整段替換為：

```python
DEFAULT_CONFIG_DATA: dict[str, Any] = {
    "input_device": None,
    "output_device": "CABLE Input",
    "hostapi": "Windows WASAPI",
    "samplerate": 48000,
    "blocksize": 128,
    "latency": "low",
    "exclusive_wasapi": False,
    "hotkey": "f8",
    "start_pressed": False,
    "profile_a": DEFAULT_PROFILE_A,
    "profile_b": DEFAULT_PROFILE_B,
}
```

- [ ] **Step 4: 實作 — 替換 `AppConfig` 定義**

```python
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
    start_pressed: bool
    profile_a: EffectProfile
    profile_b: EffectProfile
```

- [ ] **Step 5: 實作 — 替換 `config_from_dict`、新增 `profile_from_dict`、替換 `validate_config`**

`config_to_dict`（`return asdict(config)`）、`create_default_config`、`default_config_data`、`ensure_config_exists`、`load_config`、`save_config` 維持不動（`asdict` 會自動處理巢狀 dataclass）。替換 `config_from_dict` 與 `validate_config`，並新增 `profile_from_dict`：

```python
def profile_from_dict(data: dict[str, Any], defaults: dict[str, Any]) -> EffectProfile:
    profile = EffectProfile(
        name=str(data.get("name", defaults["name"])),
        distortion_mode=str(
            data.get("distortion_mode", defaults["distortion_mode"])
        ).strip().lower(),
        drive=float(data.get("drive", defaults["drive"])),
        mic_gain=float(data.get("mic_gain", defaults["mic_gain"])),
        post_gain=float(data.get("post_gain", defaults["post_gain"])),
        mix=float(data.get("mix", defaults["mix"])),
        noise_gate=float(data.get("noise_gate", defaults["noise_gate"])),
    )
    validate_profile(profile)
    return profile


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    if "profile_a" in data or "profile_b" in data:
        profile_a = profile_from_dict(data.get("profile_a", {}), DEFAULT_PROFILE_A)
        profile_b = profile_from_dict(data.get("profile_b", {}), DEFAULT_PROFILE_B)
        start_pressed = bool(data.get("start_pressed", DEFAULT_CONFIG_DATA["start_pressed"]))
    else:
        # 舊扁平格式 → 遷移：B 沿用舊效果，A 為乾淨但保留舊 mic boost。
        legacy_mic_gain = float(data.get("mic_gain", 1.0))
        legacy_mode = str(
            data.get("distortion_mode", DEFAULT_PROFILE_B["distortion_mode"])
        ).strip().lower()
        legacy_noise_gate = float(data.get("noise_gate", 0.0))
        profile_b = profile_from_dict(
            {
                "name": DEFAULT_PROFILE_B["name"],
                "distortion_mode": legacy_mode,
                "drive": data.get("drive", DEFAULT_PROFILE_B["drive"]),
                "mic_gain": legacy_mic_gain,
                "post_gain": data.get("post_gain", DEFAULT_PROFILE_B["post_gain"]),
                "mix": data.get("mix", DEFAULT_PROFILE_B["mix"]),
                "noise_gate": legacy_noise_gate,
            },
            DEFAULT_PROFILE_B,
        )
        profile_a = profile_from_dict(
            {
                "name": DEFAULT_PROFILE_A["name"],
                "distortion_mode": legacy_mode,
                "drive": 1.0,
                "mic_gain": legacy_mic_gain,
                "post_gain": 1.0,
                "mix": 0.0,
                "noise_gate": legacy_noise_gate,
            },
            DEFAULT_PROFILE_A,
        )
        start_pressed = bool(data.get("start_enabled", False))

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
        start_pressed=start_pressed,
        profile_a=profile_a,
        profile_b=profile_b,
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.blocksize <= 0:
        raise ConfigError("blocksize must be greater than 0")
    if config.samplerate <= 0:
        raise ConfigError("samplerate must be greater than 0")
    if not config.hotkey.strip():
        raise ConfigError("hotkey cannot be empty")
    for key, value in {
        "input_device": config.input_device,
        "output_device": config.output_device,
    }.items():
        if value is not None and not isinstance(value, (str, int)):
            raise ConfigError(f"{key} must be null, a string, or an integer index")
    validate_profile(config.profile_a)
    validate_profile(config.profile_b)
```

- [ ] **Step 6: 跑測試確認通過**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS（全數通過）

- [ ] **Step 7: Commit**

```bash
git add eargrape_core.py tests/test_config.py
git commit -m "feat: restructure AppConfig into A/B profiles with legacy migration"
```

---

### Task 3: `EargrapeRouter` 改為 A/B profile runtime

**Files:**
- Modify: `eargrape_core.py`（新增 `_ProfileRuntime` + `_profile_runtime`；整段替換 `EargrapeRouter`）
- Create: `tests/test_router.py`

**Interfaces:**
- Consumes: `AppConfig`、`EffectProfile`、`create_default_config`、`config_from_dict`、`config_to_dict`
- Produces:
  - `EargrapeRouter(config: AppConfig)`，方法：`callback(indata, outdata, frames, time, status)`、`toggle() -> bool`（回傳是否切到 B）、`is_b_active() -> bool`、`active_profile_name() -> str`、屬性 `last_status`

- [ ] **Step 1: 寫失敗測試** — `tests/test_router.py`

```python
import numpy as np

from eargrape_core import (
    EargrapeRouter,
    config_from_dict,
    config_to_dict,
    create_default_config,
)


def _make_router(blocksize, start_pressed=False):
    data = config_to_dict(create_default_config())
    data["blocksize"] = blocksize
    data["start_pressed"] = start_pressed
    return EargrapeRouter(config_from_dict(data))


def _run_block(router, samples):
    indata = np.asarray(samples, dtype=np.float32).reshape(-1, 1)
    outdata = np.zeros_like(indata)
    router.callback(indata, outdata, indata.shape[0], None, 0)
    return outdata[:, 0]


def test_profile_a_is_clean_passthrough():
    router = _make_router(blocksize=3)
    out = _run_block(router, [0.1, -0.2, 0.3])
    np.testing.assert_allclose(out, [0.1, -0.2, 0.3], atol=1e-6)


def test_toggle_switches_to_b_distortion():
    router = _make_router(blocksize=2)
    assert router.toggle() is True
    out = _run_block(router, [0.5, -0.5])
    assert not np.allclose(out, [0.5, -0.5])
    assert np.all(np.abs(out) <= 1.0)


def test_active_profile_name_follows_toggle():
    router = _make_router(blocksize=2)
    assert router.active_profile_name() == "普通"
    router.toggle()
    assert router.active_profile_name() == "爆麥"


def test_start_pressed_starts_on_b():
    router = _make_router(blocksize=2, start_pressed=True)
    assert router.is_b_active() is True
    assert router.active_profile_name() == "爆麥"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_router.py -v`
Expected: FAIL（舊 `EargrapeRouter.__init__` 讀 `config.start_enabled` / `config.distortion_mode` 等已不存在的欄位 → AttributeError）

- [ ] **Step 3: 實作 — 在 `EargrapeRouter` 前新增 runtime 結構**

```python
@dataclass(slots=True)
class _ProfileRuntime:
    noise_gate: float
    mix: float
    dry: float
    mic_gain: float
    post_gain: float
    drive: float
    hard_clip: bool
    soft_clip_normalizer: float
    needs_distort: bool


def _profile_runtime(profile: EffectProfile) -> _ProfileRuntime:
    drive = float(profile.drive)
    return _ProfileRuntime(
        noise_gate=profile.noise_gate,
        mix=profile.mix,
        dry=1.0 - profile.mix,
        mic_gain=profile.mic_gain,
        post_gain=profile.post_gain,
        drive=drive,
        hard_clip=profile.distortion_mode == "hard_clip",
        soft_clip_normalizer=1.0 / np.tanh(drive),
        needs_distort=profile.mix > 0.0,
    )
```

- [ ] **Step 4: 實作 — 整段替換 `EargrapeRouter`**

```python
class EargrapeRouter:
    def __init__(self, config: AppConfig) -> None:
        # threading.Event.is_set() 免鎖讀 bool，比 Lock 更適合 callback 熱路徑。
        self._effect_event = threading.Event()
        if config.start_pressed:
            self._effect_event.set()
        self.last_status: str | None = None

        # 預先把 A、B 兩套參數各算成一份 runtime（熱路徑零分配）。
        self._rt_a = _profile_runtime(config.profile_a)
        self._rt_b = _profile_runtime(config.profile_b)
        self._name_a = config.profile_a.name
        self._name_b = config.profile_b.name

        self._buf_wet = np.zeros(config.blocksize, dtype=np.float32)
        self._buf_out = np.zeros(config.blocksize, dtype=np.float32)

    def toggle(self) -> bool:
        if self._effect_event.is_set():
            self._effect_event.clear()
            return False
        self._effect_event.set()
        return True

    def is_b_active(self) -> bool:
        return self._effect_event.is_set()

    def active_profile_name(self) -> str:
        return self._name_b if self._effect_event.is_set() else self._name_a

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

        p = self._rt_b if self._effect_event.is_set() else self._rt_a

        mono = indata[:, 0] if indata.shape[1] == 1 else np.mean(indata, axis=1, dtype=np.float32)

        if p.noise_gate > 0.0:
            np.copyto(self._buf_out, mono)
            self._buf_out[np.abs(self._buf_out) < p.noise_gate] = 0.0
            mono = self._buf_out

        if p.needs_distort:
            self._distort(mono, self._buf_wet, p)
            if p.mix == 1.0:
                np.multiply(self._buf_wet, p.post_gain, out=self._buf_out)
            else:
                np.multiply(mono, p.dry, out=self._buf_out)
                np.multiply(self._buf_wet, p.mix, out=self._buf_wet)
                np.add(self._buf_out, self._buf_wet, out=self._buf_out)
                np.multiply(self._buf_out, p.post_gain, out=self._buf_out)
        else:
            np.multiply(mono, p.post_gain, out=self._buf_out)

        if p.mic_gain != 1.0:
            np.multiply(self._buf_out, p.mic_gain, out=self._buf_out)

        np.clip(self._buf_out, -1.0, 1.0, out=self._buf_out)

        outdata[:] = self._buf_out[:, None]

    def _distort(self, mono: np.ndarray, out: np.ndarray, p: _ProfileRuntime) -> None:
        np.multiply(mono, p.drive, out=out)
        if p.hard_clip:
            np.clip(out, -1.0, 1.0, out=out)
        else:
            np.tanh(out, out=out)
            np.multiply(out, p.soft_clip_normalizer, out=out)
```

- [ ] **Step 5: 跑測試確認通過**

Run: `python -m pytest tests/test_router.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: Commit**

```bash
git add eargrape_core.py tests/test_router.py
git commit -m "feat: route audio through per-profile A/B runtimes"
```

---

### Task 4: `EargrapeEngine` — profile 切換與狀態

**Files:**
- Modify: `eargrape_core.py`（`EargrapeEngine`：`is_effect_enabled`→`active_profile_name`、`toggle_effect`→`toggle_profile`、`start()` 內 hotkey 綁定、`_run_stream` 內 emit）
- Create: `tests/test_engine.py`

**Interfaces:**
- Consumes: `EargrapeRouter`、`AppConfig`、`create_default_config`、`config_from_dict`、`config_to_dict`
- Produces:
  - `EargrapeEngine.active_profile_name() -> str`
  - `EargrapeEngine.toggle_profile() -> str`（回傳切換後 live profile 名稱；router 為 None 時 raise `RuntimeError`）
  - `StatusCallback` 新增 `kind == "profile"`，payload 為 profile 名稱（取代舊 `"effect"` 的 `"ON"/"OFF"`）

- [ ] **Step 1: 寫失敗測試** — `tests/test_engine.py`

```python
import pytest

from eargrape_core import (
    EargrapeEngine,
    config_from_dict,
    config_to_dict,
    create_default_config,
)


def test_active_profile_name_before_start_uses_start_pressed():
    config = create_default_config()  # start_pressed False
    engine = EargrapeEngine(config)
    assert engine.active_profile_name() == "普通"

    data = config_to_dict(config)
    data["start_pressed"] = True
    engine_b = EargrapeEngine(config_from_dict(data))
    assert engine_b.active_profile_name() == "爆麥"


def test_toggle_profile_without_running_raises():
    engine = EargrapeEngine(create_default_config())
    with pytest.raises(RuntimeError):
        engine.toggle_profile()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL（`AttributeError: 'EargrapeEngine' object has no attribute 'active_profile_name'`）

- [ ] **Step 3: 實作 — 替換 `EargrapeEngine` 的 `is_effect_enabled` 與 `toggle_effect`**

把舊的 `is_effect_enabled` 與 `toggle_effect` 兩個方法整段替換為：

```python
    def active_profile_name(self) -> str:
        with self.lock:
            if self.router is None:
                return (
                    self.config.profile_b.name
                    if self.config.start_pressed
                    else self.config.profile_a.name
                )
            return self.router.active_profile_name()

    def toggle_profile(self) -> str:
        with self.lock:
            if self.router is None:
                raise RuntimeError("Engine is not running.")
            self.router.toggle()
            name = self.router.active_profile_name()
        self._emit("profile", name)
        return name
```

- [ ] **Step 4: 實作 — 更新 `start()` 的 hotkey 綁定**

在 `start()` 中，把：

```python
            self.hotkey_handle = keyboard.add_hotkey(
                self.config.hotkey,
                self.toggle_effect,
                suppress=False,
            )
```

改為：

```python
            self.hotkey_handle = keyboard.add_hotkey(
                self.config.hotkey,
                self.toggle_profile,
                suppress=False,
            )
```

- [ ] **Step 5: 實作 — 更新 `_run_stream` 的狀態 emit**

在 `_run_stream` 中，把：

```python
                        self._emit("engine", running_message)
                        self._emit("effect", "ON" if router.is_enabled() else "OFF")
                        self.startup_event.set()
```

改為：

```python
                        self._emit("engine", running_message)
                        self._emit("profile", router.active_profile_name())
                        self.startup_event.set()
```

- [ ] **Step 6: 跑全部測試確認通過**

Run: `python -m pytest -v`
Expected: PASS（test_config / test_router / test_engine 全數通過）

- [ ] **Step 7: Commit**

```bash
git add eargrape_core.py tests/test_engine.py
git commit -m "feat: engine toggles between A/B profiles and emits profile status"
```

---

### Task 5: GUI — A/B 切換編輯

無自動化測試（Tkinter）；以手動冒煙測試驗收。共用區（裝置 / Host API / Refresh / Hotkey / Block size / 按鈕 / Status）保留；效果區改為單組滑桿 + 「編輯中 A|B」切換。

**Files:**
- Modify: `eargrape_gui.py`

**Interfaces:**
- Consumes: `config_from_dict`、`config_to_dict`、`DEFAULT_CONFIG_DATA`、`create_default_config`、`load_config`、`save_config`、`validate_runtime`、`EargrapeEngine.toggle_profile`、`EargrapeEngine.active_profile_name`

- [ ] **Step 1: 匯入 `DEFAULT_CONFIG_DATA`**

在 `eargrape_gui.py` 頂部 `from eargrape_core import (...)` 清單中加入 `DEFAULT_CONFIG_DATA`（與其他匯入並列）。

- [ ] **Step 2: `__init__` 內新增狀態變數**

在 `EargrapeApp.__init__` 把 `self.start_enabled_var = tk.BooleanVar()` 替換為下列，並新增 profile 暫存與編輯目標：

```python
        self.start_pressed_var = tk.BooleanVar()
        self.edit_target_var = tk.StringVar(value="a")
        self.edit_profile = "a"
        self.profile_a_data: dict = dict(DEFAULT_CONFIG_DATA["profile_a"])
        self.profile_b_data: dict = dict(DEFAULT_CONFIG_DATA["profile_b"])
```

- [ ] **Step 3: `build_ui` — 在 Distortion 列前插入「編輯中」切換**

在 `build_ui` 中、目前 `self._add_label(container, row, "Distortion")` 那一段**之前**，插入一列 A/B 切換（沿用既有 `row` 遞增模式）：

```python
        row += 1
        self._add_label(container, row, "編輯中")
        edit_frame = ttk.Frame(container)
        edit_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        self.edit_a_radio = ttk.Radiobutton(
            edit_frame,
            text="A 普通",
            value="a",
            variable=self.edit_target_var,
            command=self.on_edit_target_changed,
        )
        self.edit_a_radio.grid(row=0, column=0, padx=(0, 16))
        self.edit_b_radio = ttk.Radiobutton(
            edit_frame,
            text="B 爆麥",
            value="b",
            variable=self.edit_target_var,
            command=self.on_edit_target_changed,
        )
        self.edit_b_radio.grid(row=0, column=1)
```

- [ ] **Step 4: `build_ui` — 改 start checkbox 綁定與文字**

把目前的：

```python
        self.start_check = ttk.Checkbutton(
            container,
            text="Start effect ON",
            variable=self.start_enabled_var,
        )
```

改為：

```python
        self.start_check = ttk.Checkbutton(
            container,
            text="啟動時用 B(爆麥)",
            variable=self.start_pressed_var,
        )
```

- [ ] **Step 5: `build_ui` — Status 區「Effect」改「Live」**

把 status group 內：

```python
        ttk.Label(status_group, text="Effect").grid(row=1, column=0, sticky="w", pady=(8, 0))
```

改為：

```python
        ttk.Label(status_group, text="Live").grid(row=1, column=0, sticky="w", pady=(8, 0))
```

（`effect_var` 變數名沿用，僅顯示文字改為 profile 名稱。其初始值改為 `tk.StringVar(value="普通")`：把 `__init__` 內 `self.effect_var = tk.StringVar(value="OFF")` 改成 `self.effect_var = tk.StringVar(value="普通")`。）

- [ ] **Step 6: 新增 profile 載入/擷取/切換 helper 方法**

在 `EargrapeApp` 內新增三個方法（放在 `apply_config_to_form` 附近）：

```python
    def _load_profile_into_sliders(self, which: str) -> None:
        data = self.profile_a_data if which == "a" else self.profile_b_data
        self.mode_var.set(data["distortion_mode"])
        self.drive_var.set(data["drive"])
        self.mic_gain_var.set(data["mic_gain"])
        self.post_gain_var.set(data["post_gain"])
        self.update_drive_label()
        self.update_mic_gain_label()
        self.update_gain_label()

    def _capture_sliders_into_profile(self, which: str) -> None:
        data = self.profile_a_data if which == "a" else self.profile_b_data
        # 只覆寫 GUI 有露出的欄位；name / mix / noise_gate 保留。
        data["distortion_mode"] = self.mode_var.get().strip()
        data["drive"] = float(self.drive_var.get())
        data["mic_gain"] = float(self.mic_gain_var.get())
        data["post_gain"] = float(self.post_gain_var.get())

    def on_edit_target_changed(self) -> None:
        target = self.edit_target_var.get()
        if target == self.edit_profile:
            return
        self._capture_sliders_into_profile(self.edit_profile)
        self.edit_profile = target
        self._load_profile_into_sliders(target)
```

- [ ] **Step 7: 替換 `apply_config_to_form`**

```python
    def apply_config_to_form(self, config: AppConfig) -> None:
        self.preferred_input_spec = config.input_device
        self.preferred_output_spec = config.output_device
        self.hostapi_var.set(config.hostapi or "")
        self.hotkey_var.set(config.hotkey)
        self.blocksize_var.set(str(config.blocksize))
        self.start_pressed_var.set(config.start_pressed)
        self.hotkey_status_var.set(config.hotkey)

        self.profile_a_data = config_to_dict(config)["profile_a"]
        self.profile_b_data = config_to_dict(config)["profile_b"]
        self.edit_profile = "a"
        self.edit_target_var.set("a")
        self._load_profile_into_sliders("a")
```

- [ ] **Step 8: 替換 `build_config_from_form`**

```python
    def build_config_from_form(self) -> AppConfig:
        self._capture_sliders_into_profile(self.edit_profile)
        data = dict(DEFAULT_CONFIG_DATA)
        data["input_device"] = self.current_device_index("input")
        data["output_device"] = self.current_device_index("output")
        data["hostapi"] = self.hostapi_var.get() or None
        data["hotkey"] = self.hotkey_var.get().strip()
        data["blocksize"] = int(self.blocksize_var.get())
        data["start_pressed"] = bool(self.start_pressed_var.get())
        data["profile_a"] = dict(self.profile_a_data)
        data["profile_b"] = dict(self.profile_b_data)
        return config_from_dict(data)
```

- [ ] **Step 9: 替換 `toggle_effect`（改呼叫 `toggle_profile`）**

```python
    def toggle_effect(self) -> None:
        if self.engine is None or not self.engine.is_running():
            messagebox.showwarning("Eargrape", "Start the audio engine first.")
            return

        try:
            name = self.engine.toggle_profile()
        except Exception as exc:
            messagebox.showerror("Eargrape", str(exc))
            return

        self.effect_var.set(name)
```

- [ ] **Step 10: 更新 `process_messages` 的事件處理**

把 `process_messages` 內：

```python
            elif kind == "effect":
                self.effect_var.set(message)
```

改為：

```python
            elif kind == "profile":
                self.effect_var.set(message)
```

並把同函式中 `if message == "Stopped":` 區塊內的 `self.effect_var.set("OFF")` 改為 `self.effect_var.set(self.profile_a_data["name"])`。

- [ ] **Step 11: 更新 `stop_engine` 與 `update_button_state`**

`stop_engine` 內 `self.effect_var.set("OFF")` → `self.effect_var.set(self.profile_a_data["name"])`。

`update_button_state` 內，於 combobox 群組停用清單加入兩顆 radio（執行中不可改編輯目標）：在 `self.start_check.config(state=scalar_state)` 之後加入：

```python
        self.edit_a_radio.config(state=scalar_state)
        self.edit_b_radio.config(state=scalar_state)
        self.mic_gain_scale.config(state=scalar_state)
```

（`mic_gain_scale` 原本未納入啟用/停用控制，一併補上以保持一致。）

- [ ] **Step 12: 手動冒煙測試**

Run: `python eargrape_gui.py`
Expected（即使無音訊輸入裝置也能驗）：
1. 視窗開啟，效果區出現「編輯中: A 普通 / B 爆麥」單選。
2. 編輯中=A 時，Drive 預設約 1.0；切到 B 時 Drive 跳成 18.0、Effect gain 約 0.32 → 證明兩套各自載入。
3. 在 A 改 Drive=5、切到 B 再切回 A，A 的 Drive 仍是 5 → 證明切換有保存。
4. 按 **Save**；用編輯器打開 `config.json`，確認為新巢狀格式且含 `profile_a` / `profile_b` / `start_pressed`，且 `mix` / `noise_gate` 仍在。
5. 關閉再重開 GUI，數值與步驟 3 一致 → 證明存讀正確。

- [ ] **Step 13: Commit**

```bash
git add eargrape_gui.py
git commit -m "feat: GUI edits A/B profiles with a switchable editor"
```

---

### Task 6: CLI — profile 狀態與 validate 輸出

**Files:**
- Modify: `eargrape.py`

**Interfaces:**
- Consumes: `AppConfig.profile_a/profile_b/start_pressed`、`StatusCallback kind == "profile"`

- [ ] **Step 1: 更新狀態 handler**

在 `run()` 的 `handle_status` 內，把：

```python
        elif kind == "effect":
            print(f"[HOTKEY] distortion {message}")
```

改為：

```python
        elif kind == "profile":
            print(f"[HOTKEY] profile -> {message}")
```

- [ ] **Step 2: 擴充 `--validate-config` 輸出**

在 `--validate-config` 區塊中，於現有 `print(f"Block size:  {config.blocksize}")` 之後加入：

```python
        start_name = config.profile_b.name if config.start_pressed else config.profile_a.name
        print(f"Start profile: {'B' if config.start_pressed else 'A'} {start_name}")
        for label, profile in (("A", config.profile_a), ("B", config.profile_b)):
            print(
                f"Profile {label} [{profile.name}]: mode={profile.distortion_mode} "
                f"drive={profile.drive} mic_gain={profile.mic_gain} "
                f"post_gain={profile.post_gain} mix={profile.mix} gate={profile.noise_gate}"
            )
```

- [ ] **Step 3: 手動驗證（語法 + 載入）**

Run: `python -c "import eargrape"`
Expected: 無錯誤（語法正確、模組可匯入）

Run: `python eargrape.py --validate-config`
Expected: 若有可用裝置則印出兩個 profile 摘要；若裝置不符會印 device 相關錯誤（屬預期，非本 Task 範圍）。

- [ ] **Step 4: Commit**

```bash
git add eargrape.py
git commit -m "feat: CLI reports A/B profiles in status and validate output"
```

---

### Task 7: 更新 `config.json` 範本與文件

**Files:**
- Modify: `config.json`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 用新巢狀格式覆寫 `config.json`**

```json
{
  "input_device": null,
  "output_device": "CABLE Input",
  "hostapi": "Windows WASAPI",
  "samplerate": 48000,
  "blocksize": 128,
  "latency": "low",
  "exclusive_wasapi": false,
  "hotkey": "f8",
  "start_pressed": false,
  "profile_a": {
    "name": "普通",
    "distortion_mode": "soft_clip",
    "drive": 1.0,
    "mic_gain": 1.0,
    "post_gain": 1.0,
    "mix": 0.0,
    "noise_gate": 0.0
  },
  "profile_b": {
    "name": "爆麥",
    "distortion_mode": "soft_clip",
    "drive": 18.0,
    "mic_gain": 1.0,
    "post_gain": 0.32,
    "mix": 1.0,
    "noise_gate": 0.0
  }
}
```

- [ ] **Step 2: 更新 `README.md`**

更新「使用方式 / Config」段落：說明 hotkey 已是「A↔B 兩套設定切換」而非開關；`profile_a`（普通）平常用、`profile_b`（爆麥）按下用；`start_pressed` 取代 `start_enabled`；附上步驟 1 的新 `config.json` 範例；補一行「舊版 `config.json` 會在載入時自動轉新格式」。

- [ ] **Step 3: 更新 `CLAUDE.md`**

- 「Core data flow」第 3 點：改述 `EargrapeRouter` 依目前生效 profile（A/B）跑 pipeline，hotkey 為 A↔B 切換、`_ProfileRuntime` 預先計算兩套。
- 「Thread safety」：`_effect_event` 現在代表「B 是否生效」。
- 「Commands」：把「No test suite exists」改為 `python -m pytest`（純邏輯測試：設定遷移 / 驗證 / clip 數學 / A·B 切換）；`pip install -r requirements-dev.txt`。
- 「Config file location / 設定」：補 `config_from_dict` 會自動遷移舊扁平格式。

- [ ] **Step 4: 全測試 + 匯入冒煙**

Run: `python -m pytest -v`
Expected: 全數通過

Run: `python -c "import eargrape_core, eargrape, eargrape_gui"`
Expected: 無錯誤

- [ ] **Step 5: Commit**

```bash
git add config.json README.md CLAUDE.md
git commit -m "docs: document A/B profile toggle and refresh config template"
```

---

## Self-Review

**Spec coverage：**
- A/B 資料模型 → Task 1、2 ✓
- 設定遷移／新舊相容 → Task 2 ✓
- Router 雙 runtime 與切換 → Task 3 ✓
- Engine 切換 + 狀態 → Task 4 ✓
- GUI A/B 切換編輯、mix/noise_gate 保留 → Task 5 ✓
- 狀態列 live profile 名稱 → Task 4（emit）、Task 5（顯示）✓
- CLI → Task 6 ✓
- 純邏輯 pytest → Task 1–4 ✓
- 文件 + config 範本 → Task 7 ✓

**Type consistency：** `toggle()`/`toggle_profile()`/`active_profile_name()`/`is_b_active()`/`_ProfileRuntime` 欄位於各 Task 一致；GUI/CLI 一律消費 `kind == "profile"`，已移除 `"effect"` payload 與 `is_effect_enabled`/`toggle_effect`/`start_enabled`。

**Placeholder scan：** 無 TBD/TODO；每個 code step 均附完整程式碼與預期輸出。
