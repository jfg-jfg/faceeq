# VTube Studio 接入指南（FaceEQ）

FaceEQ 经 VTube Studio 公开 WebSocket API（`ws://localhost:8001`）把放大后的表情
数据注入 VTS，由 VTS 渲染你自己的模型。前置 + 两步走。

## 前置（一次性）

1. VTube Studio 运行中 → **设置里勾 “Allow Plugin API access”**。
2. 装依赖：`.venv/Scripts/python.exe -m pip install websocket-client`
3. 模型已加载。

## 第一步：连接授权（一次性）

```
PYTHONUTF8=1 .venv/Scripts/python.exe main.py --vts
```

首次运行 VTS 会弹授权窗，点 **Allow**。之后 token 存在 `.vts_token`，不再弹窗。

此时 FaceEQ 已在注入：**默认输入参数**（头部姿态/眼开合/眼球/嘴开合/嘴笑/挑眉）
会被 VTS 自动映射到模型——**笑、惊讶立刻就有效果，无需任何配置**。

## 第二步：映射自定义参数（补全怒/悲/厌恶，每个模型一次）

FaceEQ 还自建了 4 个 VTS 自定义输入参数（VTS 默认输入没有这些通道）。要让它们
驱动模型，去 VTS 的**模型参数映射**界面，按下表把模型参数的输入源接到对应自定义参数：

| 自定义输入参数 | 范围 | 含义 | 映射到模型参数 |
|---|---|---|---|
| `FaceEQEyeSmile` | 0..1 | 眼笑/眯眼（笑） | ParamEyeLSmile、ParamEyeRSmile |
| `FaceEQBrowForm` | -1..1 | 眉形/眉角（负=怒眉内聚） | ParamBrowLForm、ParamBrowRForm |
| `FaceEQMouthFrown` | 0..1 | 嘴角下垂（悲/厌恶） | 模型的嘴下垂参数 |
| `FaceEQBrowDown` | 0..1 | 压眉（怒） | 模型的压眉参数 |

映射方法（VTS）：模型 → 编辑参数映射 → 选中某个 Live2D 参数 → 把它的输入源选成
上面的自定义参数（`addedBy: FaceEQ`）。

### 关于"双极参数"的冲突提示

`MouthSmile`（VTS 默认，只笑）和 `FaceEQMouthFrown`（只下垂）是两个独立信号：
- 模型若**分开**笑/下垂两个参数 → 各自映射，互不冲突。
- 模型若是**单一双极** `ParamMouthForm`（-1 皱 / +1 笑）→ 二选一：要么只用 VTS 默认
  `MouthSmile`（笑保留、皱嘴丢），要么把它改接到 `FaceEQMouthFrown` 按负向（皱嘴保留、
  笑走默认）。

眉高同理：`BrowLeftY`（默认，只抬） vs `FaceEQBrowDown`（只压）。双极 `ParamBrowLY` 的
模型二选一即可。

## ⚠️ VTS 参数映射设置：平滑=0、倍率=1（务必，否则表情发糊/嘴型废）

FaceEQ 注入的值**不绕过** VTS 的参数映射——它进映射后，VTS 仍按该映射的设置再处理
一遍。官方原文：注入参数“与普通跟踪参数一样处理，可作为模型参数映射的输入，并可用
UI 上的滑块设平滑”。管线是：

```
FaceEQ 注入值 → [VTS 参数映射：倍率 × 平滑 × clamp] → Live2D 模型参数
```

FaceEQ 自己已经在做放大（`--gain`）和平滑（EMA）。若 VTS 这段也开大，就成了**两级
串联**，三坑：

| 坑 | 原因 | 后果 |
|---|---|---|
| 平滑叠加 | FaceEQ EMA + VTS 平滑 | **延迟叠加**，对口型的嘴被拖两次 → 口型废 |
| 倍率叠加 | FaceEQ `--gain` × VTS 倍率 | 双重放大，容易爆掉/抽搐 |
| 调不准 | 两段都改同一个值 | 改半天不知道是谁起作用 |

**红线——每个 FaceEQ 驱动的参数映射都要设：**

1. **平滑 = 0**：FaceEQ 已用 EMA 平滑（`--smooth`），VTS 这边别再叠。
2. **倍率 = 1.0（默认）**：放大交给 FaceEQ 的 `--gain` / `--happy` 等。

对**默认输入映射**（MouthSmile/BrowLeftY…）和**自定义参数映射**（FaceEQEyeSmile…）
**都适用**。

**唯一例外**：想临时把某个参数再调大/小做最终微调，可在 VTS 把那个映射的倍率从 1.0
改成如 1.3（更夸张的笑）。但它和 `--gain` 是相乘的——**一次只调一段**，别两边同时
使劲。不确定有没有串联，实测：把某映射倍率设 2，看模型动幅是否翻倍即知。

## 运行

```
# 预览(本地 Haru) + 注入 VTS
PYTHONUTF8=1 .venv/Scripts/python.exe main.py --vts

# 纯 VTS（不开本地窗口）
PYTHONUTF8=1 .venv/Scripts/python.exe main.py --vts --no-preview

# 调夸张度（情绪强度 -1..1：1.0=全量夸张默认，0=不塑造，负=抑制该情绪做扑克脸）
PYTHONUTF8=1 .venv/Scripts/python.exe main.py --vts --no-preview --gain 2.2 --happy 1.0 --angry -0.5
```

退出：预览窗 ESC/关窗；纯 VTS 用 Ctrl-C。

## 排错

- **连不上 / 不弹授权**：VTS 没开，或没勾 “Allow Plugin API access”，或端口不是 8001。
- **自定义参数没反应**：检查第二步映射是否做了；`probes/vts_probe.py list` 能看到它们。
- **表情抖**：调大 `--smooth`（默认 0.4）；对口型会自动减半不受影响。
- **表情发糊 / 嘴型对不上**：多半是 VTS 参数映射的平滑没设 0（见上面「⚠️ VTS 参数映射设置」红线）。FaceEQ 已平滑过，VTS 再叠一次会拖延迟——对口型最致命。
