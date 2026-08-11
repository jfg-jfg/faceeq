"""
情绪引擎：规则情绪检测 + 按情绪差异化放大 + 跨参数耦合。

设计（见 [[face-project-design]]）：
- 情绪是「放大倍数的调节器」，不是替代跟踪。用户真实表情出底数，检测到的情绪
  改变各部位的放大率，让该情绪在小人上读起来更清楚（笑→嘴/眼笑放大更多；
  怒→眉放大、嘴形压一点；惊讶→睁大眼、挑眉）。
- 情绪信号用规则从 blendshape 算（EMFACS 风格）：瞬时、不抖、无延迟，绕开
  平滑治抖↔延迟的死扣。情绪规则**不依赖 jawOpen**，所以说话不会误触发情绪。
- 对口型（ParamMouthOpenY）走快车道：只吃 global_gain，不受情绪影响，
  保证说话时嘴零延迟、不被情绪层串味。
- 情绪增益是有符号强度 ∈[-1,1]：1.0=全量夸张（默认）、0=不塑造、负=抑制该情绪
  （把相关参数往中性压，做扑克脸/死板人设 = persona 控制）。
- 跨参数情绪耦合（COUPLING，FACS + Ekman「可靠肌肉」为据）：happy 让眼笑(AU6)追
  嘴笑(AU12)=Duchenne；sad 让内眉抬(AU1)追嘴角下垂(AU15)=悲伤真伪标记。这些都是难伪造、
  摄像头易欠读的共激活，纯放大主特征会让表情读起来假；耦合补上。VTS 每参数独立滑块
  结构上做不到条件跨参数驱动，这是 FaceEQ 的护城河。

注：「漫画化偏差放大」out=neutral+gain·(base−neutral) 对当前参数集是 no-op
（所有表情参数 resting=0，代入即 gain·base，等价线性），故核心仍是带符号增益 +
耦合；非线性噪声压制曲线缓后（当前未观察到噪声问题）。
"""
from .mapping import RANGES

EMOTIONS = ["happy", "angry", "sad", "surprised", "disgust"]

# signals_with_raw 返回的原始输入键（单一来源；profile.py 与校准探针都引用它）。
RAW_KEYS = ["smile", "frown", "squint", "browDn", "press",
            "browIn", "browUp", "eyeWide", "sneer", "jawOpen"]

# —— webcam 欠读补偿（实验性，2026-08-08 复测用；验证前非正式特性）——
# RGB 摄像头对 sad 的 AU15(嘴角下垂)/AU1(内眉抬)极度欠读（自校准：夸张悲也只
# frown~0.1/browIn~0.02）。这两个增益把弱信号拉高，看 sad 能否在 webcam 复活；
# 代价是放大噪声→可能 rest/无关表情误触发。复测后定：调值保留 / 还是判死。
SAD_FROWN_GAIN = 4.0
SAD_BROWIN_GAIN = 6.0

# EMFACS 公共系数（_emo_legacy 与 _emo_gained 共享，避免两引擎漂移；改这里两边自动同步）。
SQUINT_COEFF = 0.4             # happy 的 Duchenne(squint) 系数，只在 smile>frown 时计入
JAW_DEADZONE = 0.3             # surprised 的 jawOpen 说话死区（说话 jaw~0.2、惊讶~0.57）
ANGRY_W = (0.5, 0.5)           # (browDn, press)
SURPRISED_W = (0.6, 0.4, 1.2)  # (eyeWide, browUp, jaw 死区外系数)
SAD_W = (0.6, 0.4)             # (frown, browIn)
DISGUST_W = (0.7, 0.3)         # (sneer, frown)

