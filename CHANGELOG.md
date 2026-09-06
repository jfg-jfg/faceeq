# Changelog

所有重要变更记录于此。格式参考 Keep a Changelog；版本遵循语义化（首发从 0.1.0 起）。

## [0.1.0] — 2026-09-06

首个公开版本。

### 核心
- **表情情绪 EQ**：全局 gain + per-emotion 增强/抑制（-1..1）+ 跨参数耦合
  （Duchenne 眼笑追嘴笑、悲眉追嘴角下垂），滑块实时生效；
- **双路径情绪引擎**：无 profile 走 legacy 硬编码（no-regression 守卫），
  校准 profile 走 per-face 增益 + 死搭档重分配 + 量程统一（11 表情校准向导）；
- **自定义复合表情**：基础情绪加权组合（如「害羞」），滑块实时激活，随预设保存；
- **手机面捕**：iFacialMocap/MeowFace 兼容 UDP 源（TrueDepth 救活 webcam 读不到的
  sad/disgust，且不占摄像头）。

### 输出（跨引擎）
- **VTS (Live2D)**：WebSocket 注入（默认参数 + capability-aware 自定义参数 +
  断线指数退避重连 + 情绪触发热键）；
- **VMC**：OSC bundle 发放大后 ARKit 52 blendshape（Warudo/VNyans/VSeeFace/VRM 系）；
- **OSC 自定义**：prefix 模式 + `osc_mapping.json` 精确映射。

### 体验
- PySide6 控制面板（深色高对比）：输出目标切换、信号监视器、高级塑造
  （Live2D + BlendShape 双标签矩阵 + 耦合开关 + 试表情）、★ 内置 8 人设预设、
  预设 v2（塑造+自定义表情）、首启动引导、音量/亮度语音情绪（实验）。

### 分发
- PyInstaller onedir 打包（`probes/build_release.py`），免 Python 运行；
- 冻结感知资源路径（模型/内置预设随包定位）。

### 已知限制
- 普通摄像头下 sad/disgust 不可用（RGB 对细微 AU 物理性欠读）——用手机面捕路线；
- 模型 rig 是表情上限；VTS 侧需关掉自带摄像头跟踪；
- 打包体积 ~380MB（mediapipe）。
