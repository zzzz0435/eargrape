# Eargrape

透過快捷鍵即時切換爆麥效果，並支援單純放大麥克風音量的 Windows 麥克風路由工具。

```
真實麥克風 → Eargrape（mic boost / 失真效果）→ 虛擬音效卡輸入 → Discord / 遊戲讀取虛擬音效卡輸出
```

## 前置需求

使用前需先安裝 **VB-CABLE**（免費虛擬音效卡驅動）：

1. 前往 https://vb-audio.com/Cable/ 下載
2. 解壓縮後右鍵 `VBCABLE_Setup_x64.exe` → **以系統管理員身分執行** → Install Driver
3. 重新開機

## 使用方式

啟動 `Eargrape.exe`，在視窗裡設定：

| 欄位 | 說明 |
|------|------|
| Input mic | 選你的真實麥克風 |
| Output target | 選 `CABLE Input`（虛擬音效卡輸入端） |
| Host API | 先用 `Windows WASAPI`，若不穩定會自動退到相容模式 |
| Hotkey | 點「Record」後按下想要的快捷鍵，或直接手打（例如 `f8`）。按下時在 **A↔B 兩套設定之間切換** |
| 編輯中 A / B | 選現在要編輯哪一套設定。下面的 Distortion / Drive / Mic boost / Effect gain 都是套用到目前選的那一套 |
| Distortion | `soft_clip` 較圓潤，`hard_clip` 較破碎刺耳 |
| Mic boost | 放大麥克風音量 |
| Drive | 失真強度，數字越大越爆 |
| Effect gain | 失真後的音量補償 |
| 啟動時用 B(爆麥) | 勾選後，Start 時預設就是 B 那套 |
| Block size | 延遲緩衝，128 為預設值 |

快捷鍵不再是「開/關效果」，而是**在 A（普通）與 B（爆麥）兩套完整設定之間切換**：

- **A 普通**：預設為乾淨人聲（可加 Mic boost）
- **B 爆麥**：預設把 Drive 拉高、做失真

兩套各自獨立，所以你可以把 A 設成「平常講話」、B 設成「爆麥」，按一下快捷鍵就互換。

設定完成後按 **Validate** 確認，再按 **Start** 開始路由。

在 Discord 或遊戲裡，把麥克風輸入改成 `CABLE Output`，之後按快捷鍵即可在普通／爆麥之間切換。視窗的 **Live** 會顯示目前是哪一套生效。

注意：
`Input mic` 不要選 `CABLE Output`，`Output target` 也不要和 `Input mic` 選同一條 VB-CABLE 的另一端。這樣等於把同一條虛擬線自己接回自己，程式會直接擋下。

## Config

設定存在 `config.json`（位於 `Eargrape.exe` 旁邊），也可以直接編輯：

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

- `input_device`：`null` 表示自動選擇預設裝置，也可填裝置名稱或 index
- `blocksize`：越小延遲越低但越不穩定，有雜音就改 `256`
- `exclusive_wasapi`：獨佔模式可降低延遲，但其他 app 無法同時使用該裝置
- `start_pressed`：`true` 表示啟動時預設就是 B（爆麥）那套
- `profile_a` / `profile_b`：快捷鍵切換的兩套設定。每套各有：
  - `name`：顯示名稱（GUI 與狀態列會用，例如「普通」「爆麥」）
  - `distortion_mode`：`soft_clip` 或 `hard_clip`
  - `drive`：失真強度（`1.0` 幾乎無失真）
  - `mic_gain`：麥克風放大量（`1.0` 表示不放大）
  - `post_gain`：效果後的音量補償
  - `mix`：乾濕比，`0.0` 為純原音、`1.0` 為全失真
  - `noise_gate`：雜訊閘門門檻（`0.0` 關閉）
- `mix` 與 `noise_gate` 只能在 `config.json` 編輯（GUI 未提供）

> 舊版的扁平 `config.json`（含 `drive`、`start_enabled` 等頂層欄位）會在載入時**自動轉成上面的新格式**：舊效果設定變成 `profile_b`，`profile_a` 自動補成乾淨版並沿用舊的 `mic_gain`。下次存檔即升級。

## 降低延遲

- 先使用 `Windows WASAPI`
- `samplerate` 保持 `48000`
- `blocksize` 從 `128` 開始，穩定的話可試 `64`，有問題就改 `256`

如果 `WASAPI` 在你的裝置上不穩，Eargrape 會自動退到 `Windows DirectSound` 或 `MME`，通常延遲會稍高，但相容性較好。

## 疑難排解

- 麥克風沒出現在清單 → 檢查 Windows 麥克風隱私權設定
- 虛擬音效卡沒出現 → 重新安裝 VB-CABLE 驅動後重整裝置清單
- 聲音有雜音或斷音 → 把 `blocksize` 改成 `256`
- 聲音太小 → 先拉高 `Mic boost`，再視情況調整 `Effect gain`
- 啟動後顯示相容模式 → 代表 `WASAPI` 不穩，已自動退到較穩的模式
- 出現「same VB-CABLE」錯誤 → 代表你把同一條 VB-CABLE 的兩端互接了
- 快捷鍵和其他程式衝突 → 在 GUI 重新錄製或直接修改 `config.json`
- exe 找不到設定 → 確認 `config.json` 在 `Eargrape.exe` 旁邊
