# FaceEQ 常见问题 / 排错（FAQ）

按症状排查。先看「启动与杀软」，再按你的输出目标（VTS / VMC / OSC）找对应小节。
源码运行的安装问题见 [quickstart.md](quickstart.md) 的常见问题表。

## 启动与杀软

**双击 FaceEQ.exe 后 Windows 弹蓝色提示「Windows 已保护你的电脑」（SmartScreen）**
应用未做代码签名（签名证书付费，暂缓）。点「更多信息」→「仍要运行」。
介意的话可以只用源码方式运行（仓库内 `gui.py`），或等有预算后签名的版本。

**杀毒软件报毒 / exe 消失了**
Python 打包程序（PyInstaller）的常见误报，Defender 和部分国产杀软都有。
在杀软里给 `FaceEQ` 文件夹加白名单/信任区后重新解压。本项目开源、无遥测，
不放心可自行从源码运行或自行打包（`probes/build_release.py`）。

**双击后窗口一闪而过或完全没反应**
确认解压过（别在 zip 里直接双击）；`FaceEQ.exe` 必须和 `_internal` 文件夹在同一目录；
换一个不含特殊字符的纯英文路径再试；仍失败请开 Issue 附截图。

## 面捕源（输入）

**状态栏一直「断流/等数据」**
输入源没在发数据：手机 app 填对 IP/端口（开始时弹窗里有）、同一 WiFi、防火墙放行；
VMC 输入则检查发送端软件的 VMC 发送设置。

**画面很卡（源本身卡）**
v0.2.0 起 FaceEQ 不占摄像头。卡顿多来自面捕源侧：VSeeFace 和 VTS 抢同一个摄像头
→ VTS 的 Camera 设 None/Off（面捕交给 VSeeFace，VTS 只渲染）。

**想换输入源 / 没有摄像头**
「输入源」下拉切换 📱 手机 UDP / 📡 VMC 输入；VSeeFace 用电脑摄像头做面捕，免费。

## VTS（Live2D）输出

**点「开始」提示连不上 `ws://localhost:8001`**
VTS 没开，或没勾 VTS 设置里的 **Allow Plugin API access**。勾上后重试。

**VTS 弹「插件 XX 请求访问」**
点 Allow——这是首次连接的一次性鉴权，token 会存本地，之后不再弹。

**连上了但小人没反应 / 表情和没开 EQ 一样**
两件事必查：
1. VTS 自己的摄像头跟踪还开着 → 关掉（Camera 设 None），否则 VTS 侧跟踪源覆盖注入；
2. VTS 参数映射里的 **平滑（Smoothing）设 0、倍率设 1**——FaceEQ 已做增益+消抖，
   VTS 再叠一层 = 双级串联，会把效果又抹平/放大回去。详见 [vts-setup.md](vts-setup.md)。

**停止/关掉 FaceEQ 后小人不动了**
正常。FaceEQ 停止注入后，VTS 参数 1 秒内回到默认值。

## 情绪效果

**happy/angry/surprised 有效，sad/disgust 反应弱**
取决于面捕源：**TrueDepth（iPhone/iPad）实测可用**（撇嘴 sad 0.82、皱鼻 disgust 0.64）；
普通 RGB 追踪（含 VSeeFace）对细微 AU 偏弱。建议：换/加 TrueDepth 源、校准、
并把对应情绪滑块拖到 +1。v0.2.0 还做了皱鼻压 angry 的调权（皱鼻不再被怒盖住）。

**表情整体幅度太小**
模型 rig 是表情上限——Live2D 模型本身画/绑的幅度小，EQ 只能放大已有幅度。
可尝试：全局 gain 调高、校准（按你的脸重定每路增益）、换表情幅度大的模型。

**为什么要有校准？**
每张脸的表情幅度不同。11 表情校准（约 2 分钟）按你的脸实测每路增益，
效果明显更跟手；跳过也能用（走内置默认），见 [calibration.md](calibration.md)。

## 手机面捕（iFacialMocap / MeowFace）

**状态栏一直显示「手机数据断流」**
依次检查：
1. 手机和电脑连**同一个 WiFi**（手机热点里电脑也要连热点）；
2. 手机 app 里填的端口 = FaceEQ 显示的端口（默认 **49983**）；
3. 首次启动 Windows 可能弹防火墙提示 → 放行（UDP）；
4. iFacialMocap 需要 FaceEQ 的握手广播触发发送——保持 FaceEQ「开始」状态；
5. 手机 app 里确认面捕画面正常（脸在框内）。

**电脑的 IP 是多少？**
手机模式点「开始」时，FaceEQ 的确认框里会直接显示本机 IP 和端口，照填到手机 app 即可。

**模型转头/眼球方向反了（镜像）**
主窗口「方向微调 Direction」区把对应轴的滑块拨到 **-1** 即可镜像；0 = 该轴冻结不动，
中间值 = 阻尼（头动模型跟着动但幅度减半）。设置会存 `orientation.json`。

## VMC / OSC 输出（Warudo / VNyan / VSeeFace / VRChat）

> v0.2.0 起 VSeeFace 也可以当**输入源**（其 VMC 发送 → FaceEQ 的 VMC 输入，
> 端口 39539）——见 README 输入源表。

**目标软件里看不到表情**
按顺序查：
1. FaceEQ 输出目标选了「VMC → 3D 工具」，地址/端口和目标软件的接收设置一致（VMC 默认 39540）；
2. 目标软件里**开启了 VMC 接收**（Warudo：Add Asset → Motion Tracking → VMC Receiver；
   VSeeFace：General Settings → OSC 送受信），步骤见 [outputs.md](outputs.md)；
3. 3D 模型绑定了 ARKit blendshape（Perfect Sync），光有接收器没绑形状也不会动；
4. 跨机器发送（FaceEQ 和目标软件不在一台电脑）时放行 UDP 防火墙。

**没有脸入镜时正常吗？**
正常。检测不到脸时 FaceEQ 不发数据（对端保持原状），摄像头前出现脸即恢复。
手机面捕断流同理——状态栏会提示「手机数据断流」。

## 其他

**包体怎么这么大（~380MB）？**
内置了 AI 面捕模型（MediaPipe）和 PySide6。接受此体积换取免安装、离线可用。

**会上传我的画面/数据吗？**
不会。全部处理在本机完成，无遥测、无网络上传（手机面捕的 UDP 也是你自己手机发给你自己电脑）。

---

还没解决？[GitHub Issues](https://github.com/jfg-jfg/faceeq/issues) 提问（附截图与系统版本），
或按 README 的渠道反馈。
