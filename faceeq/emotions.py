"""
情绪引擎：规则情绪检测 + blendshape 空间按情绪差异化放大 + BS 空间耦合。

设计（v0.2.0 纯协议单趟管线）：
- 情绪是「放大倍数的调节器」，不是替代跟踪。用户真实表情出底数，检测到的情绪
  改变各形状的放大率，让该情绪读起来更清楚（笑→嘴/眼笑放大更多；怒→眉放大；惊讶→睁大眼、挑眉）。
- 情绪信号用规则从 blendshape 算（EMFACS 风格）：瞬时、不抖、无延迟，绕开
  平滑治抖↔延迟的死扣。情绪规则**不依赖 jawOpen**，所以说话不会误触发情绪。
- **EQ 只发生在 blendshape 空间**（v0.2.0 单趟换轴）：signals 吃原始 bs → bs_amplify
  出 EQ 后 bs' → 映射层从 bs' 翻译 Live2D 参数。不再有 Live2D 空间的平行放大。
- 情绪增益是有符号强度 ∈[-1,1]：1.0=全量夸张（默认）、0=不塑造、负=抑制该情绪
  （把相关形状往 0 压，做扑克脸/死板人设 = persona 控制）。
- BS 空间耦合（BS_COUPLING，FACS + Ekman「可靠肌肉」为据）：happy 让眼笑(AU6)追
  嘴笑(AU12)=Duchenne；sad 让内眉抬(AU1)追嘴角下垂(AU15)=悲伤真伪标记。这些难伪造、
  易欠读的共激活，纯放大主特征会让表情读起来假；耦合补上。
"""
from dataclasses import dataclass, field

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

# 皱鼻(sneer)对 angry 的抑制系数（v0.2.0，iPad TrueDepth 实测背书）：
# 皱鼻(AU9)的表情原型天然伴随皱眉(AU4)，browDown 拉满时 angry 0.88 会盖过 disgust 0.64
# （验收实测）。sneer 高时按 (1−k·sneer) 压 angry，让 disgust 抢回主导。
SNEER_ANGRY_SUPPRESS = 0.45

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


def _angry(r, w_bd=ANGRY_W[0], w_pr=ANGRY_W[1]):
    """angry = browDn/press 加权和 × sneer 抑制。两引擎共享（见 SNEER_ANGRY_SUPPRESS）。"""
    base = w_bd * r["browDn"] + w_pr * r["press"]
    return _clamp01(base * (1.0 - SNEER_ANGRY_SUPPRESS * min(1.0, r["sneer"])))


def _emo_legacy(r):
    """无 profile 路径：逐字等于硬编码默认（含 SAD_FROWN_GAIN/SAD_BROWIN_GAIN）。
    任何改动都会破坏 no-regression；profile 激活时此路径不执行。"""
    return {
        "happy":     _happy(r),        # squint 只在真笑计入（见 _happy），防 rest squint 底白送 happy
        "angry":     _angry(r),
        # sad：AU15/AU1 在 RGB 摄像头严重欠读，实验性加 SAD_*_GAIN 拉高弱信号（gained 路径不用）。
        "sad":       _sad(r["frown"] * SAD_FROWN_GAIN, r["browIn"] * SAD_BROWIN_GAIN, r["smile"]),
        "surprised": _clamp01(SURPRISED_W[0] * r["eyeWide"] + SURPRISED_W[1] * r["browUp"]
                              + SURPRISED_W[2] * max(0.0, r["jawOpen"] - JAW_DEADZONE)),
        "disgust":   _disgust(r),
    }


def _emo_gained_raw(r, live, target_delta):
    """profile 路径的"原始"情绪值（未除 emotion_scale）。r=(raw−neutral)·gain；
    live[k]=该 AU 是否活；target_delta 用于 surprised jaw 的满量程映射。"""
    # angry：ANGRY_W 按 live 归一（死搭档权重扔给活搭档），再吃 sneer 抑制
    w_bd = ANGRY_W[0] if live.get("browDn") else 0.0
    w_pr = ANGRY_W[1] if live.get("press") else 0.0
    wsum = w_bd + w_pr
    angry = ((w_bd * r["browDn"] + w_pr * r["press"]) / wsum if wsum > 0 else 0.0)
    angry = _clamp01(angry * (1.0 - SNEER_ANGRY_SUPPRESS * min(1.0, r["sneer"])))
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


