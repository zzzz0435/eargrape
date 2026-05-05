# Eargrape

`Eargrape` is a minimal Windows microphone router for one job only:

- capture your mic
- apply a single nonlinear distortion effect
- send the result to a target output device
- toggle the effect with a global hotkey
- ship as a simple Windows GUI app or a single-file `.exe`

The intended routing is:

`real microphone -> Eargrape -> virtual cable input -> Discord / game reads virtual cable output`

## Why this shape

For voice-chat style use, the simplest practical approach is not to write a virtual microphone driver first. Existing projects like [Figaro](https://github.com/MattMoony/figaro) and [TTS Voice Wizard's virtual cable guide](https://github.com/VRCWizard/TTS-Voice-Wizard/wiki/Virtual-Cable) use the same routing model: process audio in user space and send it into a virtual cable device.

This MVP uses [`sounddevice`](https://github.com/spatialaudio/python-sounddevice), which wraps PortAudio on Windows/Linux/macOS. That keeps the code small while still letting us run a callback-based real-time audio stream.

## Scope

Included:

- one global hotkey
- one distortion effect
- low-latency callback routing
- simple Windows GUI
- single-file `exe` packaging

Not included:

- extra effects
- monitoring mix
- tray icon
- automatic device switching
- virtual microphone driver

## Quick start

1. Install Python 3.12+.
2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Install a virtual audio cable. Example: [VB-CABLE](https://vb-audio.com/Cable/).
4. Start the GUI:

```powershell
python eargrape_gui.py
```

5. In the window:
   - choose your real microphone as `Input mic`
   - choose your virtual cable playback side as `Output target`, usually `CABLE Input`
   - keep `Host API` on `Windows WASAPI` if possible
   - choose a hotkey such as `F8`
   - press `Validate`, then `Start`
6. In Discord or your game, set the microphone/input device to the virtual cable recording side, usually `CABLE Output`.

## CLI tools

Useful for troubleshooting:

```powershell
python eargrape.py --list-devices
python eargrape.py --validate-config
```

## Build EXE

This repository includes a PyInstaller build script and already produced one local build at [dist/Eargrape.exe](/C:/Users/ITRI/Desktop/eargrape/dist/Eargrape.exe).

To rebuild:

```powershell
.\build.ps1
```

The result is a single-file GUI executable:

```text
dist\Eargrape.exe
```

The app stores `config.json` next to the executable when running as a packaged build. That keeps the setup friendlier for self-use or sharing with a few friends.

## Manual setup

If you want to inspect devices before using the GUI:

```powershell
python eargrape.py --list-devices
```

Then edit [config.json](C:/Users/ITRI/Desktop/eargrape/config.json) and set:
   - `input_device` to your microphone name or index
   - `output_device` to your virtual cable playback side, usually `CABLE Input`
   - `hostapi` to `Windows WASAPI`
Validate the config before streaming:

```powershell
python eargrape.py --validate-config
```

Start Eargrape from CLI:

```powershell
python eargrape.py
```

## Config

Default [config.json](C:/Users/ITRI/Desktop/eargrape/config.json):

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

Notes:

- `input_device`: `null` means "best default match under the selected host API".
- `output_device`: string match or numeric index.
- `blocksize`: smaller is lower latency but less stable. Start with `128`. If it crackles, move to `256`.
- `exclusive_wasapi`: can reduce latency, but shared mode is safer for the first pass.
- `distortion_mode`: `soft_clip` is smoother, `hard_clip` is harsher.
- `drive`: higher means more breakup.
- `post_gain`: trims the distorted signal back down after clipping.
- `mix`: `1.0` means fully wet.

## Tuning for low latency

- Keep both devices on `Windows WASAPI`.
- Prefer `48000` Hz unless your devices clearly want something else.
- Use the same host API for both input and output.
- Start with `blocksize = 128`.
- If stable, try `64`.
- If unstable, go up to `256`.

## Limitations

- This version outputs mono voice duplicated across the target output channels.
- It assumes the target app will read from a virtual cable device.
- The packaged GUI app is convenient, but because it is built from Python it is not as small as a native C++ utility.
- It has not been end-to-end tested in this repository because the current machine shows no input-capable audio device in `sounddevice`.

## Troubleshooting

- If `--list-devices` shows outputs only and no microphone inputs, first check Windows microphone privacy permissions.
- If the virtual cable does not appear, reinstall it and run `python eargrape.py --list-devices` again.
- If audio crackles, raise `blocksize` from `128` to `256`.
- If the hotkey collides with another app, change `hotkey` in [config.json](C:/Users/ITRI/Desktop/eargrape/config.json).
- If the packaged `exe` cannot find your settings, check for `config.json` next to `Eargrape.exe`.

## References

- [Figaro](https://github.com/MattMoony/figaro)
- [TTS Voice Wizard virtual cable guide](https://github.com/VRCWizard/TTS-Voice-Wizard/wiki/Virtual-Cable)
- [python-sounddevice](https://github.com/spatialaudio/python-sounddevice)
- [miniaudio](https://github.com/mackron/miniaudio)
