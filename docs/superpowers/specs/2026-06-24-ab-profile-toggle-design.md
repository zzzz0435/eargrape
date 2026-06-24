# A/B 雙設定檔切換 — 設計規格

日期：2026-06-24
狀態：草稿（待使用者審閱）

## 背景與問題

目前 hotkey 的語意是「**啟用 / 關閉**單一爆麥效果」：
- 效果 OFF → 乾淨原音透傳 + `mic_gain`（`EargrapeRouter.callback` 走 `np.copyto(buf_out, mono)`）
- 效果 ON → 套用 `drive / mix / post_gain` 失真

使用者最初想用 hotkey 在「原生麥克風」與「效果版」之間切換，但因為 Discord 同一時間只能綁定**一個**麥克風裝置、且沒有快速切換裝置的快捷鍵，所以必須把 Discord 永久設成 `CABLE Output`。結論是：切換只能發生在 **Eargrape 送進同一條 cable 的內容**上，而不是切換 Discord 的裝置。

使用者真正的訴求（已於 brainstorming 釐清）：把 hotkey 從「開關效果」改成「**在兩套完整參數之間切換**」——平常一套（普通／乾淨＋mic boost），按下一套（爆麥／drive 與 effect gain 拉滿），且**每個效果參數都能各自設定兩個值**。

## 目標

1. hotkey 切換 **Profile A（放開／普通）↔ Profile B（按下／爆麥）**，不再是 on/off。
2. 每個 profile 各自獨立擁有：`distortion_mode / drive / mic_gain / post_gain / mix / noise_gate`。
3. 舊的扁平 `config.json` **自動遷移**、新舊格式都讀得進來。
4. GUI 採「**A/B 切換編輯**」版面：保留單組滑桿，上方加「編輯中: A | B」切換；裝置／hotkey／blocksize／按鈕／狀態為共用區。
5. 狀態列顯示目前 live 的 profile 名稱（預設「普通」「爆麥」）。
6. 補一組**純邏輯 pytest**（設定遷移、profile 參數計算、clip 數學），不需音訊硬體即可在開發機執行。

## 非目標（YAGNI）

- 不支援超過兩套 profile。
- `mix` 與 `noise_gate` **不**拉進 GUI，維持只在 `config.json` 編輯（與現況一致）。
- 不在 GUI 提供 profile 改名 widget（名稱可在 config 編輯，v1 僅顯示）。
- 不更動裝置解析與相容性退場機制（`resolve_device` / `iter_runtime_candidates` 等）。
- 不嘗試自動化 Discord 端（裝置限制使其不可行）。

## 資料模型（`eargrape_core.py`）

新增 `EffectProfile` dataclass：

```python
@dataclass(slots=True)
class EffectProfile:
    name: str
    distortion_mode: str   # soft_clip | hard_clip
    drive: float
    mic_gain: float
    post_gain: float
    mix: float             # 0.0=全乾(純透傳/boost) .. 1.0=全濕
    noise_gate: float
```

`AppConfig` 調整為「共用串流設定 + 兩個 profile」：

```python
@dataclass(slots=True)
class AppConfig:
    # 共用（不變）
    input_device, output_device, hostapi
    samplerate, blocksize, latency, exclusive_wasapi, hotkey
    # 切換
    start_pressed: bool          # 取代 start_enabled：啟動時是否以 B 生效
    profile_a: EffectProfile     # 放開／普通
    profile_b: EffectProfile     # 按下／爆麥
```

### 預設值

| 參數 | profile_a（普通） | profile_b（爆麥） |
|------|------------------|------------------|
| name | 普通 | 爆麥 |
| distortion_mode | soft_clip | soft_clip |
| drive | 1.0 | 18.0 |
| mic_gain | 1.0 | 1.0 |
| post_gain | 1.0 | 0.32 |
| mix | 0.0 | 1.0 |
| noise_gate | 0.0 | 0.0 |

`start_pressed = false`。profile_b 即沿用目前 `DEFAULT_CONFIG_DATA` 的效果數值；profile_a 為「乾淨＋可 boost」（`mix=0 → 不套失真`）。

## 設定檔（序列化 / 遷移）

`config_from_dict(data)` 同時支援兩種格式：

