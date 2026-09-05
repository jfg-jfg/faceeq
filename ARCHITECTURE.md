# FaceEQ 架构

FaceEQ = VTuber 表情 EQ 过滤器：实时面捕 → 按情绪差异化放大/抑制 → 经 VTube Studio WebSocket API 注入 → VTS 渲染用户模型。开源、本地处理、无遥测。

## 管线

```
捕捉源（open_source 工厂）：webcam Capture(mediapipe) | 手机 PhoneCapture(iFacialMocap/MeowFace UDP)
  → engine.process_frame（同时产出 Live2D 参数空间 + ARKit blendshape 空间）
  → mapping.base_map(特征→Live2D参数；头部姿态/眼球优先手机直传，无则特征点几何)
  → emotions.signals(检测情绪) → emotions.amplify / bs_amplify(gain+boost+coupling)
  → Smoother(EMA消抖) → 输出层 output.py（VTS 注入 | VMC blendshape | 自定义 OSC）
```

GUI (gui.py) 在 QThread 里跑这个循环，滑块实时调参数；CLI (main.py) 单线程跑同逻辑（经 engine.process_frame 共用）。

## 模块

| 模块 | 职责 |
|---|---|
| `faceeq/capture.py` | 捕捉源：open_source 工厂；Capture(mediapipe blendshape+478点) | PhoneCapture(iFacialMocap/MeowFace UDP：52 bs+头旋转+眼球，断流超时→空帧) |
| `faceeq/mapping.py` | base_map：52 blendshape + 478 landmarks → 13 Live2D 参数；RANGES 量程 |
| `faceeq/emotions.py` | signals：blendshape → 5 情绪强度（EMFACS 规则）；amplify：per-emotion boost + 耦合（Live2D 空间）；bs_amplify：同构放大（ARKit blendshape 空间，VMC/OSC 输出）；Shaping：用户可调塑造配置（默认=硬编码基线，序列化进预设/profile）；apply_custom：自定义复合表情加权注入 |
| `faceeq/output.py` | 输出适配层：OutputAdapter 接口 + VTSOutput(包装 VTSBridge) / VmcOutput(OSC bundle 发 /VMC/ext/blend/val ARKit 字符串名，默认 39540) / OscRawOutput(prefix 或 osc_mapping.json 映射，默认 9000)；create_output 工厂 |
| `faceeq/voice.py` | 语音情绪引擎（实验）：sounddevice 麦克风 → 能量/频谱质心 → 规则偏置（快攻慢放 EMA）；纯函数可测，VAD 门限安静时零偏置 |
| `faceeq/hotkeys.py` | 情绪→VTS 热键触发：配置消毒/持久化 + decide_triggers 纯函数（阈值+冷却） |
| `faceeq/profile.py` | 校准 profile（JSON）：au_gains/neutral/dead/emotion_scale；load/resolve/write |
| `faceeq/smooth.py` | Smoother：per-param EMA（对口型减半）；set_strength 实时改 |
| `faceeq/vts_bridge.py` | VTSBridge：WebSocket 连接/鉴权/发现/自建参数(capability-aware)/注入/重连 |
| `faceeq/engine.py` | process_frame：共享逐帧核心（capture→base_map→signals→amplify） |
| `faceeq/render.py` | Live2DRenderer：开发用 glfw 预览（Haru）；产品路径不用 |
| `gui.py` | PySide6 控制面板（滑块+预设+校准+VTS注入）；FaceEQWorker QThread |
| `main.py` | CLI 入口（自动化/调试）；首跑自动校准 |

## 情绪信号系统（emotions.py）

**双路设计**：
- `_emo_legacy(raw)`：无 profile 路径（硬编码默认，含 SAD_FROWN_GAIN/SAD_BROWIN_GAIN）。
- `_emo_gained(g, live)`：profile 路径。`gained = (raw − neutral) · gain`；死搭档重分配；除 emotion_scale → 0..1。

**共享子公式**（防漂移）：`_happy`/`_disgust`/`_sad` + 常量（SQUINT_COEFF/JAW_DEADZONE/ANGRY_W/SURPRISED_W/SAD_W/DISGUST_W）。

**量程统一**：`compute_emotion_scale(dead, target_delta)` 按 `_MAX_POSE`（每情绪的 max 脸 AU 映射）预算每情绪满量程 → `_emo_gained` 除 scale → 各活情绪在用户 max 脸都≈1.0、跨情绪可比。

**死搭档重分配**：angry 按 live 权重归一（press 死→全归 browDn）；surprised 在 eyeWide+browUp 都死时靠 jaw 映射满量程。

**耦合（COUPLING 表）**：
- happy → 眼笑(AU6) 追 嘴笑(AU12) = Duchenne。
- sad → 内眉抬(AU1) 追 嘴角下垂(AU15)（webcam 上因检测盲而空转）。
- `must_beat`：sad 须≥怒/厌 才开火（防 frown 共享串味）。
- 只抬不压；乘 persona `eg` 负增益停摆。

## 校准/profile 系统

**向导** (`probes/calibrate.py`)：单 cv2 窗（左摄像头 + 右 PIL 中英文提示面板），11 pose（neutral + 10 AU），SPACE 采样 ~1s 均值 → 算 au_gains（每 AU max 归一到 target_delta=0.5）→ 写 `profiles/calibration.json`。