# ---- blendshape 空间的塑形表（EQ 唯一作用空间，VMC/OSC/VTS 全部吃这里）----
# {ARKit blendshape 名: (是否吃全局 gain, {情绪: boost})}。未列出的键 = (False, {})
# （结构性形状 1:1 透传：眨眼/视线/舌头/下巴左右等——放大眨眼只会夸张瞎闪）。
# jawOpen 吃全局但不吃情绪 boost：它同时是说话通道（零延迟）。
_G = True
BS_CONFIG = {
    # 嘴部表情
    "mouthSmileLeft":  (_G, {"happy": 0.5}), "mouthSmileRight":  (_G, {"happy": 0.5}),
    "mouthFrownLeft":  (_G, {"sad": 0.5}),   "mouthFrownRight":  (_G, {"sad": 0.5}),
    "mouthPressLeft":  (_G, {"angry": 0.35}), "mouthPressRight": (_G, {"angry": 0.35}),
    "mouthUpperUpLeft": (_G, {"disgust": 0.35}), "mouthUpperUpRight": (_G, {"disgust": 0.35}),
    "mouthDimpleLeft": (_G, {"happy": 0.3}), "mouthDimpleRight": (_G, {"happy": 0.3}),
    "mouthStretchLeft": (_G, {}), "mouthStretchRight": (_G, {}),
    "mouthFunnel": (_G, {}), "mouthPucker": (_G, {}),
    "mouthRollLower": (_G, {}), "mouthRollUpper": (_G, {}),
    "mouthShrugLower": (_G, {}), "mouthShrugUpper": (_G, {}),
    "mouthLowerDownLeft": (_G, {}), "mouthLowerDownRight": (_G, {}),
    "jawOpen": (_G, {}),
    # 眉/眼表情
    "browDownLeft":  (_G, {"angry": 0.5}), "browDownRight":  (_G, {"angry": 0.5}),
    "browInnerUp":   (_G, {"sad": 0.4}),
    "browOuterUpLeft": (_G, {"surprised": 0.35}), "browOuterUpRight": (_G, {"surprised": 0.35}),
    "eyeWideLeft":   (_G, {"surprised": 0.5}), "eyeWideRight":   (_G, {"surprised": 0.5}),
    "eyeSquintLeft": (_G, {"happy": 0.35}), "eyeSquintRight": (_G, {"happy": 0.35}),
    "cheekSquintLeft": (_G, {"happy": 0.35}), "cheekSquintRight": (_G, {"happy": 0.35}),
    "noseSneerLeft": (_G, {"disgust": 0.5}), "noseSneerRight": (_G, {"disgust": 0.5}),
    "jawForward":    (_G, {"angry": 0.2}),
}
# 未列出的 1:1 透传：eyeBlinkLeft/Right、eyeLook*（8）、jawLeft/Right、
# mouthLeft/Right、cheekPuff、tongue*。


# ---- BS 空间跨形状耦合（原 Live2D 空间 COUPLING 的单趟化，FACS 依据不变）----
# 语义与老 COUPLING 一致：门情绪>0 且压过 must_beat 竞争者时，把【已放大】的目标形状
# 抬到至少 k·源形状·门情绪·该情绪增益（只抬不压）。BS 空间里源值天然 0..1，无需取反技巧。
# - happy → eyeSquint(AU6) 追 mouthSmile(AU12)：Duchenne 微笑（AU6 难伪造 + 易欠读）。
# - sad   → browInnerUp(AU1) 追 mouthFrown(AU15)：AU1 悲伤真诚标记（Ekman 可靠肌肉），
#   须 sad≥angry 且 sad≥disgust 才开火（下垂同时属于 sad/disgust，防厌恶/怒脸误抬眉）。
# - 刻意不加 angry/surprised：无一致欠读标记（依据见 git 历史里 Live2D COUPLING 的论证）。
BS_COUPLING = [
    ("eyeSquintLeft",  "mouthSmileLeft",  "happy", 0.8, ()),
    ("eyeSquintRight", "mouthSmileRight", "happy", 0.8, ()),
    ("browInnerUp",    "mouthFrownLeft",  "sad", 0.5, ("angry", "disgust")),
]


