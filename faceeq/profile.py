"""每用户校准 profile：加载 / 校验 / 优先级解析 / 写入。

profile 把 per-AU 欠读补偿（曾在 emotions.py 硬编码为 SAD_FROWN_GAIN/SAD_BROWIN_GAIN）
变成**每用户 JSON**，由校正向导 `probes/calibrate.py` 实测生成。设计见
[[face-project-design]]，实现计划见 plans/valiant-forging-wand.md。

铁律：不带 profile ⇒ emotions 走 legacy 路径（逐字等于硬编码默认）。
优先级：CLI > profile > 代码默认。
"""
import json
from dataclasses import dataclass, field

from .emotions import EMOTIONS, RAW_KEYS, compute_emotion_scale, shaping_from_dict

SCHEMA_VERSION = 1
DEFAULT_GLOBAL_GAIN = 1.4
DEFAULT_SMOOTH = 0.4
DEFAULT_EMOTION_GAIN = 1.0
_GAIN_FLOOR, _GAIN_CAP = 0.0, 50.0   # au_gains 合理区间；超界钳制并警告


@dataclass
class Calib:
    """profile 激活时传给 emotions.signals 的校准包。gains=au_gains(已 coerce)；
    neutral=每 AU 静态基线（signals 先减去再乘 gain，修中性基线被放大）；
    dead=判死的 AU 集（signals 据此重分配权重）；
    target_delta+emotion_scale=量程统一（各情绪在用户 max 脸时归一到 0..1，跨情绪可比）。"""
    gains: dict
    neutral: dict
    dead: set
    target_delta: float = 0.5
    emotion_scale: dict | None = None


@dataclass
class Resolved:
    """resolve() 产物：main.py 实际用的有效值。calib=None ⇒ 无 profile，
    emotions.signals 走 legacy 路径（逐字等于今天）。shaping=None ⇒ 引擎用默认塑造。"""
    global_gain: float
    smooth: float
    emotion_gains: dict
    calib: Calib | None = None
    shaping: object | None = None


@dataclass
class Profile:
    schema_version: int
    au_gains: dict                  # 全 10 键，null/缺失已→1.0，钳到 [0,50]
    neutral: dict
    captures: dict
    global_gain: float | None = None
    smooth: float | None = None
    emotion_gains: dict | None = None
    demographic: object | None = None
    camera: dict | None = None
    created_at: str | None = None
    shaping: dict | None = None             # 可选塑造配置（emotions.shaping_from_dict 解析）
    dead: set = field(default_factory=set)   # 校准判死的 AU 键集（au_gains 原为 null）
    target_delta: float = 0.5                # 校准目标 delta（每 AU max 归一到它）


def _coerce_gains(raw: dict | None) -> dict:
    """au_gains 补全 10 键、null/缺失→1.0、非数值→1.0、钳 [0,50]（超界警告）。"""
    out = {}
    for k in RAW_KEYS:
        v = (raw or {}).get(k)
        if v is None:
            out[k] = 1.0
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            print(f"[profile] au_gains[{k}] 非数值 {v!r}，按 1.0")
            out[k] = 1.0
            continue
        if v < _GAIN_FLOOR or v > _GAIN_CAP:
            print(f"[profile] au_gains[{k}]={v} 越界 [{_GAIN_FLOOR},{_GAIN_CAP}]，钳到边界")
            v = max(_GAIN_FLOOR, min(_GAIN_CAP, v))
        out[k] = v
    return out


def load_profile(path: str | None) -> Profile | None:
    """path=None ⇒ 返回 None（无 profile，走 legacy）。读 JSON、校验 schema、补全 au_gains。
    文件缺失 / JSON 错 ⇒ raise（让 main.py fail-fast，绝不静默回退）。"""
    if path is None:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"profile 文件不存在：{path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"profile JSON 解析失败 {path}：{e}")

    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        print(f"[profile] schema_version={sv}（本版支持 {SCHEMA_VERSION}），尽力加载")

    raw_ag = data.get("au_gains") or {}
    dead = {k for k in RAW_KEYS if k in raw_ag and raw_ag[k] is None}   # 显式 null ⇒ 判死；缺失键按默认活(gain1.0)
    return Profile(
        schema_version=sv if isinstance(sv, int) else SCHEMA_VERSION,
        au_gains=_coerce_gains(raw_ag),
        neutral=data.get("neutral") or {},
        captures=data.get("captures") or {},
        global_gain=data.get("global_gain"),
        smooth=data.get("smooth"),
        emotion_gains=data.get("emotion_gains"),
        demographic=data.get("demographic"),
        camera=data.get("camera"),
        created_at=data.get("created_at"),
        shaping=data.get("shaping") or None,
        dead=dead,
        target_delta=(data.get("target_delta") or 0.5),
    )


def resolve(args, profile: Profile | None) -> Resolved:
    """优先级 CLI > profile > 默认。要求 args.gain / args.smooth / args.<emo> 默认为 None
    （main.py 已改），这样能区分「用户传了」与「没传」。"""
    g_gain = getattr(args, "gain", None)
    global_gain = (g_gain if g_gain is not None
                   else (profile.global_gain if profile and profile.global_gain is not None
                         else DEFAULT_GLOBAL_GAIN))

    g_smooth = getattr(args, "smooth", None)
    smooth = (g_smooth if g_smooth is not None
              else (profile.smooth if profile and profile.smooth is not None
                    else DEFAULT_SMOOTH))

    eg = {}
    prof_eg = profile.emotion_gains if (profile and profile.emotion_gains) else {}
    for e in EMOTIONS:
        cli = getattr(args, e, None)
        if cli is not None:
            eg[e] = cli
        elif e in prof_eg and prof_eg[e] is not None:
            eg[e] = prof_eg[e]
        else:
            eg[e] = DEFAULT_EMOTION_GAIN

    if profile:
        es = compute_emotion_scale(profile.dead, profile.target_delta)
        calib = Calib(gains=profile.au_gains, neutral=profile.neutral, dead=profile.dead,
                      target_delta=profile.target_delta, emotion_scale=es)
    else:
        calib = None
    shaping = shaping_from_dict(profile.shaping) if (profile and profile.shaping) else None
    return Resolved(global_gain=global_gain, smooth=smooth,
                    emotion_gains=eg, calib=calib, shaping=shaping)


def write_profile(path: str, data: dict) -> None:
    """向导用：把已构建好的 profile dict 校验+写成 JSON（pretty）。"""
    data = dict(data)  # 浅拷贝，避免改调用方
    data.setdefault("schema_version", SCHEMA_VERSION)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
