# FaceEQ

实时人脸表情**放大** + **情绪 EQ** → 驱动 Live2D 的开源 VTuber 工具（VTube Studio 插件）。

把主播的表情按情绪**差异化放大/抑制**——让小人在直播里表情更好认，或按人设压平某些情绪。
补现有 VTuber 工具（VTube Studio 等）只做 1:1 跟踪、表情「太平」的空白。

**核心：FaceEQ = 你表情的情绪 EQ**
- 全局放大（拖滑块）让表情更夸张；
- per-emotion 增强/抑制（拖到 +1 放大、拖到 -1 压成扑克脸 = persona）；
- 跨参数耦合（笑时眼笑追嘴笑 = Duchenne 真笑；VTS 静态滑块结构上做不到）。

**宿主 = VTube Studio**：FaceEQ 把放大后的参数经 VTS 公开 WebSocket API 注入，由 VTS
渲染**你自己的模型**（FaceEQ 模型无关）。FaceEQ 是独立 GUI 控制面板（深色蓝高亮，VTS 风格）。

## 上手

> Python 3.9–3.12（MediaPipe 不支持 3.13/3.14）。需 VTube Studio + 摄像头。

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**① 校准（按你的脸）**：照向导做 11 个表情（中英文提示 + 实时值），自动生成你的增益 profile。
GUI 里点「校准」按钮，或手动跑：
```bash
PYTHONUTF8=1 .venv\Scripts\python.exe probes\calibrate.py
```
详见 [docs/calibration.md](docs/calibration.md)。

**② 接入 VTube Studio**：[docs/vts-setup.md](docs/vts-setup.md)（连接、参数映射、红线）。
**注意**：VTS 里把摄像头跟踪关掉（Camera → None/Off），让 FaceEQ 独占摄像头。

**③ 运行（推荐 GUI）**：
```bash
PYTHONUTF8=1 .venv\Scripts\python.exe gui.py
```
GUI 面板：拖滑块实时调每情绪增强/抑制 + 全局 gain + 平滑；点「开始」注入 VTS（会先提示
关掉 VTS 摄像头）；「校准」呼出向导。运行中拖滑块即时生效。

CLI 保留给自动化/调试：
```bash
PYTHONUTF8=1 .venv\Scripts\python.exe main.py --vts --no-preview --happy 1.0 --angry -0.5
```

## 文档
- [校准与 profile](docs/calibration.md) —— per-face 增益向导、profile 格式
- [VTube Studio 接入](docs/vts-setup.md) —— 连接授权、参数映射、平滑/倍率红线

## 状态
开发中。webcam 版**可用情绪**：happy / surprised / angry；sad / disgust 在普通 RGB 摄像头
上检测不到（细微 AU 严重欠读，非权重问题），等 iPhone/深度检测路线。设计细节见各 docstring
与 `docs/`。本项目只做本地处理，**无遥测、不发送任何数据**。
