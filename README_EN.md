# FaceEQ

**Real-time facial expression "emotion EQ" → drive your VTuber model (Live2D / 3D). Open source, fully local, no telemetry.**

Amplify or suppress the streamer's expressions *differently per emotion* — make your avatar more readable and expressive, or flatten emotions to fit a persona. Fills the gap left by tools that only do 1:1 tracking and leave expressions feeling "flat".

## Features

- **Emotion EQ**: global gain + per-emotion boost/suppression sliders (+1 amplify, −1 poker-face persona), live while streaming;
- **Cross-parameter coupling**: eye-smile follows mouth-smile when happy (Duchenne smile), inner-brow follows mouth-corners when sad — emotion-conditioned linking that independent sliders can't do;
- **Custom composite expressions**: define "shy" = happy 0.3 + surprised 0.4, activate with a slider, save into presets;
- **Persona presets**: switch Genki / Cool / Poker-face / Tsundere… with one click (8 built-in ★ presets);
- **Voice emotion (experimental)**: speaking volume/timbre biases expressions — stay expressive when your face is covered;
- **Emotion-triggered hotkeys (VTS)**: laughter over threshold → auto sticker/expression (threshold + cooldown);
- **Per-face calibration**: 11-pose wizard measures per-AU gains for *your* face;
- **Phone tracking**: iFacialMocap (iOS) / MeowFace (Android) over UDP — TrueDepth revives sad/disgust that webcams can't read.

## Multi-app output (not locked to one tool)

| Output | Works with | Channel |
|---|---|---|
| **VTS (Live2D)** | VTube Studio | WebSocket parameter injection |
| **VMC** | Warudo, VNyan, VSeeFace, VRM/Unity/UE apps | amplified ARKit blendshapes (OSC/UDP 39540) |
| **Raw OSC** | VRChat (via FT bridge), any OSC receiver | configurable name mapping |

Inputs are equally free: a normal webcam or a phone app.

## How it relates to other tools

| You want | Suggestion |
|---|---|
| Just make expressions bigger | VTS built-in parameter range remap is enough — skip FaceEQ |
| Emotion-differentiated expressions / persona switching / genuine-smile coupling | **FaceEQ** (that's why it exists) |
| iPhone 52 blendshapes into Live2D custom params (re-rig) | VBridger (paid) / Vitamins |
| Phone tracking + 3D model + emotion amplification | FaceEQ (VMC out) + iFacialMocap/MeowFace |

Honest note: **your model's rig is the ceiling** — a stiff rig stays small even when amplified.

## Getting started

> Windows 10/11; Python 3.10–3.12 (MediaPipe doesn't support 3.13/3.14).

**Option A (recommended)**: download `FaceEQ.zip` from Releases → unzip → run `FaceEQ.exe`.
First launch shows a guide: pick camera → calibrate (~2 min) → press Start.

**Option B (from source)**:

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
set PYTHONUTF8=1
.venv\Scripts\python.exe gui.py
```

CLI for automation/debugging: `main.py --output vts|vmc|osc --phone`, see `main.py --help`.
(Chinese docs: [docs/](docs/); architecture in [ARCHITECTURE.md](ARCHITECTURE.md).)

## Status & privacy

In development. On webcam, reliable emotions: happy / surprised / angry; sad / disgust need the
phone-tracking route (fine AUs are physically under-read by RGB cameras — implemented, see phone docs).
Everything runs locally: **no telemetry, nothing leaves your machine**. MIT licensed —
stars and sponsorships appreciated.
