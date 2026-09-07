"""GUI 双语支持（zh 源 / en 译）。

设计：中文原文即 key，`tr(s)` 在 en 模式下查 `_EN` 映射（未收录的原样返回，
天然幂等）。语言存 `lang.txt`（"zh"/"en"），首次按系统语言初始化。
切换语言后**重启生效**（GUI 启动时做一次控件树扫描 + 调用点 tr()）。
"""
import locale
import os

LANG_FILE = "lang.txt"
_LANGS = ("zh", "en")

_lang = None


def current_lang() -> str:
    global _lang
    if _lang is None:
        if os.path.exists(LANG_FILE):
            _lang = open(LANG_FILE, encoding="utf-8").read().strip() or "zh"
        else:
            try:
                loc = locale.getlocale()[0] or ""
            except (ValueError, TypeError):
                loc = ""
            _lang = "en" if loc.lower().startswith("en") else "zh"
            _save(_lang)
        if _lang not in _LANGS:
            _lang = "zh"
    return _lang


def set_lang(lang: str):
    global _lang
    if lang in _LANGS:
        _lang = lang
        _save(lang)


def _save(lang: str):
    try:
        with open(LANG_FILE, "w", encoding="utf-8") as fh:
            fh.write(lang)
    except OSError:
        pass


def tr(s: str) -> str:
    """中文原文 → 当前语言文本。未收录/zh 模式原样返回（幂等）。"""
    if current_lang() != "en":
        return s
    return _EN.get(s, s)