# 每情绪的"max 脸"：各 AU 在该情绪最强时该取的值（"td"=target_delta=正贡献/max；
# 未列出=0=负贡献或无关）。用于预计算 emotion_scale（量程统一）。死 AU 在预计算时再置 0。
_MAX_POSE = {
    "happy":     {"smile": "td", "squint": "td"},            # frown=0 让 smile 主导
    "angry":     {"browDn": "td", "press": "td"},
    "sad":       {"frown": "td", "browIn": "td"},            # smile=0
    "surprised": {"eyeWide": "td", "browUp": "td", "jawOpen": "td"},
    "disgust":   {"sneer": "td", "frown": "td"},
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _clamp01(v):
    return max(0.0, min(1.0, v))


def _happy(r):
    """happy = smile − frown + (squint 若真笑)。两引擎共享（squint 系数走 SQUINT_COEFF）。"""
    return _clamp01(r["smile"] - r["frown"]
                    + (SQUINT_COEFF * r["squint"] if r["smile"] > r["frown"] else 0.0))


def _disgust(r):
    """disgust = sneer + frown。两引擎共享。"""
    return _clamp01(DISGUST_W[0] * r["sneer"] + DISGUST_W[1] * r["frown"])


def _sad(frown_eff, browIn_eff, smile):
    """sad = frown + browIn − smile。两引擎共享（legacy 传 SAD_*_GAIN 放大后的 eff，
    gained 传已增益原值）。"""
    return _clamp01(SAD_W[0] * min(1.0, frown_eff)
                    + SAD_W[1] * min(1.0, browIn_eff) - smile)


def _emo_legacy(r):
    """无 profile 路径：逐字等于硬编码默认（含 SAD_FROWN_GAIN/SAD_BROWIN_GAIN）。
    任何改动都会破坏 no-regression；profile 激活时此路径不执行。"""
    return {
        "happy":     _happy(r),        # squint 只在真笑计入（见 _happy），防 rest squint 底白送 happy
        "angry":     _clamp01(ANGRY_W[0] * r["browDn"] + ANGRY_W[1] * r["press"]),
        # sad：AU15/AU1 在 RGB 摄像头严重欠读，实验性加 SAD_*_GAIN 拉高弱信号（gained 路径不用）。
        "sad":       _sad(r["frown"] * SAD_FROWN_GAIN, r["browIn"] * SAD_BROWIN_GAIN, r["smile"]),
        "surprised": _clamp01(SURPRISED_W[0] * r["eyeWide"] + SURPRISED_W[1] * r["browUp"]
                              + SURPRISED_W[2] * max(0.0, r["jawOpen"] - JAW_DEADZONE)),
        "disgust":   _disgust(r),
    }


def _emo_gained_raw(r, live, target_delta):
    """profile 路径的"原始"情绪值（未除 emotion_scale）。r=(raw−neutral)·gain；
    live[k]=该 AU 是否活；target_delta 用于 surprised jaw 的满量程映射。"""
    # angry：ANGRY_W 按 live 归一（死搭档权重扔给活搭档）
    w_bd = ANGRY_W[0] if live.get("browDn") else 0.0
    w_pr = ANGRY_W[1] if live.get("press") else 0.0
    wsum = w_bd + w_pr
    angry = (w_bd * r["browDn"] + w_pr * r["press"]) / wsum if wsum > 0 else 0.0
    # surprised：eyeWide+browUp 都死 → jaw 独撑，[deadzone, target_delta]→[0,1]
    if not (live.get("eyeWide") or live.get("browUp")):
        span = max(1e-6, target_delta - JAW_DEADZONE)
        surprised = (_clamp01((r["jawOpen"] - JAW_DEADZONE) / span)
                     if live.get("jawOpen") else 0.0)
    else:
        surprised = (SURPRISED_W[0] * r["eyeWide"] + SURPRISED_W[1] * r["browUp"]
                     + SURPRISED_W[2] * max(0.0, r["jawOpen"] - JAW_DEADZONE))
    return {
        "happy":     _happy(r),
        "angry":     _clamp01(angry),
        "sad":       _sad(r["frown"], r["browIn"], r["smile"]),
        "surprised": _clamp01(surprised),
        "disgust":   _disgust(r),
    }


def _emo_gained(r, live, target_delta, emotion_scale=None):
    """profile 路径情绪值。先算 raw（_emo_gained_raw），再按 emotion_scale 归一到 0..1
    （各情绪在用户 max 脸时都≈1.0，跨情绪可比）。emotion_scale=None 时返回 raw（守卫/调试用）。"""
    emo = _emo_gained_raw(r, live, target_delta)
    if emotion_scale:
        emo = {e: _clamp01(emo[e] / emotion_scale.get(e, 1.0)) for e in emo}
    return emo


def compute_emotion_scale(dead, target_delta):
    """预计算每情绪的"满量程"= 它在所有活 AU 都达 target_delta 时的 raw 值（死 AU 置 0）。
    死情绪（raw≈0，如 webcam 上的 sad/disgust）存 1.0 避免除 0。返回 {emotion: scale}。
    供 profile.resolve 构造 Calib 时调用，使各情绪落到统一 0..1 量程。"""
    live = {k: (k not in dead) for k in RAW_KEYS}
    out = {}
    for e in EMOTIONS:
        r = {k: (target_delta if (k in _MAX_POSE[e] and k not in dead) else 0.0) for k in RAW_KEYS}
        val = _emo_gained_raw(r, live, target_delta)[e]
        out[e] = val if val > 1e-6 else 1.0
    return out


def signals_with_raw(bs: dict, calib=None):
    """从 blendshape 算 (情绪强度字典, 原始输入字典)，单一来源。

    raw 永远是**未增益**的真检测读数（校正向导量的、signal_probe 显示的都是它）。
    calib=None ⇒ 走 _emo_legacy（逐字等于硬编码默认，no-regression）；
    calib 给定（profile.Calib：gains+neutral+dead）⇒ gained=(raw−neutral)·gain，按 dead 把
    情绪权重重分配给活 AU（_emo_gained）。先扣中性，避免高压基线被放大。
    """
    def g(n):
        return bs.get(n, 0.0)

    smile   = (g("mouthSmileLeft") + g("mouthSmileRight")) / 2
    frown   = (g("mouthFrownLeft") + g("mouthFrownRight")) / 2
    squint  = (g("eyeSquintLeft") + g("eyeSquintRight")) / 2
    browDn  = (g("browDownLeft") + g("browDownRight")) / 2
    press   = (g("mouthPressLeft") + g("mouthPressRight")) / 2
    browIn  = g("browInnerUp")
    browUp  = (g("browInnerUp") + g("browOuterUpLeft") + g("browOuterUpRight")) / 3
    eyeWide = (g("eyeWideLeft") + g("eyeWideRight")) / 2
    sneer   = (g("noseSneerLeft") + g("noseSneerRight")) / 2
    jaw     = g("jawOpen")

    raw = {"smile": smile, "frown": frown, "squint": squint, "browDn": browDn,
           "press": press, "browIn": browIn, "browUp": browUp,
           "eyeWide": eyeWide, "sneer": sneer, "jawOpen": jaw}

    if calib:
        neu = calib.neutral
        gained = {k: max(0.0, raw[k] - neu.get(k, 0.0)) * calib.gains.get(k, 1.0) for k in raw}
        live = {k: (k not in calib.dead) for k in raw}
        emo = _emo_gained(gained, live, calib.target_delta, calib.emotion_scale)
    else:
        emo = _emo_legacy(raw)
    return emo, raw


def signals(bs: dict, calib=None) -> dict:
    """从 blendshape 字典算各情绪强度 ∈[0,1]。规则启发式，可调。
    calib=None 走 legacy（逐字默认）；给定（profile.Calib）则按 per-user 校准。"""
    return signals_with_raw(bs, calib)[0]


# 每个参数的放大配置：(是否吃 global_gain, {情绪: 额外放大系数})
# - 快车道 ParamMouthOpenY：只吃 global_gain，不受情绪影响
# - 眼睛开合：不吃 global_gain（眨眼保持1:1），仅情绪调节
# - 姿态/眼球：纯 1:1
# - ParamEyeLSmile/RSmile 的 happy 塑造、ParamBrowLY/RY 的 sad 塑造都交给下面 COUPLING
#   （耦合独占，避免与 boost 双重计数）
PARAM_CONFIG = {
    "ParamMouthOpenY": (True, {}),
    "ParamMouthForm":  (True, {"happy": 0.6, "sad": 0.4, "angry": 0.3, "disgust": 0.2}),
    "ParamBrowLY":     (True, {"surprised": 0.6}),   # sad 内眉抬交给 COUPLING（AU1←AU15）
    "ParamBrowRY":     (True, {"surprised": 0.6}),
    "ParamBrowLForm":  (True, {"angry": 0.6, "sad": 0.3}),
    "ParamBrowRForm":  (True, {"angry": 0.6, "sad": 0.3}),
    "ParamEyeLOpen":   (False, {"surprised": 0.4}),
    "ParamEyeROpen":   (False, {"surprised": 0.4}),
    "ParamEyeLSmile":  (False, {}),   # 眼笑塑造交给 COUPLING（happy 时追嘴笑）
    "ParamEyeRSmile":  (False, {}),
    "ParamAngleX": (False, {}), "ParamAngleY": (False, {}), "ParamAngleZ": (False, {}),
    "ParamEyeBallX": (False, {}),
}


# 跨参数情绪耦合规则（FACS + Ekman「可靠肌肉」理论；FaceEQ 护城河——VTS 每参数独立
# 滑块做不到条件跨参数驱动）。每条：(目标输出参数, 源输出参数, 门情绪, 强度 k, 必须胜过)。
# 源参数名前可加 '-' 表示取反（取双极参数负半轴为正量纲，如嘴角下垂 = -MouthForm）。
# 「必须胜过」=一组情绪名：门情绪强度须 ≥ 这些里任一个，耦合才开火（防串味——如下垂
# 同时属于 sad/disgust，纯靠 sad>0 会在厌恶/怒脸上误抬眉）。
#
# 语义：门情绪>0 且胜过竞争情绪时，把【已放大】的目标输出抬到至少 k·|源正半轴|·门情绪·
# 该情绪增益（只抬不压，不覆盖更强的真实检测）。乘 eg 让 persona 负增益时自然停耦合，
# 避免「一处被压、另一处却被耦合抬」的不一致。在 amplify 逐参数循环之后、输出空间做。
#
# 每条都对应「该情绪的真伪/强度标记 AU」——Ekman 难伪造的可靠肌肉，或摄像头欠读的共激活：
# - happy → 眼笑(AU6) 追 嘴笑(AU12)：Duchenne 微笑。AU6 难伪造 + ARKit 欠读 eyeSquint。
# - sad   → 内眉抬(AU1) 追 嘴角下垂(AU15)：依据是 Ekman 可靠肌肉理论——AU1(frontalis 内侧)
#   难主动伪造、是悲伤原型(AU1+AU4+AU15)的真诚标记；摄像头易欠读 → 用好读的下垂去补。
#   （注：Malek,Messinger 2018,Emotion 把 Duchenne 标记推广到悲，测的是 AU6 眼缩窄、对 AU1
#   零证据；选 AU1 而非 AU6 是因「悲嘴+笑眼」会读成假笑/惊悚，AU1 无此歧义。）
#
# 刻意不加（有据排除，非偷懒）：
# - angry：原型 AU4+5+7+23。眼向存疑——AU5(睁大怒视)与 AU7(睑收紧)在冷怒/暴怒里方向相反，
#   无一致欠读标记；AU23(唇收紧)无 ARKit 通道。怒的可靠标记 AU4(皱眉)已由 BrowForm 直接放大覆盖。
# - surprised：原型 AU1+2+5+26 全部好读且已映射，无欠读标记（文献亦未将惊讶纳入 Duchenne 推广）。
# - disgust：标记 AU9(皱鼻)好读(noseSneer)但当前无 Live2D 输出参数。非不可能——FaceEQ 既会
#   自建自定义 VTS 参数，未来可加 FaceEQNoseWrinkle + disgust→皱鼻耦合；暂不做（优先级低）。
COUPLING = [
    # happy 时眼笑追嘴笑（AU6←AU12，Duchenne）。happy 由 smile 驱动、不和负面情绪共享，无需 must_beat。
    ("ParamEyeLSmile", "ParamMouthForm", "happy", 0.8, ()),
    ("ParamEyeRSmile", "ParamMouthForm", "happy", 0.8, ()),
    # sad 时内眉抬追嘴角下垂（AU1←AU15）。下垂同时属于 sad/disgust，故须 sad≥怒 且 sad≥厌 才开火，
    # 否则会在厌恶/愤怒脸上误抬眉（FACS：厌恶眉中性、怒眉 AU4 下压，都该平/下不该抬）。
    ("ParamBrowLY", "-ParamMouthForm", "sad", 0.5, ("angry", "disgust")),
    ("ParamBrowRY", "-ParamMouthForm", "sad", 0.5, ("angry", "disgust")),
]


def dominant(emo: dict, threshold: float = 0.15) -> str:
    """返回当前最强情绪名（用于显示）；都低于阈值时算 neutral。"""
    if not emo:
        return "neutral"
    name, val = max(emo.items(), key=lambda kv: kv[1])
    return name if val >= threshold else "neutral"


def amplify(base: dict, emo: dict, global_gain: float = 1.5,
            emotion_gains: dict = None) -> dict:
    """底数 base（来自 mapping.base_map）× (global_gain + 情绪差异化) + 跨参数耦合。

    emotion_gains: {情绪: 有符号强度 ∈[-1,1]}（入口 clamp 到 [-1,1]）。
      1.0 = 该情绪按规则全量夸张（默认）；0 = 不对该情绪做额外塑造；
      负值 = 反向抑制（把该情绪相关参数往中性 0 压，做扑克脸/死板人设）。
    最终值 = base * (global_gain if 吃全局 else 1) * (1 + Σ eg·强度·boost)，
    再按 COUPLING 做跨参数耦合后处理（如 happy 时眼笑追嘴笑）。
    """
    eg = {e: _clamp(x, -1.0, 1.0) for e, x in (emotion_gains or {}).items()}
    out = {}
    for p, v in base.items():
        use_gg, boosts = PARAM_CONFIG.get(p, (False, {}))
        mult = global_gain if use_gg else 1.0
        extra = 1.0
        for e, b in boosts.items():
            extra += eg.get(e, 1.0) * emo.get(e, 0.0) * b
        lo, hi = RANGES.get(p, (-1.0, 1.0))
        out[p] = _clamp(v * mult * extra, lo, hi)

    # 跨参数耦合（输出空间后处理）：门情绪>0、且胜过 must_beat 里的竞争情绪时，把目标抬向
    # k·|源正半轴|·门情绪·该情绪增益，只抬不压。源名前缀 '-' 取反（双极参数负半轴，如下垂）。
    # eg 为负时 target≤0 自然跳过 → persona 抑制时不耦合抬，避免「一处被压、另一处抬」的不一致。
    for tgt, src, gate, k, must_beat in COUPLING:
        g = emo.get(gate, 0.0)
        if g <= 0 or tgt not in out:
            continue
        if any(emo.get(e, 0.0) > g for e in must_beat):   # 防串味：门情绪须压过共享特征的竞争情绪
            continue
        neg = src.startswith("-")
        key = src[1:] if neg else src
        if key not in out:
            continue
        mag = max(0.0, -out[key] if neg else out[key])
        target = k * mag * g * eg.get(gate, 1.0)
        if target > out[tgt]:
            hi = RANGES.get(tgt, (-1.0, 1.0))[1]
            out[tgt] = min(target, hi)
    return out
