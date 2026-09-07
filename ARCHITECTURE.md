# FaceEQ 架构

FaceEQ = VTuber 表情 **EQ 中间件**：面捕协议流 → 按情绪差异化放大/抑制 → 注入 VTS（Live2D）或 VMC/OSC（3D）。**自己不做面捕**——输入永远是现成追踪软件（iFacialMocap/MeowFace/VSeeFace/Warudo…）推来的 ARKit blendshape 流，FaceEQ 只做 EQ 层。开源、本地处理、无遥测。

## 数据流（v0.2.0 单趟管线）

```
输入适配 inputs/（iFacialMocap/MeowFace UDP │ VMC 输入）
  → Frame{bs52 原始, rot, eye}
  → core.Pipeline.step(frame, cfg, state)      ← 唯一逐帧入口，平滑在核内
     ① emotions.signals(原始 bs, calib) → 情绪向量（+自定义复合表情 +语音偏置）
        ——永远吃原始 bs，防 EQ 回灌
     ② emotions.bs_amplify(原始 bs, emo) → bs'   ← EQ 唯一发生地（boost + BS 耦合）
     ③ mapping.base_map(bs', rot, eye) → Live2D 参数（映射后置；头/眼协议直传）
     ④ Smoother（核内持有）→ 各输出空间最终值
  → worker 把 StepResult 发给所有启用的输出（多输出并发）
```

调用方（GUI worker / CLI main.py）只是薄壳：喂数帧、发结果。平滑规则在核内，
新消费端不会忘记平滑；EQ 后的 bs' 与映射出的参数都已平滑。

## 模块

| 模块 | 职责 |
|---|---|
| `faceeq/frame.py` | Frame 数据类（bs/rot/eye）——所有输入适配器的统一产出 |
| `faceeq/core.py` | PipelineConfig/PipelineState/Pipeline.step：单趟管线（替代 v0.1.0 engine.py） |
| `faceeq/mapping.py` | base_map：EQ 后 bs' + 协议 rot/eye → 13 Live2D 参数（clamp 在此） |
| `faceeq/emotions.py` | signals：blendshape → 5 情绪（EMFACS 规则，legacy/profile 双路）；bs_amplify：BS 空间 EQ（boost + BS_COUPLING 耦合）；Shaping（用户可调塑造）；apply_custom |
| `faceeq/inputs/__init__.py` | InputAdapter 接口 + create_input 工厂 |
| `faceeq/inputs/phone.py` | PhoneInput：iFacialMocap/MeowFace UDP（解析/握手/断流节流/符号常量） |
| `faceeq/inputs/vmc.py` | VmcInput：VMC 协议输入（blend/val + face/pos 四元数→欧拉；默认 39539） |
| `faceeq/outputs/__init__.py` | OutputAdapter + create_output 工厂 |
| `faceeq/outputs/vts.py` | VTSOutput：Live2D 参数注入（断线指数退避重连在适配器内） |
| `faceeq/outputs/vmc.py` | VmcOutput：ARKit blendshape → VMC bundle（UDP 39540） |
| `faceeq/outputs/osc.py` | OscRawOutput：prefix / osc_mapping.json 精确映射 |
| `faceeq/smooth.py` | Smoother：per-键 EMA（嘴部开合减半） |
| `faceeq/profile.py` | 校准 profile（JSON）：au_gains/neutral/dead/emotion_scale；load/resolve/write |
| `faceeq/voice.py` | 语音情绪引擎（实验）：sounddevice → 能量/亮度 → 规则偏置 |
| `faceeq/hotkeys.py` | 情绪→VTS 热键触发：配置消毒 + decide_triggers 纯函数 |
| `faceeq/calibrate.py` | 引导式 11 表情校准向导（probes/calibrate.py 为 CLI shim；frozen exe 内嵌） |
| `gui.py` | PySide6 控制面板：输入源/多输出勾选/滑块/预设/塑造(单 BS 矩阵)/触发/首启动引导 |
| `main.py` | CLI 薄壳（自动化/调试） |

