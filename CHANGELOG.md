# Changelog

所有重要变更记录于此。格式参考 Keep a Changelog；版本遵循语义化（首发从 0.1.0 起）。

## [0.2.0] — 2026-09-07

**纯协议 EQ 中间件**：FaceEQ 不再做面捕，只做 EQ 层——「任何面捕 ↔ FaceEQ ↔ 任何引擎」。

### 架构（breaking）
- **EQ 单趟换轴**：EQ 只作用在 ARKit blendshape 空间，Live2D 参数 = EQ 后 bs 的映射
  产物（删 Live2D 空间平行放大 `amplify`/`PARAM_CONFIG`/`COUPLING`，塑造对话框只剩
  单 BlendShape 矩阵）；
- **删除本地面捕**：mediapipe/webcam 采集、模型文件、CLI `--source webcam`、GUI 摄像头
  下拉全部移除——安装包 340MB → 约 160MB，摄像头冲突、RGB 欠读免责声明随之消失；
- **平滑收进核内**（`core.Pipeline.step`，状态显式），worker 变薄壳；
- **多输出并发**：输出目标从单选变勾选组（VTS/VMC/OSC 任意组合同时发）；
- **VMC 输入（新）**：接收 VSeeFace/Warudo 等 PC 追踪软件的 VMC blendshape 流
  （端口 39539）；VTS 重连逻辑收回适配器内部。

### 修复 / 调权
- **signals 调权**：皱鼻时压制 angry（TrueDepth 实测皱鼻伴随皱眉，angry 0.88 曾盖过
  disgust 0.64 → 现 disgust 抢回主导）；
- **打包版校准修复**：frozen exe 的「校准」按钮此前会误拉起第二个 GUI，现走内嵌校准模式。

### 兼容性
- 旧预设 v2 的 `param_boosts`/`couplings`（Live2D 空间）加载时静默忽略，
  EQ 增益/`bs_boosts`/自定义表情照常继承；塑造效果与 v0.1.0 存在可感知的细微差异。

### 验收（docs/acceptance-sprint1.md）
- iPad TrueDepth 离线实测：撇嘴 sad=0.82、皱鼻 disgust=0.64、微笑 happy=1.00——
  「TrueDepth 下 sad/disgust 可用」有实测背书。

## [0.1.0] — 2026-09-07

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

### 修复
- 手机面捕断流/未连接时 worker 忙循环烧 CPU（实测空转上万 fps、FPS 显示异常）——
  断流空帧路径加 ~30fps 节流（`probes/phone_smoke.py` 新增回归断言）。

### 已知限制
- 普通摄像头下 sad/disgust 不可用（RGB 对细微 AU 物理性欠读）——用手机面捕路线；
- 模型 rig 是表情上限；VTS 侧需关掉自带摄像头跟踪；
- 打包体积 ~340MB（mediapipe，已裁剪不用的 Qt 组件）。
