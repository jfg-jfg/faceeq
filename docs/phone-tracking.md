# 手机面捕（iFacialMocap / MeowFace）

FaceEQ 支持用手机 app 代替摄像头做面捕。普通 RGB 摄像头对细微表情（嘴角下垂、皱鼻、
内眉抬）严重欠读，**sad / disgust 在 webcam 上基本不可用**；iPhone 的 TrueDepth（结构光）
能读到这些 AU，Android 上用 MeowFace 也能显著好于 webcam。附带好处：**不占用摄像头**，
VTS 摄像头冲突（1fps 问题）随之消失。

支持两个 app（同一套 UDP 协议，FaceEQ 做接收端）：
- **iFacialMocap**（iOS/iPadOS，App Store 付费）——需 TrueDepth 设备（iPhone X+、
  2018 款后 Face ID iPad Pro）。⚠️ App Store 搜「iFacialMocap」认准开发者 shirajuki，
  有同名仿制 app（开发者 DevelopW LLC）不兼容。
- **MeowFace**（Android，免费）——兼容 iFacialMocap 协议（无深度，细微 AU 偏弱）。

另有 📡 **VMC 输入**可接 PC 追踪软件（VSeeFace/Warudo），见 [outputs.md](outputs.md)。

## 设置步骤

1. **手机和电脑连同一个 WiFi**（重要，热点也行）。
2. 查电脑的局域网 IP：
   - GUI：选「📱 手机 UDP」后点「开始」，确认框里直接显示本机 IP；
   - 或 cmd 运行 `ipconfig`，看「IPv4 地址」（形如 192.168.1.23）。
3. 手机 app 里：模式选 **iFacialMocap 送信**（MeowFace 同理），填电脑 IP，
   **端口 49983**（改了端口的话 FaceEQ 侧 `--phone-port` / GUI 保持一致），开始发送。
4. 首次运行 FaceEQ 可能弹 **Windows 防火墙**允许框 → 勾「专用网络」允许。
5. FaceEQ 里选「📱 手机 UDP」→「开始」。状态栏出现「运行中（注入 VTS，手机源）」即在收数据。

## 校准

手机源同样要走校准（每张脸的 AU 读数差异大）：GUI 里选手机源后点「校准」，或：

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe probes/calibrate.py --source phone
```

向导没有摄像头画面，左侧显示黑底收流状态画布；照右侧中英文提示做 11 个表情即可。
换输入源（webcam ↔ 手机）后建议**重新校准**——不同检测器的 per-AU 读数不可混用。

## CLI

```bash
# 手机源 + 注入 VTS（不需要本地预览）
PYTHONUTF8=1 .venv/Scripts/python.exe main.py --phone --vts --no-preview

# 端口改成手机 app 里填的值
PYTHONUTF8=1 .venv/Scripts/python.exe main.py --phone --phone-port 49983
```

## 注意事项

- **断流**：手机锁屏 / app 退后台 / WiFi 掉了 → 状态栏提示「手机数据断流」，参数保持
  最后一帧；恢复发送后自动继续。
- **VTS 摄像头跟踪仍要保持关闭**：FaceEQ 注入是 set 模式会覆盖 VTS 自带跟踪，两边同写会打架。
- **eyeWide**：iFacialMocap/MeowFace 有独立 eyeWide 通道（webcam 检测器只能估），
  surprised 的表现通常比 webcam 好。
- **sad / disgust**：TrueDepth 下 AU15（嘴角下垂）/ AU1（内眉抬）/ AU9（皱鼻）可读——
  **v0.2.0 iPad 实测：撇嘴 sad=0.82、皱鼻 disgust=0.64（FaceEQ 实时估计）**，
  完整数据见 [acceptance-sprint1.md](acceptance-sprint1.md)。安卓 MeowFace 无深度，
  以校准实测为准（校准报告里 delta>0.05 即活）。
- **设备请固定**（支架/架稳）：头旋转是相对摄像头的——手持设备时头和设备一起动，
  头转不映射到模型（app 有头旋转数据时才生效）。
- **方向不对？**（转头方向/眼球方向反了）：轴与符号集中定义在
  `faceeq/capture.py` 的 `_ROT_SIGN` / `_EYE_SIGN`，改这两个元组即可，别动解析逻辑。
- 首选 5GHz WiFi 或 USB 网络共享，延迟更低；抖动由 FaceEQ 的 EMA 平滑兜底（可调 smooth）。
