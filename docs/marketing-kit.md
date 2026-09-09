# 营销素材包(v0.2.0)

渠道按 RELEASE.md §4。本文案可直接复制使用;`assets/` 里是现成图素材。

## 现成素材

| 文件 | 用途 |
|---|---|
| `assets/eq-demo.gif` | **核心演示 GIF**:同一份 TrueDepth 实录,左「原始 1:1」右「FaceEQ EQ(元气预设)」双面板对比(6s 循环,356KB,直接贴 GitHub README / Reddit) |
| `assets/shots/main-zh.png` / `main-en.png` | 主面板截图(B站用 zh,itch/Reddit 用 en) |
| `assets/shots/shaping-zh.png` | 高级塑造矩阵截图 |
| `assets/shots/monitor-zh.png` | 信号监视器截图 |
| `assets/_framing.png` | (内部)取景校准图,勿发布 |

**待录素材(需要你,约 10 分钟)**:见文末「真人对比 GIF 录制指引」——真人口播/真人形象
对比的转化率远高于纯 GIF;录完把原始屏幕录像给我,我用 ffmpeg 剪成 30s 版。

---

## B站视频脚本(3–5 分钟)

**标题(选一)**:
- 「让 Live2D 表情不再"死鱼眼"——免费开源表情 EQ,一键人设切换」
- 「面捕表情太木?我写了个表情均衡器(开源免费)」

**分镜**:

| 段 | 时长 | 画面 | 台词要点 |
|---|---|---|---|
| 1 钩子 | 0:00–0:15 | 左右分屏 GIF(eq-demo.gif 或真人版):左原始右 EQ | 「同样的面捕数据,右边多了一层免费开源的'表情均衡器'——它叫 FaceEQ」 |
| 2 痛点 | 0:15–0:45 | VTS 里原始面捕(平静/微弱) | 「面捕跟踪本身是 1:1 的:你笑 30%,模型就笑 30%。想要更夸张?VTS 只能给所有参数统一拉倍率——开心放大,生气也放大,没有'情绪'的区别」 |
| 3 原理 | 0:45–1:30 | 主面板截图(main-zh)+情绪滑块特写 | 「FaceEQ 的思路是 EQ:每个情绪独立滑块,+1 全量夸张、−1 压成扑克脸。还有跨形状耦合——笑的时候眼笑自动跟上(杜兴真笑),悲的时候内眉抬追嘴角下垂。这是独立滑块结构上做不到的」 |
| 4 演示 | 1:30–3:00 | 真人实录:校准→开始→拖滑块→切预设(元气/扑克脸/傲娇) | 「11 个表情校准 2 分钟,按你的脸定制增益;8 个内置人设一键切换;自定义复合表情——'害羞'=30% 开心+40% 惊讶,自己调」 |
| 5 3D/多输出 | 3:00–3:40 | Warudo 画面 + 勾选组特写 | 「不止 Live2D:VMC 输出直接喂 Warudo/VNyans,VTS 和 Warudo 还能同时喂。VSeeFace 的追踪也能当输入源」 |
| 6 上手+局限 | 3:40–4:30 | 首启动引导 + quickstart 三步 | 「exe 双击就能跑,54MB。诚实说:模型 rig 是表情上限,细表情(悲/厌)建议 TrueDepth 面捕——iPad 实测数据在简介里。链接和文档在下方」 |

**简介栏**:GitHub 链接 + 一句话定位 + 实测数据(sad 0.82/disgust 0.64)+ 「免费开源 MIT」。

---

## Reddit 帖(r/vtubertech,英文成品)

**标题**:
> I built a free, open-source "emotion EQ" that sits between your face tracker and your avatar — per-emotion boost/suppress, Duchenne coupling, multi-output (Live2D + 3D)

**正文**:

> Most tracking pipelines are 1:1 — you smile 30%, the avatar smiles 30%. VTS can remap ranges, but that's static and identical for every emotion.
>
> I wanted an *EQ*: boost happiness while suppressing sadness for a Genki persona, or flatten everything for a poker-face one. So I wrote **FaceEQ** — a local, open-source (MIT) middleware that sits between any tracker and your model:
>
> - Per-emotion sliders (-1..1): amplify, dampen, or full poker-face
> - Cross-shape coupling: eye-squint follows mouth-smile when happy (Duchenne), inner-brow follows frown when sad — the "is this smile genuine" markers that static remaps can't do
> - Custom blends: "shy" = 0.3 happy + 0.4 surprised, on its own slider
- Persona presets (Genki / Poker / Tsundere…), 11-pose per-face calibration
> - **Inputs**: iFacialMocap / MeowFace (UDP), or any VMC sender (VSeeFace, Warudo…) — it doesn't track faces itself, it's purely the EQ layer
> - **Outputs**: VTS (Live2D params), VMC, raw OSC — simultaneously
>
> Measured on an iPad TrueDepth feed: frown → sad 0.82, nose-sneer → disgust 0.64, smile → happy 1.00 (its own engine's estimates). Honest caveat: the model rig is still the ceiling, and subtle emotions depend on your tracker.
>
> Free (MIT), Windows exe + source: `<GitHub 链接>` — demo GIF below. Feedback welcome!

**配图**:eq-demo.gif + main-en.png。

---

## itch.io 页面文案(英文)

**Title**: FaceEQ — expression emotion EQ for VTubers

**Short tagline**: Any tracker → FaceEQ → any engine. Per-emotion boost/suppress, Duchenne coupling, persona presets. Free & open source.

**Body**:

> Your face tracker is 1:1. Your persona isn't.
>
> FaceEQ is a local EQ layer for VTuber expressions: boost or suppress each emotion
> independently (Genki to poker-face), with emotion-conditioned coupling (eye-smile
> follows mouth-smile — the Duchenne marker) and custom blended expressions.
>
> **Works with what you already have**
> - In: iFacialMocap, MeowFace, or any VMC sender (VSeeFace, Warudo…)
> - Out: VTube Studio (Live2D), VMC, raw OSC — multiple at once
>
> **Highlights**
> - 8 built-in persona presets + 11-pose per-face calibration
> - Voice emotion (experimental): stay expressive when your face is covered
> - Emotion-triggered VTS hotkeys
> - Direction fine-tuning per axis (mirror / freeze / damp)
> - 55 MB, portable, no telemetry, MIT
>
> **Honest limits**: your model rig is the ceiling; subtle emotions (sad/disgust)
> need a good tracker — measured 0.82 sad / 0.64 disgust on iPad TrueDepth.

**Tags**: vtuber, live2d, vtube-studio, face-tracking, expression, free

---

## VTS 官方 Plugins Wiki 申请(PR 文本)

> **Add FaceEQ to the Plugins page**
>
> FaceEQ is a free, open-source (MIT) expression EQ that injects into VTS via the
> official WebSocket API. It sits between a face tracker and VTS: per-emotion
> boost/suppress sliders, emotion-conditioned cross-parameter coupling (Duchenne
> eye-smile, sad inner-brow), persona presets, custom blended expressions,
> emotion-triggered hotkeys, and per-face calibration. It also outputs VMC/OSC for 3D.
>
> - Repo + docs (quickstart, per-tool setup guides, FAQ): `<GitHub 链接>`
> - Windows portable exe; token auth via the standard popup; users are told to set
>   VTS smoothing to 0 / multiply 1 and disable built-in camera tracking (covered in docs)
>
> 收录理由对应 wiki 标准:user friendly(exe 双击即用 + 首启动引导 + 中文/英文文档)
> + good manual(quickstart/vts-setup/faq 全套)。

---

## 真人对比 GIF 录制指引(你出镜,10 分钟)

**布局**:左半屏 = VSeeFace/MeowFace 直驱的形象(或 VTS 关 EQ 状态);右半屏 = FaceEQ 驱动。
最简单的实现:**两台设备各跑一个形象**,或同屏录 FaceEQ 信号监视器 + 模型。

**流程**:
1. 屏幕录像(OBS/Win+G,60fps,分辨率 ≥1280×720)
2. 面捕源开始发送 → 形象保持中性 2 秒
3. 依次:大笑 3s → 撇嘴 3s → 皱鼻 3s → 惊讶 3s(中间回中性)
4. **录两遍**:第一遍 FaceEQ「1比1对照」预设(=原始);第二遍「元气」预设(=EQ)
5. 把两段录像发我,我用 ffmpeg 对齐剪辑成 30s 左右对比视频 + GIF

**或者更简单**:录完把两段原片丢给我,剪辑参数我来定。