def dominant(emo: dict, threshold: float = 0.15) -> str:
    """返回当前最强情绪名（用于显示）；都低于阈值时算 neutral。"""
    if not emo:
        return "neutral"
    name, val = max(emo.items(), key=lambda kv: kv[1])
    return name if val >= threshold else "neutral"


# ---- 「试表情」的 blendshape 空间参考底 ----
# 试表情时引擎跳过面捕，直接拿这套非零底 + 合成情绪值走 EQ，不照镜子预览塑造效果。
REFERENCE_BS = {
    "mouthSmileLeft": 0.2, "mouthSmileRight": 0.2,
    "mouthFrownLeft": 0.1, "mouthFrownRight": 0.1,
    "browDownLeft": 0.15, "browDownRight": 0.15,
    "browInnerUp": 0.15, "browOuterUpLeft": 0.15, "browOuterUpRight": 0.15,
    "eyeWideLeft": 0.15, "eyeWideRight": 0.15,
    "eyeSquintLeft": 0.2, "eyeSquintRight": 0.2,
    "noseSneerLeft": 0.05, "noseSneerRight": 0.05,
    "jawOpen": 0.1,
    "cheekSquintLeft": 0.1, "cheekSquintRight": 0.1,
    "mouthPressLeft": 0.1, "mouthPressRight": 0.1,
    "mouthUpperUpLeft": 0.05, "mouthUpperUpRight": 0.05,
}


def reference_bs() -> dict:
    return dict(REFERENCE_BS)


def _bs_default_boosts():
    """BS_CONFIG 默认 boost 表的独立副本（Shaping 默认值用）。"""
    return {k: dict(b) for k, (_, b) in BS_CONFIG.items()}


# ---- 用户可调塑造配置 ----
# 默认值 = 上面 BS_CONFIG/BS_COUPLING 硬编码基线（no-regression：profile_smoke 钉死
# 「默认配置输出 == 硬编码基线」）。bs_boosts={形状: {情绪: 附加放大系数}}；
# bs_couplings=[(目标形状,源形状,门情绪,k,必须胜过)]。谁吃全局 gain 是结构项
# （说话快车道、眨眼 1:1 等），不开放给用户调，仍查 BS_CONFIG 的第一列。
@dataclass
class Shaping:
    bs_boosts: dict = field(default_factory=_bs_default_boosts)
    bs_couplings: list = field(default_factory=lambda: [tuple(c) for c in BS_COUPLING])

    def copy(self) -> "Shaping":
        return Shaping(bs_boosts={k: dict(b) for k, b in self.bs_boosts.items()},
                       bs_couplings=[tuple(c) for c in self.bs_couplings])


DEFAULT_SHAPING = Shaping()


def shaping_to_dict(sh: Shaping) -> dict:
    """Shaping → JSON 友好 dict（预设 / profile 持久化用）。"""
    return {
        "bs_boosts": {k: dict(b) for k, b in sh.bs_boosts.items()},
        "bs_couplings": [{"target": t, "source": s, "gate": g, "k": k,
                          "must_beat": list(mb)} for t, s, g, k, mb in sh.bs_couplings],
    }


def _clean_boosts(raw: dict) -> dict:
    """{形状: {情绪: 系数}} 容错清洗（非法项丢弃）。"""
    out = {}
    for k, b in raw.items():
        if not isinstance(b, dict):
            continue
        clean = {}
        for e, v in b.items():
            if e not in EMOTIONS:
                continue
            try:
                clean[e] = float(v)
            except (TypeError, ValueError):
                continue
        out[k] = clean
    return out