- **新格式**（含 `profile_a` / `profile_b`）→ 各自以 `profile_from_dict()` 解析（沿用 `.get` 容錯，缺鍵以預設補）。
- **舊扁平格式**（含 `drive` 等頂層效果鍵）→ 遷移：
  - `profile_b` ← 舊效果欄位（`distortion_mode / drive / mic_gain(缺則 1.0) / post_gain / mix / noise_gate`），name="爆麥"
  - `profile_a` ← 乾淨版但**沿用舊 `mic_gain`**（保留原本 OFF 狀態的 boost 行為）：`drive=1.0, mix=0.0, post_gain=1.0, distortion_mode=舊值, noise_gate=舊值, mic_gain=舊 mic_gain`，name="普通"
  - `start_pressed` ← 舊 `start_enabled`

`config_to_dict()` 一律輸出**新巢狀格式**（`asdict` 處理巢狀 dataclass）。舊使用者載入後，下次 Save 即升級成新格式。

> 註：repo 內現有的 `config.json` 是扁平且**缺 `mic_gain`** —— 遷移需以 `mic_gain=1.0` 補上，不可假設該鍵存在。

## 驗證

- 抽出 `validate_profile(profile)`：`drive>0`、`mic_gain>0`、`post_gain>0`、`0<=mix<=1`、`noise_gate>=0`、`distortion_mode ∈ {soft_clip, hard_clip}`、`name` 非空。
- `validate_config(config)`：`blocksize>0`、`samplerate>0`、`hotkey` 非空、device 規格合法；再對 `profile_a`、`profile_b` 各跑 `validate_profile`。

## 音訊核心（`EargrapeRouter`）

移除「效果 on/off」分支，改為「**目前生效的 profile**」。`__init__` 預先把 A、B 兩套參數各算成一份 `_ProfileRuntime`（純 scalar，供熱路徑零分配使用）：

```python
@dataclass(slots=True)
class _ProfileRuntime:
    noise_gate: float
    mix: float
    dry: float                 # 1 - mix
    mic_gain: float
    post_gain: float
    drive: float
    hard_clip: bool
    soft_clip_normalizer: float  # 1/tanh(drive)
    needs_distort: bool          # mix > 0.0
```

- `__init__`：建 `_rt_a`、`_rt_b`；`_buf_wet`、`_buf_out` 維持依 `blocksize` 預配置；`_event = threading.Event()`，`start_pressed` 為真則 `.set()`（B 生效）。沿用以 `Event.is_set()` 免鎖讀取作為熱路徑切換的設計。
- `callback`：
  ```
  p = _rt_b if _event.is_set() else _rt_a
  mono = 下混為單聲道
  if p.noise_gate > 0: 套 noise gate
  if p.needs_distort:
      _distort(mono, _buf_wet, p)            # drive / hard_clip / normalizer 取自 p
      mix==1.0 → _buf_out = _buf_wet * post_gain
      否則     → _buf_out = mono*dry + _buf_wet*mix，再 * post_gain
  else:
      _buf_out = mono * p.post_gain          # 乾淨 + 輸出增益
  if p.mic_gain != 1.0: _buf_out *= p.mic_gain
  np.clip(_buf_out, -1, 1)
  outdata[:] = _buf_out[:, None]
  ```
  （緩衝重用順序與現行一致：先算 wet 再覆寫 out，gate 用 `_buf_out` 暫存後當作 mono 亦安全。）
- `_distort(mono, out, rt)`：簽章改為吃 `_ProfileRuntime`，內部用 `rt.drive / rt.hard_clip / rt.soft_clip_normalizer`。
- `toggle() -> bool`：翻轉 `_event`，回傳是否切到 B。
- `active_profile_name() -> str`：回傳目前生效 profile 的 `name`。

## 引擎（`EargrapeEngine`）

- `start()`：初始 `_event` 由 `start_pressed` 決定。
- `toggle_effect` → 改名 `toggle_profile`，回傳/送出**目前 live 的 profile 名稱**。
- `is_effect_enabled` → `active_profile_name()`。
- 狀態事件：`StatusCallback` 的 `kind` 新增/改為 `"profile"`，payload 為 profile 名稱（取代原本 `"effect"` 的 `"ON"/"OFF"`）。`engine` 的 running 行附帶目前 live profile。

## GUI（`eargrape_gui.py`）— A/B 切換編輯