**profile schema**：`au_gains`(null=dead)、`neutral`、`dead`、`target_delta`、`emotion_scale`（resolve 时预算）、`captures`、可选 `shaping`（塑造配置，缺省=默认）、passthrough(global_gain/smooth/emotion_gains=null)。

**resolve 优先级**：CLI > profile > 代码默认。

**GUI 校准**：CalibrateRunner 跑 QThread（不阻塞 GUI）→ subprocess calibrate.py → 完成后重载 profile。

## GUI 架构（gui.py）

- **PySide6 + QSS**：VTS 风格深色蓝高亮（#252a35/#4a9eff/圆角）。
- **FaceEQWorker(QObject)**：QThread 跑 engine.process_frame 循环 + Smoother + VTSBridge.inject + VTS 重连（3 次指数退避）。emit status/dominant/fps/error/finished。
- **Params(threading.Lock)**：GUI 写、worker 读；滑块拖动实时改（不用重启）。
- **预设系统**：`presets/<name>.json` 存 EQ 快照（gain+emotions+smooth；v2 另含 shaping 塑造配置，旧预设兼容）；GUI 下拉加载 + 存/删（覆盖/新建选项）；名字消毒。
- **高级塑造（ShapingDialog，非模态）**：参数×情绪 boost 矩阵 + 耦合开关/强度 + 一键恢复默认 + 试表情按钮（engine 参考底 pose + 合成情绪 1.5s，不照镜子预览）；改动即时写 Params。
- **自定义复合表情**：`custom_expressions.json`（随仓库预置示例）存定义 {名字: {基础情绪: 权重}}，GUI 每定义一行滑块（激活度 0..1）+ 新建/编辑/删除；激活时 additive 注入情绪向量（persona 负增益语义沿用），注入强度盖过检测时状态栏显示自定义名；定义随预设 v2 携带。
- **语音情绪（实验）**：GUI 组（开关/麦克风设备/灵敏度/影响强度），worker 内 VoiceCapture 按需启停；偏置走 engine voice_bias additive 通道。
- **情绪触发**：⌨ 对话框 per-emotion（启用/阈值/冷却/热键下拉，热键列表 worker 连 VTS 后自动发现）；配置 hotkey_triggers.json；worker 逐帧 decide_triggers → adapter.trigger_hotkey（仅 VTS 输出）。
- **CalibrateRunner(QObject)**：QThread subprocess，不阻塞 GUI；透传退出码分档提示（完成/崩溃/未生成 profile）。
- 情绪滑块 init 0（0=不塑造），精度 0.01。

## VTS 集成（vts_bridge.py）

- WebSocket `ws://localhost:8001`；token 鉴权（`AuthenticationTokenRequest` → 弹窗 → 存盘复用）。
- `InjectParameterDataRequest` mode=set 逐帧注入 → 覆盖 VTS 跟踪源（每秒至少一次）。
- 注入 VTS 默认输入参数（FaceAngleX/MouthSmile/BrowLeftY…，语义变换）+ 4 个自建自定义参数（faceeqEyeSmile/BrowForm/MouthFrown/BrowDown）。
- **capability-aware**：`discover_model_params()`（Live2DParameterListRequest）→ 只创建模型有对应 Live2D 参数的自定义参数。
- **VTS 红线**：用户须在 VTS 参数映射里设 平滑=0、倍率=1（faceamp 已做 gain+EMA，VTS 再叠=双级串联）。
- `_send` 超时 / `inject` 连接类失败均 raise ConnectionError → GUI worker 重连逻辑触发（指数退避 3 次）；CLI 捕获后提示掉线并继续跑。
- 摄像头冲突：FaceEQ + VTS 同抓摄像头 → 1fps。FaceEQ 独占（VTS 摄像头设 None）= 满速。

## webcam 限制 / 手机源

RGB 摄像头（mediapipe blendshape）对细微 AU 严重欠读：
- **可用**：happy（smile/squint）、surprised（jawOpen/eyeWide）、angry（browDn）。
- **不可用**：sad（frown/browIn 死）、disgust（sneer 死）。
- **手机面捕路线（已实现）**：iFacialMocap(iOS)/MeowFace(Android) 兼容 UDP 源
  （`PhoneCapture`，见 docs/phone-tracking.md）——TrueDepth 能读 AU15/AU1/AU9，
  sad/disgust 预期复活；且不占摄像头，冲突消失。head pose/眼球直取手机旋转数据（更准）。

## 开发工具（probes/）

| 文件 | 用途 | 运行时? |
|---|---|---|
| `calibrate.py` | 校正向导（GUI/CLI 共用） | ✅ 必需 |
| `profile_smoke.py` | 回归测试（无摄像头） | 开发 |
| `signal_probe.py` | 实时 AU 值显示（调试用） | 开发 |
| `camera_conflict_probe.py` | 摄像头共享冲突诊断 | 开发 |
| `vts_probe.py` | VTS 参数发现 + 正弦扫描 | 开发 |
| `blendshape_latency.py` / `fps_diagnostic.py` | 性能基准 | 开发 |
| `render_probe.py` | Live2D 渲染验证 | 开发 |
| `fetch_sample_model.py` | 下载 Haru 模型 | 一次性 |
