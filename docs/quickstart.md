# FaceEQ 快速上手指南（小白版）

## FaceEQ 是什么？

FaceEQ 是一个 VTube Studio 插件，能**放大你的面部表情**——让你的 VTuber 小人表情更夸张、更好认。
就像给表情加了一个「均衡器」(EQ)，你可以单独调每个情绪的增强/抑制。

**你需要准备：**
1. **Windows 电脑**（Windows 10/11）
2. **摄像头**（内置或 USB 都行）
3. **VTube Studio**（Steam 免费下载）+ 一个 Live2D 模型
4. **Python 3.10~3.12**（⚠️ 不要装 3.13/3.14）

---

## 第 1 步：安装 Python

1. 去 https://www.python.org/downloads/ 下载 **Python 3.12**
2. 安装时 ⚠️ **勾选 "Add Python to PATH"**（页面最底部，很重要！）
3. 验证：按 `Win+R` → 输入 `cmd` → 回车 → 输入 `python --version` → 看到 `Python 3.12.x` 就对了

## 第 2 步：下载并解压 FaceEQ

1. 下载 `FaceEQ.zip`
2. 解压到一个文件夹（比如 `D:\FaceEQ`）

## 第 3 步：安装依赖

打开命令提示符（`Win+R` → `cmd`），进入 FaceEQ 文件夹，依次输入：

```
cd D:\FaceEQ
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

⏳ 等待安装完成（几分钟，会下载 mediapipe / opencv / PySide6 等）。

## 第 4 步：设置 VTube Studio

1. 打开 VTube Studio，**加载你的模型**
2. 进入 **设置**，勾选 **「Allow Plugin API access」**
3. ⚠️ **关掉摄像头跟踪**（Camera → None/Off）—— FaceEQ 需要独占摄像头

## 第 5 步：启动 FaceEQ

在命令提示符里：

```
.venv\Scripts\python.exe gui.py
```

🎉 你会看到 FaceEQ 的控制面板（深色蓝高亮窗口，VTS 风格）。

## 第 6 步：首次校准（约 2 分钟）

1. 点 **「校准」** → 弹出确认框 → 点确认
2. 打开一个摄像头窗口 + 右侧**中英文提示面板**
3. 照着右侧提示，**依次做 11 个表情**：
   - 先做 neutral（放松脸）→ 按空格采样
   - 然后笑 / 皱眉 / 眯眼 / 抿唇 / 抬眉 / 瞪眼 / 皱鼻 / 张嘴 → 每个保持住后按空格
4. 全部做完 → 自动生成你的**个人校准文件**

💡 校准只需做一次（换摄像头/换脸时重做）。详情见 [校准指南](calibration.md)。

## 第 7 步：在 VTS 里映射参数（一次性）

FaceEQ 会自动在 VTS 里创建自定义参数（如 `faceeqEyeSmile`、`faceeqBrowForm` 等）。
你需要在 VTS 的 **模型参数映射** 界面里，把它们接到你模型的对应参数上。

📖 详细步骤见 [VTS 接入指南](vts-setup.md) 的「第二步」。

## 第 8 步：开始使用！

1. FaceEQ 面板里点 **「开始」**
2. 提示「关掉 VTS 摄像头」→ 确认
3. 🎬 你的小人开始跟着你的表情动，而且**更夸张**了！
4. **拖滑块实时调整**（运行中即时生效，不用重启）：
   - 某情绪拖到 **+1.0** = 放大到最强
   - 拖到 **0** = 不额外塑造
   - 拖到 **-1.0** = 压成扑克脸（抑制该情绪）

## 保存你的设置（预设）

调好了？点 **「存」** → 输入名字（如「元气少女」）→ 保存。
下次打开 FaceEQ，下拉选「元气少女」→ 一键恢复所有滑块值。

---

## 常见问题

| 问题 | 解决 |
|---|---|
| 启动报错 `ModuleNotFoundError` | 重装依赖：`.venv\Scripts\python.exe -m pip install -r requirements.txt` |
| 点「开始」后没反应 | 确认 VTS 开着 + 勾了「Allow Plugin API access」 |
| 小人很卡（1 FPS） | VTS 摄像头跟踪没关 → VTS 设置里 Camera 设 None/Off |
| sad/disgust 滑块拖了没效果 | 普通摄像头对「嘴角下垂」「皱鼻」等细微表情读数有限。happy/angry/surprised 是可靠的。 |
| 校准时摄像头画面是黑的 | 摄像头被其他程序占用（VTS/OBS/Zoom）→ 关掉它们再试 |
| VTS 弹「是否允许插件」 | 点 **Allow**（首次连接时弹出，之后不再问） |
| 关掉 FaceEQ 后小人不动了 | 正常——FaceEQ 停止注入后，VTS 参数 1 秒后自动回到默认 |

---

## 还需要帮助？

- 📖 [完整校准指南](calibration.md)
- 📖 [VTS 接入详细指南](vts-setup.md)
- 📖 [项目架构文档](../ARCHITECTURE.md)
