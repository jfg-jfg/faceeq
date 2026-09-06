# FaceEQ v0.2.0 规格:纯协议 EQ 中间件

> 冲刺②的工作契约。共识背景见会话定稿;本文件落地到模块/接口/文件级。
> 原则:**搬家不是重写**——被五个 smoke 钉死的逻辑只挪位置不改算法;允许的语义变更
> 仅限本文件明确列出的「行为变更」节。

## 1. 产品定义

纯协议表情 EQ 中间件:「任何面捕 ↔ FaceEQ ↔ 任何引擎」。

- **输入**(全部协议):iFacialMocap/MeowFace UDP、**VMC 输入(新)**;
- **输出**(可多选并发):VTS / VMC / 自定义 OSC;
- **EQ 只作用于 ARKit blendshape 空间**;Live2D 参数 = EQ 后 bs 的映射产物;
- 硬边界:VTS 不能当输入(不外发跟踪数据);
- 不自带面捕:mediapipe/webcam 全部移除。

## 2. 数据流

```
InputAdapter(phone UDP │ VMC 输入)
  → Frame{bs52 原始, rot, eye}            # lms/img 字段删除
  → Pipeline.step(frame, cfg, state)      # 唯一逐帧入口;状态显式传入
     ① signals(bs 原始, calib) → emo     # 永远吃原始 bs,防 EQ 回灌
        + apply_custom + voice_bias      # 不变
     ② bs_amplify(bs 原始, emo) → bs'    # EQ 唯一发生地
     ③ base_map(Frame(bs', rot, eye))    # 映射后置;rot/eye 直传,几何回落删除
        → Live2D 参数(未平滑)
     ④ Smoother(核内持有):bs' → bs_out;params → params_out
        # EMA 线性 ⇒ 先平滑后映射 ≡ 先映射后平滑;嘴部减半规则留在参数侧
  → StepResult{params_out, bs_out, emotions, dominant, face_found}
  → worker 把结果发给【所有启用的】OutputAdapter(多输出并发)
```

## 3. 目标模块结构

```
faceeq/
  __init__.py        # resource_path / __version__(原样)
  frame.py           # Frame 数据类(bs/rot/eye);lms/img 删
  core.py            # PipelineConfig/PipelineState/Pipeline.step(替代 engine.py;
                     #   平滑状态在 state,调用方持有 state 生命周期)
  mapping.py         # base_map(bs',rot,eye);特征点几何分支删
  emotions.py        # signals*/bs_amplify/coupling/apply_custom/dominant/reference_* 留;
                     #   amplify()(Live2D 空间放大)删
  smooth.py          # Smoother 原样
  profile.py         # 原样(au_gains 喂 signals 不变)
  voice.py           # 原样
  hotkeys.py         # 原样
  inputs/
    __init__.py      # InputAdapter 接口:label/start/read()→Frame/is_stale/release
                     # + create_input(kind, **kw) 工厂
    phone.py         # PhoneCapture 迁入(iFacialMocap/MeowFace;握手/断流节流/signs 常量)
    vmc.py           # 新:VMC 输入(监听 /VMC/ext/blend/val|apply + /VMC/ext/face/pos
                     #   → Frame{bs,rot};默认端口 39539,避开自家 39540 输出)
  outputs/
    __init__.py      # OutputAdapter + create_output 迁入
    vts.py           # VTSOutput;重连(指数退避)收回适配器内部
    vmc.py           # VmcOutput 原样
    osc.py           # OscRawOutput 原样
gui/                 # gui.py(65KB)拆包
  __init__.py        # app 入口(main)
  main_window.py     # 布局/滑块/预设
  worker.py          # 薄循环:input.read → Pipeline.step → 各 output.inject
  params.py          # Params(锁)+ 统一 app 配置持久化
  dialogs/           # shaping(单 BS 矩阵)/hotkeys/custom/calibrate/wizard
main.py              # CLI 薄壳(参数面随输入/输出重构更新)
```

**删除清单**:`faceeq/capture.py`(拆解后删)、`faceeq/engine.py`、`faceeq/render.py`
(无 webcam 的本地 Live2D 预览失去意义)、`models/`、CLI `--source webcam`、GUI 摄像头下拉、
依赖 `mediapipe` + `opencv-python`(cv2 仅剩 dev 探针用,不入产品 requirements)。

## 4. 行为变更(相对 v0.1.0)

| 变更 | 说明 |
|---|---|
| EQ 单趟 | Live2D 参数 = base_map(bs'),塑造效果与 v0.1.0 有**可感知的细微差异**;smoke 断言按新管线重录 |
| 塑造 UI | 双标签矩阵 → 单 BlendShape 矩阵;旧预设 v2 的 `live2d boosts` 加载时**静默忽略**,EQ 增益/bs_boosts/自定义表情照常继承 |
| 多输出 | 单选下拉 → 勾选组;VTS+VMC+OSC 任意组合同时发 |
| 首启动引导 | 「选摄像头→校准→开始」→「装面捕 app(带下载链接)→ FaceEQ 选源 → 开始」 |
| 包体 | ~340MB → 目标 ≤120MB(mediapipe/opencv 出库后实测) |
| 版本 | v0.2.0(breaking);CHANGELOG 独立小节 |

## 5. 依赖变化(requirements)

```
保留:websocket-client, python-osc, Pillow, PySide6, sounddevice, numpy(voice.py)
移除:mediapipe, opencv-python(产品运行);FaceEQ.spec 删 models add-data 与
      collect_all('mediapipe')
```

## 6. i18n(冲刺③,列此备查)

GUI 字符串全部 `self.tr()` 包裹;PySide6 Linguist(.ts/.qm);zh 源 en 译;
系统语言跟随 + 手动切换下拉。放架构冻结之后做,避免字符串改两遍。

## 7. smoke 重算计划

| smoke | 影响 | 动作 |
|---|---|---|
| profile_smoke | signals 不变,断言基本不动 | 跑一遍核对 |
| phone_smoke | base_map 吃 bs'(值同序) | 断言值重算;(g) 断流节流保留 |
| output_smoke | amplify 删除:Live2D 参数断言改为「EQ 后映射」新真值;VMC/OSC 断言不变 | 重算重录 |
| gui_smoke | 摄像头下拉→输入源下拉;输出下拉→勾选组 | 控件断言改写 |
| voice_smoke | 不受影响 | 回归即可 |
| **新增** | vmc_input 探针:伪造 VMC 发送端 → Pipeline 断言 bs'/rot | 新写 |

## 8. 验收标准(冲刺②完成定义)

1. 六个 smoke 全 PASS(含新 vmc_input);
2. 干净环境语义冒烟:exe 启动 → 三步引导 → 手机源数据流 → 多输出勾选 → VMC 包抓取;
3. exe ≤120MB;无 mediapipe/opencv 残留(`_internal` 检查);
4. 端到端:VSeeFace(PC webcam)→ VMC 输入 → FaceEQ → VTS + VMC 双输出同时工作;
5. 文档改口完成:README/quickstart/outputs/faq 全部按纯协议定位重写,宣传语带冲刺①实测数据。

## 9. 排期与依赖

- 冲刺①(验收卡 `docs/acceptance-sprint1.md`,用户执行)与规格/重构并行,互不阻塞;
- 冲刺②内顺序:inputs/core(管线换轴)→ outputs 多并发 → gui 拆包 → 引导/文档 → 构建;
- 冲刺③ i18n 在②冻结后。