v0.1.0 已删除：`engine.py`（Live2D 空间平行放大管线）、`capture.py`（mediapipe
webcam 采集）、`render.py`（Haru 本地预览）、`amplify()`/`PARAM_CONFIG`/`COUPLING`
（Live2D 空间 EQ——单趟化后 Live2D 参数是 EQ 后 bs 的映射产物，不再有平行放大）。

## 情绪信号系统（emotions.py）

**双路设计**（不变）：
- `_emo_legacy(r)`：无 profile 路径（硬编码默认）。
- `_emo_gained(r, live, target_delta)`：profile 路径。`gained=(raw−neutral)·gain`；
  死搭档重分配；除 emotion_scale → 0..1。

**sneer 压 angry（v0.2.0 新）**：皱鼻(AU9)原型天然伴随皱眉(AU4)，iPad TrueDepth
实测 browDown 拉满时 angry 0.88 盖过 disgust 0.64 → angry 乘 (1−0.45·sneer)，
disgust 抢回主导（验收数据见 docs/acceptance-sprint1.md）。

**BS 空间耦合（BS_COUPLING，原 Live2D COUPLING 单趟化）**：
- happy → eyeSquint(左/右) 追 mouthSmile：Duchenne 真笑。
- sad → browInnerUp 追 mouthFrown（须 sad≥angry 且 sad≥disgust 才开火）。
- 语义：只抬不压；persona 负增益时耦合自然停摆。

**量程统一 / 死搭档重分配**：不变（compute_emotion_scale + _emo_gained_raw）。

## 校准 / profile / 预设

- 校准向导（faceeq/calibrate.py）：单 cv2 窗（PIL 中英文提示），11 pose，SPACE 采样。
- profile schema 不变（au_gains/neutral/dead/target_delta/emotion_scale/shaping）。
- 预设 v2：v0.2.0 起只认 `bs_boosts`/`bs_couplings`；旧 `param_boosts`/`couplings`
  （Live2D 空间）加载时**静默忽略**，EQ 增益/自定义表情照常继承。

## GUI（gui.py，v0.2.0 将拆包）

输入源下拉（📱 手机 UDP / 📡 VMC 输入）+ 端口；输出目标**三勾选并发**
（VTS/VMC/OSC）+ 地址/端口；情绪滑块；塑造对话框=单 BlendShape 矩阵 + BS 耦合；
首启动三步引导（装面捕 app → 选源 → 校准/开始）。worker 薄循环：
`input.read → pipeline.step → 各输出 inject`；VTS 断线重连在适配器内。

## 面捕源注意

- **设备要固定**（支架）：头旋转是相对摄像头的，手持时头转不映射。
- 断流：输入适配器空帧节流 ~30fps（防 worker 空转），状态栏提示。
- VMC 输入完整 52 形状需要发送端 Perfect Sync（VSeeFace 需 PS 模型）。

## 开发工具（probes/）

| 文件 | 用途 |
|---|---|
| `calibrate.py` | 校正向导 CLI shim（实现在 faceeq/calibrate.py） |
| `phone_smoke.py` / `profile_smoke.py` / `output_smoke.py` / `gui_smoke.py` / `voice_smoke.py` | 五个回归 smoke（无摄像头/无 GL） |
| `phone_sign_probe.py` | 手机源方向符号验收探针（实时打印 rot/eye/AU/情绪） |
| `vmc_sign_probe.py` | VMC 输入验收探针（VSeeFace/Warudo 路径） |
| `fbx_peaks.py` | 二进制 FBX 混合形状曲线峰值提取（离线验收/分析） |
| `build_release.py` | PyInstaller 打包 + 打包后裁剪 |
| `vts_probe.py` | VTS 参数发现 + 正弦扫描（调试） |
