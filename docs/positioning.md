# FaceEQ 产品定位（内部文档）

> 依据 2026-09 的生态调研（VTS wiki/Steam/itch/GitHub/Reddit/B站）。结论先行：
> **FaceEQ = 给 VTuber 的开箱即用表情情绪 EQ**。核心三点无人占据；发行形态决定生死。

## 1. 真空白（我们的差异化，宣传只打这三点）

1. **连续的、按情绪差异化的增益/抑制**——所有现存"情绪感知"（VSeeFace 检测、VNyan
   filter）都是 on/off 触发器；所有"放大"手段（VTS 范围重映射、Warudo 灵敏度）都是
   静态无条件的。「情绪→增益曲线」这层不存在。
2. **情绪条件跨参数耦合**（Duchenne 等）——最接近的是 Warudo Constraint BlendShape
   （静态 1:1）和 sharp-bridge（手写表达式），均无条件、无现成 UI。
3. **人设 EQ 预设**这个产品框架——完全无人占位（一键 元气/扑克脸/傲娇）。

## 2. 已被覆盖、不能当卖点的点

- **单纯全局放大**：VTS 逐参数输出范围重映射 + Multiply 表情已解决，是社区标准答案。
- **参数注入机制**：VBridger/sharp-bridge 已验证，无技术壁垒。
- **情绪触发表情**：VSeeFace 已覆盖（3D 侧）——我们做 VTS 侧对等物（⌨ 情绪触发），
  定位是补齐而非卖点。

## 3. 竞品对照

| 工具 | 模式 | 与 FaceEQ 的关系 |
|---|---|---|
| VTS 内建 | 参数范围重映射/Multiply 表情/逐参数平滑 | 覆盖"静态放大"；无情绪维度。文档要直接回答"为什么不用它" |
| VBridger（Steam $9.99+DLC$19.99） | iPhone blendshape→Live2D 自定义参数（模型重 rig） | 最近竞品：占"进阶映射"心智，200 评价。我们走"开箱+情绪层"，避开映射编辑器 |
| Vitamins（免费开源） | 脚本式，同领域 | 22 评价——"要写公式"的采用天花板实证 |
| sharp-bridge（1 star） | 参数表达式变换 | 反面教材：裸编辑器没市场 → 2c 映射层 GUI 降级远期 |
| Warudo/VNyans（3D） | 节点图可搭任意逻辑但门槛高 | 通过 VMC 输出成为它们的"表情增强上游"，不是对手 |
| VSeeFace（3D） | 情绪检测→VRM 触发 | 需求已被验证；Live2D/VTS 侧无对应物 = 我们的空间 |

## 4. 发行（证据驱动）

- **形态**：免 Python 的绿色 exe（VSeeFace 因杀软误删被迫打包的先例；OpenSeeFace 纯
  Python 无终端用户）。VBridger 一键付费 200 评价 vs Vitamins 免费+脚本 22 评价——
  **易用性 = 10 倍采用差距**。
- **渠道**：GitHub Release（主）→ itch.io（VTS 插件事实标准渠道）→ 申请收录
  [VTS 官方 Plugins Wiki](https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins)
  （唯一"官方商店"，条件：cool + user friendly + good manual）→ B站教程（中文主阵地）
  → r/vtubertech 前后对比视频。
- **变现**：免费开源 + Ko-fi/Sponsors 起步；验证留存后可学 VBridger 上 Steam（$5–10）。
  纯捐赠在此生态无成功先例，不作为策略。
- **口碑红线**：诚实告知"模型 rig 是表情上限"，否则用户拿烂 rig 测出无效果 = 差评。

## 5. 明确不做（有据排除）

- Steam 付费/闭源转向（验证留存前）；3D/VRM 原生渲染（Warudo/VSeeFace 领地，我们做上游）；
- AI 情绪识别替代规则引擎（规则瞬时/无延迟/可解释是特性）；映射层 GUI 编辑器（=sharp-bridge 覆辙）；
- 从 VTS 回读做 EQ（反馈环风险）；自研手机 app（iFacialMocap/MeowFace 兼容已覆盖）。

## 6. 远期观察

- AI VTuber 生态（Open-LLM-VTuber 等）需要"情绪→Live2D 表情"层，FaceEQ 引擎可复用——暂只记录；
- NVIDIA/网页面捕等新输入源——输出层/输入层均为适配器结构，接入成本低。