# ---- zh → en 映射表（主窗口/对话框/worker 消息）----
_EN = {
    # —— 标题/副标题/固定区 ——
    "v{v} · 表情情绪 EQ · Live2D / 3D 跨引擎": "v{v} · Expression EQ · Live2D / 3D cross-engine",
    "输入源:": "Input:",
    "端口:": "Port:",
    "地址:": "Address:",
    "启用:": "Enable:",
    "📱 手机/平板 UDP (iFacialMocap/MeowFace)": "📱 Phone/tablet UDP (iFacialMocap/MeowFace)",
    "📡 VMC 输入 (VSeeFace/Warudo 等 PC 软件)": "📡 VMC input (VSeeFace/Warudo and other PC apps)",
    # —— 输出目标 ——
    "输出目标 Output": "Output",
    "VTS (Live2D)": "VTS (Live2D)",
    "VMC → 3D 工具 (Warudo/VNyans/VRM…)": "VMC → 3D apps (Warudo/VNyans/VRM…)",
    "OSC 自定义 (VRChat FT…)": "Raw OSC (VRChat FT…)",
    "VTS：勾选 Allow Plugin API access，并关掉自带摄像头跟踪":
        "VTS: enable Allow Plugin API access and turn off its built-in camera tracking",
    "VMC：目标软件开 VMC 接收，端口对齐（默认 39540）":
        "VMC: enable VMC receiving in the target app, ports aligned (default 39540)",
    "OSC：目标监听对应端口；osc_mapping.json 可精确映射":
        "OSC: target listens on the port; osc_mapping.json for exact name mapping",
    "（未勾选任何输出——点开始后只跑管线不注入）":
        "(no output selected — pipeline runs but nothing is injected)",
    # —— 语音情绪 ——
    "语音情绪（实验）——说话的音量/亮度给表情加偏置":
        "Voice emotion (experimental) — volume/brightness biases expressions",
    "启用（需麦克风）": "Enable (needs microphone)",
    "麦克风:": "Microphone:",
    "灵敏度": "Sensitivity",
    "影响强度": "Impact",
    "大声说话→表情更夸张；明亮音色偏 happy，低沉偏 angry。安静时零偏置。默认关闭。":
        "Louder speech → more exaggerated expressions; bright timbre biases happy, deep biases angry. Zero bias when silent. Off by default.",
    # —— 分组/滑块/按钮 ——
    "情绪 抑制/增强（-1..1，0=不塑造）": "Emotions boost/suppress (-1..1, 0 = no shaping)",
    "信号监视（实时情绪强度）": "Signal monitor (live emotion levels)",
    "▶  开始": "▶  Start",
    "⏹  停止": "⏹  Stop",
    "●  校准": "●  Calibrate",
    "🎛 高级塑造": "🎛 Advanced shaping",
    "⌨ 情绪触发": "⌨ Emotion triggers",
    "💾 存": "💾 Save",
    "🗑 删": "🗑 Del",
    "＋ 新建": "＋ New",
    "预设:": "Preset:",
    "预设 Preset（存/加载 EQ 快照）": "Preset (save/load EQ snapshot)",
    "自定义表情（基础情绪加权组合，拖滑块激活 0..1）":
        "Custom expressions (weighted base-emotion blends, slider 0..1)",
    "全局 gain": "global gain",
    "平滑 Smoothing": "Smoothing",
    "profile: 未加载": "profile: not loaded",
    "profile: 无/失败": "profile: none/failed",
    "就绪。点「开始」注入 VTS（会先提示关掉 VTS 摄像头）。":
        "Ready. Press Start to inject (a pre-flight note will show).",
    # —— 首启动引导 ——
    "欢迎使用 FaceEQ": "Welcome to FaceEQ",
    "三步开始：\n\n"
    "1. 准备面捕源：手机/平板装 iFacialMocap 或 MeowFace，\n"
    "    或电脑装 VSeeFace/Warudo——FaceEQ 不自己做面捕，只做 EQ\n"
    "2. 上方选输入源，点「开始」按提示在源端填 IP/端口\n"
    "3. 点「校准」照提示做 11 个表情——或先跳过，直接勾输出目标 +\n"
    "    预设下拉里的 ★ 内置人设试效果\n\n"
    "提示：VTS 里请关掉自带摄像头跟踪（Camera → None）。\n\n"
    "现在就校准吗？（推荐，约 2 分钟，按你的脸定制效果）":
        "Three steps:\n\n"
        "1. Prepare a tracker: install iFacialMocap or MeowFace on your phone/tablet,\n"
        "    or VSeeFace/Warudo on this PC — FaceEQ doesn't track faces itself, it's the EQ\n"
        "2. Pick the input source above, press Start and fill in the IP/port on the tracker\n"
        "3. Press Calibrate and follow 11 poses — or skip and just tick outputs +\n"
        "    try the ★ built-in presets from the dropdown\n\n"
        "Tip: in VTS, turn off its built-in camera tracking (Camera → None).\n\n"
        "Calibrate now? (recommended, ~2 min, tuned to your face)",
    "立即校准": "Calibrate now",
    "稍后，先随便看看": "Later, just look around",
    # —— 启动前确认 ——
    "启动前确认": "Pre-start checklist",
    "VTS：把【摄像头跟踪关掉】(Camera → None/Off)，并勾选 Allow Plugin API access。":
        "VTS: turn OFF camera tracking (Camera → None/Off) and enable Allow Plugin API access.",
    "VMC：在目标 3D 软件（Warudo/VNyans/VSeeFace 等）里开启 VMC 接收，端口对齐。":
        "VMC: enable VMC receiving in the target 3D app (Warudo/VNyans/VSeeFace…), ports aligned.",
    "OSC：确认目标正在监听对应端口（VRChat FT 桥默认 9000）。":
        "OSC: make sure the target listens on the port (VRChat FT bridge defaults to 9000).",
    "未勾选任何输出——本次运行只跑管线（信号监视器可看）。":
        "No output selected — pipeline runs only (signal monitor still works).",
    "手机/平板面捕模式：app（iFacialMocap / MeowFace）里填\n\nIP：{ip}\n端口：{port}\n\n设备与电脑同一 WiFi 后开始发送；首次可能弹 Windows 防火墙提示，请放行。\n{note}\n\n准备好后点「开始」。":
        "Phone/tablet tracking: in the app (iFacialMocap / MeowFace) enter\n\nIP: {ip}\nPort: {port}\n\nPut both devices on the same WiFi, then start sending; Windows may prompt about the firewall — allow it.\n{note}\n\nPress OK when ready.",
    "VMC 输入模式：发送端软件（VSeeFace/Warudo 等）的 VMC 发送指向\n\n127.0.0.1:{port}\n\n{note}\n\n准备好后点「开始」。":
        "VMC input mode: point the sender's VMC output (VSeeFace/Warudo…) to\n\n127.0.0.1:{port}\n\n{note}\n\nPress OK when ready.",
    # —— worker 状态消息 ——
    "等待面捕数据…（手机/平板 app 或发送端软件开始推送）":
        "Waiting for tracking data… (start pushing from the app/sender)",
    "正在连接输出目标…": "Connecting outputs…",
    "语音情绪已开启（实验）": "Voice emotion enabled (experimental)",
    "手机数据断流（检查 app 发送与防火墙）":
        "Phone data stalled (check app sending & firewall)",
    "VMC 数据断流（检查发送端软件与端口）":
        "VMC data stalled (check the sender app & port)",
    "正在停止…": "Stopping…",
    "已停止。": "Stopped.",
    "语言": "Language",
    "（重启 FaceEQ 后生效）": "(takes effect after restarting FaceEQ)",
    # —— 塑造对话框 ——
    "高级塑造 · 情绪→BlendShape 增强 / 耦合": "Advanced shaping · emotion→BlendShape boost / coupling",
    "情绪→BlendShape 附加放大系数（未列出的形状 1:1 透传）":
        "Emotion→BlendShape extra gain (unlisted shapes pass through 1:1)",
    "跨形状耦合（门情绪开火时把目标形状抬向源；只抬不压）":
        "Cross-shape coupling (gated by emotion; lifts target toward source; lift-only)",
    "强度": "Strength",
    "另有 {n} 条自定义耦合（JSON 配置）原样保留。":
        "{n} custom couplings (from JSON) kept as-is.",
    "试表情（注入合成情绪值 1.5 秒，在目标软件里看塑造效果）":
        "Try expression (injects a synthetic emotion for 1.5 s — watch it in the target app)",
    "↺ 恢复默认": "↺ Reset to defaults",
    "关闭": "Close",
    # —— 触发对话框 ——
    "情绪触发 · 检测情绪 → VTS 热键": "Emotion triggers · detected emotion → VTS hotkey",
    "（选择热键）": "(pick a hotkey)",
    # —— 自定义表情 ——
    "自定义表情定义": "Custom expression",
    "名字": "Name",
    "确定": "OK",
    "取消": "Cancel",
    "已存在": "Already exists",
    "删自定义表情": "Delete custom expression",
    "删除「{name}」？": "Delete \"{name}\"?",
    "先选中一个预设再删。": "Select a preset to delete first.",
    "内置预设（★）不可删除；可另存为新名字修改它。":
        "Built-in (★) presets can't be deleted; save under a new name to edit.",
    "删除预设": "Delete preset",
    # —— 消息 ——
    "预设「{name}」已保存（含塑造与自定义表情）。": "Preset \"{name}\" saved (with shaping & custom expressions).",
    "已加载预设「{name}」{tail}。": "Loaded preset \"{name}\"{tail}.",
    "加载失败：{e}": "Load failed: {e}",
    "自定义表情需要名字和至少一个非零权重。": "Custom expression needs a name and at least one non-zero weight.",
    "「{name}」已存在，请直接编辑它。": "\"{name}\" already exists — edit it directly.",
    "自定义表情「{name}」已创建。": "Custom expression \"{name}\" created.",
    "修改无效：需要至少一个非零权重。": "Invalid edit: needs at least one non-zero weight.",
    "自定义表情「{name}」已保存。": "Custom expression \"{name}\" saved.",
    "自定义表情「{name}」已删除。": "Custom expression \"{name}\" deleted.",
    "错误：{msg}": "Error: {msg}",
    # —— 校准窗口 ——
    "FaceEQ calibrate (SPACE=采样 / ESC=跳过 / q=退出)": "FaceEQ calibrate (SPACE=capture / ESC=skip / q=quit)",
    "receiving ...": "receiving ...",
    "waiting for data ... (check app IP / firewall)": "waiting for data ... (check app IP / firewall)",
    "保持住表情": "Hold the expression",
    "→ 按 SPACE 采样": "→ press SPACE to capture",
    "做这个表情：": "Make this expression:",
    "按任意键/q 关闭": "press any key / q to close",
    "(no profile written; 按任意键关闭)": "(no profile written; press any key to close)",
}
