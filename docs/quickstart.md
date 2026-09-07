# FaceEQ 快速上手指南（小白版）

## FaceEQ 是什么？

FaceEQ 是一个**表情「情绪 EQ」中间件**：把你面捕软件追踪到的表情，按情绪**差异化放大/抑制**
——让角色表情更夸张、更好认，或按人设压平某些情绪。就像给表情加了一个「均衡器」(EQ)。

它**自己不做面捕**：你先有一个面捕源（手机/平板 app，或 PC 追踪软件），FaceEQ 吃它的数据、
吐出「调过音」的表情给你的形象软件（VTube Studio / Warudo 等）。

**你需要准备：**
1. **Windows 电脑**（Windows 10/11）
2. **一个面捕源**（三选一）：
   - 📱 **手机/平板 app**：iFacialMocap（iOS，付费，TrueDepth 最强）或 MeowFace（安卓，免费）
   - 📡 **PC 追踪软件**：VSeeFace（免费，用电脑摄像头）或 Warudo
3. **形象软件**：VTube Studio（Live2D）或 Warudo 等（3D），装好并加载模型

> 不用摄像头也能用 FaceEQ（走手机 app 时不占电脑摄像头）；有电脑摄像头的话，
> VSeeFace 挂上它就是免费面捕源。

## 第 1 步：下载并运行（exe 版，免安装）

1. 下载 `FaceEQ-v0.2.0-win64.zip` → **解压到一个文件夹**（别在 zip 里直接双击）
2. 双击 `FaceEQ.exe`
   - 若 Windows 弹蓝色 SmartScreen 提示 → 「更多信息」→「仍要运行」（应用未做签名，见 FAQ）
   - 若杀毒软件报毒/删文件 → 给 FaceEQ 文件夹加白名单（详见 FAQ）

## 第 2 步：准备面捕源（以手机 app 为例）

1. 手机/平板和电脑连**同一个 WiFi**
2. FaceEQ 里选输入源（📱 手机 UDP），点「开始」→ 弹窗里显示**本机 IP 和端口**（默认 49983）
3. 手机 app 里填这个 IP 和端口，开始发送
4. FaceEQ 状态栏不再提示「断流」= 数据通了（首次可能弹防火墙提示，点允许）

**用电脑摄像头？** 选 📡 VMC 输入，然后装 [VSeeFace](https://www.vseeface.icu/)：
设置里开启 VMC 发送、地址 127.0.0.1、端口 39539（完整 52 表情需要 Perfect Sync 模型）。

## 第 3 步：校准（推荐，约 2 分钟）

点「● 校准」，照屏幕上的中英文提示做 11 个表情（中性 → 微笑 → 撇嘴 → …），
每个保持 1 秒按空格采样。校准让每个表情的增益匹配**你的脸**，效果明显更跟手。
跳过也行（用通用默认），随时可以再校准。

## 第 4 步：选输出目标 + 开始

1. 输出目标勾选（可多选）：
   - **VTS (Live2D)**：VTube Studio 里先勾 Allow Plugin API access、
     **关掉自带摄像头跟踪（Camera → None）**，首次连接点 Allow 授权
   - **VMC**：Warudo/VNyans/VSeeFace 等开启 VMC 接收（端口 39540 对齐）
   - **OSC**：自定义目标（VRChat FT 桥等）
2. 点「▶ 开始」→ 做表情试试！
3. 「信号监视」区五根条实时显示情绪强度；拖**情绪滑块**（+1 放大 / −1 压平）立即生效
4. **预设 Preset** 下拉里选 ★ 内置人设（元气/扑克脸/傲娇…）一键切换风格

## 源码运行（开发者/不想用 exe）

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
PYTHONUTF8=1 .venv\Scripts\python.exe gui.py
```

CLI：`main.py --input phone --output vts vmc` 等，见 `main.py --help`。

## 常见问题

| 问题 | 解决 |
|---|---|
| 杀软报毒 / SmartScreen 拦截 | 未签名应用的常见误报 → 白名单/仍要运行，详见 [FAQ](faq.md) |
| 状态栏一直「断流」 | 手机和电脑同一 WiFi、app 里 IP/端口填对、防火墙放行 UDP——FAQ 有五步排查 |
| VTS 连不上 | VTS 开着 + 勾 Allow Plugin API access |
| 小人很卡（1 FPS） | VTS 摄像头跟踪没关 → Camera 设 None/Off（面捕交给你的源） |
| 表情幅度小 | 模型 rig 是上限；先校准、gain 拖高；细节见 FAQ |
| sad/disgust 没反应 | 取决于面捕源：TrueDepth(iPhone/iPad) 实测可用；普通摄像头偏弱——校准+调源 |

---

## 还需要帮助？

- 📖 [FAQ / 排错](faq.md)（杀软误报、连不上、表情不动等）
- 📖 [校准详解](calibration.md) · [VTS 接入](vts-setup.md) · [输出目标](outputs.md) · [手机面捕](phone-tracking.md)