共用區（裝置 / Host API / Refresh / Hotkey / Block size / Save・Validate・Start・Stop・Toggle / Status）**不變**。效果區改為：

```
─ Effect profiles ──────────────
編輯中:  (•) A 普通   ( ) B 爆麥
Distortion  [ soft_clip ]
Drive       [==|        ]  1.0
Mic boost   [======|    ]  2.0x
Effect gain [=========| ]  0.80
☐ 啟動時用 B(爆麥)
```

- 新增 `self.edit_profile`（"a"/"b"）與兩顆 Radiobutton 作「編輯中」切換。
- 既有 `mode_var / drive_var / mic_gain_var / post_gain_var` 改為代表**目前編輯中**的 profile。
- 以 `self.profile_a_data / self.profile_b_data`（dict 或 `EffectProfile`）保存兩套；切換編輯目標時：先把目前滑桿值**寫回**離開的 profile，再把進入的 profile **載入**滑桿。
- **GUI 只覆寫它有露出的欄位**（`distortion_mode / drive / mic_gain / post_gain`）；`mix / noise_gate / name` 必須從既存的 `profile_*_data` **保留**，不可用預設重建而洗掉（否則 config 裡手動設的 mix/noise_gate 會在 Save 時遺失）。
- `build_config_from_form()`：先把目前編輯 profile 的滑桿值寫回對應 `profile_*_data`，再以**兩份既存 profile 資料**（含保留的 mix/noise_gate/name）+ 共用欄位 + `start_pressed` 組出 `AppConfig`。
- `apply_config_to_form(config)`：存下兩 profile、編輯目標設 A、載入 A 至滑桿、設定 `start_pressed` 勾選。
- 既有 checkbox「Start effect ON」→「啟動時用 B(爆麥)」綁 `start_pressed`。
- Status 區「Effect」標籤 → 「Live」，顯示目前生效 profile 名稱（消費 `kind=="profile"`）。
- `update_button_state()`：引擎執行中時，比照現況 disable 編輯切換器與滑桿（效果參數於 `start()` 時烘焙進 router，執行中改值需重啟才生效）；但 **Toggle 按鈕在執行中維持可用**（即時切換 live profile）。

## CLI（`eargrape.py`）

- 狀態 handler：`kind=="profile"` → 印 `"[HOTKEY] profile -> <名稱>"`。
- `--validate-config`：除現有裝置/取樣率/blocksize 外，列出 A、B 兩 profile 摘要與 `start_pressed`。

## 測試（新增 `tests/`，pytest）

開發機無可錄音裝置，故聚焦**不碰音訊硬體的純邏輯**：

1. `test_config_migration`：舊扁平 dict → `profile_a/b` 正確生成；`start_enabled→start_pressed`；profile_a 為乾淨（`mix=0, drive=1`）且沿用舊 `mic_gain`；profile_b 對應舊效果；缺 `mic_gain` 時補 1.0。
2. `test_config_roundtrip`：新巢狀 dict → `config_to_dict` → `config_from_dict` 穩定不變。
3. `test_validate_profile`：各非法值（drive<=0、mix>1、未知 distortion_mode…）皆 raise `ConfigError`。
4. `test_router_ab_switch`：用已知 numpy 輸入直接呼叫 `callback`（自備 in/out 陣列）。profile A 乾淨（`drive=1,mix=0,gain=1`）→ 輸出≈輸入（clip 後）；`toggle()` 後走 profile B → 輸出符合對應 clip 數學。驗證 A/B 切換邏輯。

執行：`python -m pytest`（需 `pip install pytest`；另加 `requirements-dev.txt` 收錄 `pytest`）。

## 文件

- 更新 `README.md`：說明 hotkey 改為 A/B 切換、兩 profile 的設定與新版 `config.json` 範例。
- 更新 `CLAUDE.md`：核心資料流改述為「A/B profile 切換」、`start_pressed`、新增測試指令與「No test suite exists」一行的修訂。

## 相容性與風險

- 載入路徑必須對「新巢狀」「舊扁平」皆不崩潰；遷移後欄位語意需與舊 OFF/ON 行為對齊（A 保留舊 mic boost、B 等同舊效果）。
- frozen exe 旁的舊 `config.json` 於載入時即遷移，Save 後升級格式。
- 無功能旗標、單次切換；屬破壞性結構變更但有遷移保護。
