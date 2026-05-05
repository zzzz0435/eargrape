# Eargrape

透過快捷鍵即時切換爆麥效果的 Windows 麥克風路由工具。

```
真實麥克風 → Eargrape（失真效果）→ 虛擬音效卡輸入 → Discord / 遊戲讀取虛擬音效卡輸出
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
| Host API | 保持 `Windows WASAPI` |
| Hotkey | 點「Record」後按下想要的快捷鍵，或直接手打（例如 `f8`） |
| Distortion | `soft_clip` 較圓潤，`hard_clip` 較破碎刺耳 |
| Drive | 失真強度，數字越大越爆 |
| Output gain | 失真後的音量補償 |
| Block size | 延遲緩衝，128 為預設值 |

設定完成後按 **Validate** 確認，再按 **Start** 開始路由。

在 Discord 或遊戲裡，把麥克風輸入改成 `CABLE Output`，之後按快捷鍵即可切換爆麥效果。

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
  "start_enabled": false,
  "distortion_mode": "soft_clip",
  "drive": 18.0,
  "post_gain": 0.32,
  "mix": 1.0,
  "noise_gate": 0.0
}
```

- `input_device`：`null` 表示自動選擇預設裝置，也可填裝置名稱或 index
- `blocksize`：越小延遲越低但越不穩定，有雜音就改 `256`
- `exclusive_wasapi`：獨佔模式可降低延遲，但其他 app 無法同時使用該裝置
- `start_enabled`：`true` 表示啟動時效果預設開啟

## 降低延遲

- 兩個裝置都使用 `Windows WASAPI`
- `samplerate` 保持 `48000`
- `blocksize` 從 `128` 開始，穩定的話可試 `64`，有問題就改 `256`

## 疑難排解

- 麥克風沒出現在清單 → 檢查 Windows 麥克風隱私權設定
- 虛擬音效卡沒出現 → 重新安裝 VB-CABLE 驅動後重整裝置清單
- 聲音有雜音或斷音 → 把 `blocksize` 改成 `256`
- 快捷鍵和其他程式衝突 → 在 GUI 重新錄製或直接修改 `config.json`
- exe 找不到設定 → 確認 `config.json` 在 `Eargrape.exe` 旁邊