def shaping_from_dict(d: dict | None) -> "Shaping | None":
    """dict → Shaping（容错：非法项丢弃）。None/空 → None（调用方用默认塑造）。

    v0.1.0 预设兼容：旧字段的 param_boosts/couplings（Live2D 空间）静默忽略，
    只继承 bs_boosts/bs_couplings。"""
    if not d:
        return None
    bs_boosts = None
    if isinstance(d.get("bs_boosts"), dict):   # 缺省=用默认表；显式给出（哪怕空）才覆盖
        bs_boosts = _clean_boosts(d["bs_boosts"])
    bs_couplings = []
    for c in d.get("bs_couplings") or []:
        try:
            bs_couplings.append((c["target"], c["source"], c["gate"],
                                 float(c.get("k", 0.0)), tuple(c.get("must_beat") or ())))
        except (KeyError, TypeError, ValueError):
            continue
    if bs_boosts is None:
        return Shaping(bs_couplings=bs_couplings) if bs_couplings else None
    return Shaping(bs_boosts=bs_boosts, bs_couplings=bs_couplings)


# ---- 自定义复合表情（Phase 2b）----
# 定义 = {名字: {基础情绪: 权重}}，如「害羞」= happy 0.35 + surprised 0.30。
# 权重可负（该表情压某个基础情绪）。激活度 a∈[0,1]（GUI 滑块）：
# 注入量 = 权重 × a，additive 叠到检测情绪上再 clamp 0..1，之后走 EQ 全链路
# （persona 情绪滑块的负增益语义原样作用于注入值——「害羞」也怕扑克脸人设压 happy）。
def apply_custom(emo: dict, exprs: dict, act: dict):
    """把激活的自定义表情加权注入情绪向量。

    emo: 检测到的情绪向量；exprs: {名字: {情绪: 权重}}；act: {名字: 激活度 0..1}。
    返回 (新情绪向量, 主导自定义表情名或 None)。主导判定：注入强度（激活度×最大
    权重）超过检测最大值时，GUI 状态栏显示自定义名而不是底层情绪名。
    """
    out = dict(emo)
    det_max = max(emo.values()) if emo else 0.0
    best_name, best_val = None, 0.0
    for name, a in (act or {}).items():
        w = (exprs or {}).get(name)
        if not w or a <= 0:
            continue
        for e, weight in w.items():
            if e in EMOTIONS and weight:
                out[e] = _clamp01(out.get(e, 0.0) + weight * a)
        strength = a * max(abs(v) for v in w.values())
        if strength > best_val:
            best_name, best_val = name, strength
    return out, (best_name if best_val > det_max else None)


def bs_amplify(base_bs: dict, emo: dict, global_gain: float = 1.4,
               emotion_gains: dict = None, shaping: "Shaping | None" = None) -> dict:
    """blendshape 空间的情绪 EQ（EQ 唯一发生地）：原始 bs → 放大后的 bs'。

    值 × (全局 gain if 吃全局 else 1) × (1 + Σ eg·情绪·boost)，clamp 0..1；
    之后按 BS_COUPLING 做跨形状耦合后处理（如 happy 时眼笑追嘴笑）。
    只处理 base_bs 里出现的键（检测器给的形状）；用户 bs_boosts 覆盖 BS_CONFIG 默认。
    persona 负增益 = 压向 0。
    """
    sh = shaping if shaping is not None else DEFAULT_SHAPING
    eg = {e: _clamp(x, -1.0, 1.0) for e, x in (emotion_gains or {}).items()}
    out = {}
    for k, v in base_bs.items():
        use_gg, default_boosts = BS_CONFIG.get(k, (False, {}))
        boosts = sh.bs_boosts.get(k, default_boosts)
        mult = global_gain if use_gg else 1.0
        extra = 1.0
        for e, b in boosts.items():
            extra += eg.get(e, 1.0) * emo.get(e, 0.0) * b
        out[k] = _clamp01(v * mult * extra)

    # BS 空间耦合（后处理）：门情绪>0、且压过 must_beat 竞争者时，把目标形状抬向
    # k·源形状·门情绪·该情绪增益，只抬不压。eg 为负时 target=0 自然跳过
    # → persona 抑制时不耦合抬，避免「一处被压、另一处抬」的不一致。
    for tgt, src, gate, k, must_beat in sh.bs_couplings:
        g = emo.get(gate, 0.0)
        if g <= 0 or tgt not in out or src not in out:
            continue
        if any(emo.get(e, 0.0) > g for e in must_beat):   # 防串味：门情绪须压过共享特征的竞争情绪
            continue
        target = k * out[src] * g * eg.get(gate, 1.0)
        if target > out[tgt]:
            out[tgt] = min(target, 1.0)
    return out
