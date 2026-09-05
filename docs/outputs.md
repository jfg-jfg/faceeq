# 输出目标（多软件支持）

FaceEQ 的价值在 EQ 层（情绪差异化放大/抑制 + 耦合 + 自定义表情），输出目标可插拔。
当前支持三种输出，GUI 顶部「输出目标」下拉切换：

| 输出 | 适用软件 | 通道内容 | 默认端口 |
|---|---|---|---|
| **VTS (Live2D)** | VTube Studio | 放大后的 Live2D 参数（WebSocket 注入） | ws://localhost:8001 |
| **VMC** | Warudo、VNyan、VSeeFace、VMC、支持 VMC 的 VRM/Unity/UE 工具 | 放大后的 ARKit 52 blendshape（OSC/UDP） | 39540 |
| **OSC 自定义** | VRChat（经 FT 桥）、任何 OSC 接收器 | 放大后的 blendshape，地址可配 | 9000 |

输出目标与输入源（摄像头 / 手机 UDP）自由组合——**手机面捕 → VMC → Warudo** 是 3D 主打链路。

## VMC 输出（3D 工具通用）

1. FaceEQ 输出目标选「VMC → 3D 工具」，地址填目标软件所在机器 IP（本机 127.0.0.1），端口 39540。
2. 目标软件开启 VMC 接收：
   - **Warudo**：Add Asset → Motion Tracking → VMC Receiver，端口对齐 39540；
     模型需带 ARKit/Perfect Sync blendshape（BlendShape Mapping 选对应项）。
   - **VNyan**：设置里开启 OSC/VMC 输入。
   - **VSeeFace**：General Settings →OSC 送受信，接收端口对齐。
3. 点「开始」。FaceEQ 每帧发一个 OSC bundle：`/VMC/ext/blend/val <ARKit名> <放大值>` ×52 +
   `/VMC/ext/blend/apply` 收帧（与 VSeeFace 发送端同款字符串名约定）。

说明：
- VRM0 / VRM1 的表情命名差异由接收端转换（VMagicMirror、Warudo 均内置转换项）。
- 头部旋转默认不发送（blendshape 主通路不受影响）；各软件用自己的头部/摄像头跟踪即可。
- 3D 模型没做 Perfect Sync rig 的话，只有部分 blendshape 有绑定——那是模型侧问题，
  FaceEQ 的信号监视器可以帮你确认「放大值有在发」。

## OSC 自定义输出

- 默认模式：每个形状发 `<前缀>/bs/<ARKit名>`（如 `/faceeq/bs/mouthSmileLeft`），值 0..1。
- **精确映射模式**：仓库根目录建 `osc_mapping.json`：

```json
{
  "jawOpen": "/avatar/parameters/JawOpen",
  "mouthSmileLeft": "/avatar/parameters/SmileLeft"
}
```

  配置后**只发映射了的形状**，地址用映射值——用于 VRChat FT 桥等需要特定参数名的目标。

## VTS 输出（Live2D）

行为同此前版本：WebSocket 连接 + token 鉴权 + 默认参数/自定义参数注入。
详见 [vts-setup.md](vts-setup.md)。

## 排错

- **目标没反应**：先看 FaceEQ「信号监视器」——情绪条在动说明 EQ 层正常，问题在接收端
  （端口/IP 对不上、目标软件没开接收、模型没绑 blendshape）。
- **Warudo 里动作但表情平**：模型的 Perfect Sync 绑定缺失，或 FaceEQ 情绪滑块全 0
  （0=不塑造，默认塑造请拖到 +1）。
- **vmc/osc 发送被防火墙拦**：跨机器发送时放行 UDP 出站/入站。
