# FaceEQ

**The expression "emotion EQ" middleware for VTubers: any tracker → FaceEQ → any engine. Open source, fully local, no telemetry.**

Amplify or suppress the expressions coming from your tracking software *differently per emotion* — make your avatar more readable and expressive, or flatten emotions to fit a persona. Fills the gap left by tools that only do 1:1 tracking and leave expressions feeling "flat". **FaceEQ does not do face tracking itself** — feed it from a phone/tablet app or PC tracking software, and it outputs the tuned result.

## Features

- **Emotion EQ**: global gain + per-emotion boost/suppression sliders (+1 amplify, −1 poker-face persona), live while streaming;
- **Cross-shape coupling**: eye-squint follows mouth-smile when happy (Duchenne smile), inner-brow follows mouth-corners when sad — emotion-conditioned linking that independent sliders can't do;
- **Custom composite expressions**: define "shy" = happy 0.3 + surprised 0.4, activate with a slider, save into presets;
- **Persona presets**: switch Genki / Cool / Poker-face / Tsundere… with one click (8 built-in ★ presets);
- **Voice emotion (experimental)**: speaking volume/timbre biases expressions — stay expressive when your face is covered;
- **Emotion-triggered hotkeys (VTS)**: laughter over threshold → auto sticker/expression (threshold + cooldown);
- **Per-face calibration**: 11-pose wizard measures per-AU gains for *your* face;
- **Multi-output**: feed VTS *and* Warudo at the same time with one tracker.

## Inputs / Outputs (protocol-only, not locked to one tool)

| Input | Channel |
|---|---|
| 📱 iFacialMocap (iOS, TrueDepth) / MeowFace (Android) | UDP 49983 |
| 📡 VSeeFace, Warudo and other PC trackers | VMC input (UDP 39539) |

| Output | Works with | Channel |
|---|---|---|
| **VTS (Live2D)** | VTube Studio | WebSocket parameter injection |
| **VMC** | Warudo, VNyan, VSeeFace, VRM/Unity/UE apps | amplified ARKit blendshapes (OSC/UDP 39540) |
| **Raw OSC** | VRChat (via FT bridge), any OSC receiver | configurable name mapping |

## How it relates to other tools

| You want | Suggestion |
|---|---|
| Just make expressions bigger | VTS built-in parameter range remap is enough, skip FaceEQ |
| Per-emotion shaping / persona presets / Duchenne coupling / multi-output | **FaceEQ** (the reason it exists) |
| iPhone 52-blendshape → Live2D custom params (model re-rig) | VBridger (paid) / Vitamins |

Honest notes: **the model rig is the expression ceiling** — EQ amplifies what the rig already has; **subtle expressions (sad/disgust) depend on your tracker** — verified working on TrueDepth (see below), weaker on plain-RGB trackers.

## Getting started

> Windows 10/11; Python 3.10–3.12 (for source runs).

**Option 1 (recommended)**: download `FaceEQ-v0.2.0-win64.zip` from Releases → unzip → run `FaceEQ.exe`. First launch walks you through: prepare a tracker → pick input → calibrate (~2 min) → tick outputs → start. See [docs/quickstart.md](docs/quickstart.md).

**Option 2 (source)**:

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
PYTHONUTF8=1 .venv\Scripts\python.exe gui.py
```

CLI: `main.py --input phone --output vts vmc` etc. See `main.py --help`.

## Measured data (iPad TrueDepth, v0.2.0 acceptance)

Sad mouth → **sad 0.82**, nose sneer → **disgust 0.64**, smile → **happy 1.00** (live estimates from FaceEQ's own emotion engine). Full data: [docs/acceptance-sprint1.md](docs/acceptance-sprint1.md).

## Docs

- [Quickstart (中文)](docs/quickstart.md) · [FAQ / troubleshooting](docs/faq.md)
- [Outputs: VTS / VMC / OSC](docs/outputs.md) · [Phone tracking](docs/phone-tracking.md) · [Calibration](docs/calibration.md) · [VTS setup](docs/vts-setup.md)
- [Positioning (internal)](docs/positioning.md) · [Release checklist](RELEASE.md) · [Architecture](ARCHITECTURE.md)

## Status & privacy

In development (v0.2.0). Everything runs locally — **no telemetry, no data leaves your machine**. MIT licensed. Star if you like it / [sponsor link slot](RELEASE.md).
