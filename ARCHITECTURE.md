# FaceEQ 架构

FaceEQ = VTuber 表情 EQ 过滤器：实时面捕 → 按情绪差异化放大/抑制 → 经 VTube Studio WebSocket API 注入 → VTS 渲染用户模型。开源、本地处理、无遥测。

## 管线

```
摄像头 → Capture(mediapipe blendshape) → engine.process_frame
  → mapping.base_map(特征→Live2D参数) → emotions.signals(检测情绪) → emotions.amplify(gain+boost+coupling)
  → Smoother(EMA消抖) → VTSBridge.inject(WebSocket set模式) → VTS → 模型
```

GUI (gui.py) 在 QThread 里跑这个循环，滑块实时调参数；CLI (main.py) 单线程跑同逻辑（经 engine.process_frame 共用）。

## 模块

| 模块 | 职责 |
|---|---|
| `faceeq/capture.py` | mediapipe FaceLandmarker → Frame(bs + lms + img)；list_sources 探测摄像头 |
| `faceeq/mapping.py` | base_map：52 blendshape + 478 landmarks → 13 Live2D 参数；RANGES 量程 |
| `faceeq/emotions.py` | signals：blendshape → 5 情绪强度（EMFACS 规则）；amplify：per-emotion boost + 耦合 |
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

**profile schema**：`au_gains`(null=dead)、`neutral`、`dead`、`target_delta`、`emotion_scale`（resolve 时预算）、`captures`、passthrough(global_gain/smooth/emotion_gains=null)。

**resolve 优先级**：CLI > profile > 代码默认。

**GUI 校准**：CalibrateRunner 跑 QThread（不阻塞 GUI）→ subprocess calibrate.py → 完成后重载 profile。

## GUI 架构（gui.py）

- **PySide6 + QSS**：VTS 风格深色蓝高亮（#252a35/#4a9eff/圆角）。
- **FaceEQWorker(QObject)**：QThread 跑 engine.process_frame 循环 + Smoother + VTSBridge.inject + VTS 重连（3 次指数退避）。emit status/dominant/fps/error/finished。
- **Params(threading.Lock)**：GUI 写、worker 读；滑块拖动实时改（不用重启）。
- **预设系统**：`presets/<name>.json` 存 EQ 快照（gain+emotions+smooth）；GUI 下拉加载 + 存/删（覆盖/新建选项）；名字消毒。
- **CalibrateRunner(QObject)**：QThread subprocess，不阻塞 GUI。
- 情绪滑块 init 0（0=不塑造），精度 0.01。

## VTS 集成（vts_bridge.py）

- WebSocket `ws://localhost:8001`；token 鉴权（`AuthenticationTokenRequest` → 弹窗 → 存盘复用）。
- `InjectParameterDataRequest` mode=set 逐帧注入 → 覆盖 VTS 跟踪源（每秒至少一次）。
- 注入 VTS 默认输入参数（FaceAngleX/MouthSmile/BrowLeftY…，语义变换）+ 4 个自建自定义参数（faceeqEyeSmile/BrowForm/MouthFrown/BrowDown）。
- **capability-aware**：`discover_model_params()`（Live2DParameterListRequest）→ 只创建模型有对应 Live2D 参数的自定义参数。
- **VTS 红线**：用户须在 VTS 参数映射里设 平滑=0、倍率=1（faceamp 已做 gain+EMA，VTS 再叠=双级串联）。
- `_send` 超时 raise ConnectionError → worker 重连逻辑触发。
- 摄像头冲突：FaceEQ + VTS 同抓摄像头 → 1fps。FaceEQ 独占（VTS 摄像头设 None）= 满速。

## webcam 限制

RGB 摄像头（mediapipe blendshape）对细微 AU 严重欠读：
- **可用**：happy（smile/squint）、surprised（jawOpen）、angry（browDn）。
- **不可用**：sad（frown/browIn 死）、disgust（sneer 死）。
- iPhone/TrueDepth 路线（待实现）将救活 sad/disgust + 消除摄像头冲突。

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
