"""EQ 后的 blendshape → 原始 Live2D 参数翻译（base_map）。

本模块只做「翻译」：把 blendshape（v0.2.0 起是 **EQ 后的** bs'）+ 协议直传的
头旋转/眼球数据转成 Live2D 参数原始值并 clamp 到量程。v0.2.0 单趟管线里
base_map 位于 EQ 之后（signals 吃原始 bs → bs_amplify → base_map(bs')）。
"""
from .frame import Frame

# ---- 各参数取值范围（来自 Haru 实测；base_map 输出即最终值，clamp 在这里做）----
RANGES = {
    "ParamEyeLOpen": (0, 1), "ParamEyeROpen": (0, 1),
    "ParamEyeLSmile": (0, 1), "ParamEyeRSmile": (0, 1),
    "ParamEyeBallX": (-1, 1), "ParamEyeBallY": (-1, 1),
    "ParamBrowLY": (-1, 1), "ParamBrowRY": (-1, 1),
    "ParamBrowLForm": (-1, 1), "ParamBrowRForm": (-1, 1),
    "ParamMouthForm": (-1, 1), "ParamMouthOpenY": (0, 1),
    "ParamAngleX": (-30, 30), "ParamAngleY": (-30, 30), "ParamAngleZ": (-30, 30),
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def base_map(f: Frame) -> dict:
    """一帧（EQ 后）→ Live2D 参数（已 clamp 到量程）。

    表情 ← blendshape（bs'，EQ 后）；头部姿态 / 眼球方向 ← 协议直传
    （iFacialMocap/MeowFace 的 rot / eye，无则不输出对应参数）。空帧 → {}。
    """
    if not f.bs and f.rot is None and f.eye is None:
        return {}
    g = f.bs_get
    out = {}

    # ---- 眼睛开合（眨眼）----
    out["ParamEyeLOpen"] = _clamp(1.0 - g("eyeBlinkLeft"), 0, 1)
    out["ParamEyeROpen"] = _clamp(1.0 - g("eyeBlinkRight"), 0, 1)
    # ---- 眼睛笑（眯眼）----
    out["ParamEyeLSmile"] = _clamp(g("eyeSquintLeft"), 0, 1)
    out["ParamEyeRSmile"] = _clamp(g("eyeSquintRight"), 0, 1)
    # ---- 眉毛 ----
    brow_up_l = (g("browInnerUp") + g("browOuterUpLeft")) / 2
    brow_up_r = (g("browInnerUp") + g("browOuterUpRight")) / 2
    out["ParamBrowLY"] = _clamp(brow_up_l - g("browDownLeft"), -1, 1)
    out["ParamBrowRY"] = _clamp(brow_up_r - g("browDownRight"), -1, 1)
    out["ParamBrowLForm"] = _clamp(-g("browDownLeft"), -1, 1)
    out["ParamBrowRForm"] = _clamp(-g("browDownRight"), -1, 1)
    # ---- 嘴 ----
    smile = (g("mouthSmileLeft") + g("mouthSmileRight")) / 2
    frown = (g("mouthFrownLeft") + g("mouthFrownRight")) / 2
    out["ParamMouthForm"] = _clamp(smile - frown, -1, 1)
    out["ParamMouthOpenY"] = _clamp(g("jawOpen"), 0, 1)
    # ---- 头部姿态（协议直传；clamp ±30 防 app 抖动出界）----
    if f.rot is not None:
        out["ParamAngleX"] = _clamp(f.rot[0], -30, 30)
        out["ParamAngleY"] = _clamp(f.rot[1], -30, 30)
        out["ParamAngleZ"] = _clamp(f.rot[2], -30, 30)
    # ---- 眼球方向（协议直传）----
    if f.eye is not None:
        lx, ly, rx, ry = f.eye
        out["ParamEyeBallX"] = _clamp((lx + rx) / 2, -1, 1)
        out["ParamEyeBallY"] = _clamp((ly + ry) / 2, -1, 1)
    return out
