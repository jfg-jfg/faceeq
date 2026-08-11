"""
blendshape / 特征点 → 原始 Live2D 映射信号（base_map）。

本模块只做「翻译」：把 blendshape / 特征点几何转成 Live2D 参数的原始值，
**不做放大、不做最终 clamp**。放大（全局 gain + 按情绪差异化）交给 emotions.amplify。

混合输入（设计里定的）：
- 表情（眉/眼/嘴）← ARKit blendshape（稳定）
- 头部姿态 / 眼球方向 ← 特征点几何（blendshape 给不了 yaw/pitch/roll）
"""
import numpy as np

from .capture import Frame

# ---- 特征点索引（仅用于头部姿态 + 眼球方向；眼睛/嘴开合走 blendshape）----
_HEAD   = [33, 133, 362, 263, 1, 454, 234, 10, 152]  # 头部姿态
_L_IRIS = [473, 362, 263]                             # 右虹膜 + 右眼内外角
_R_IRIS = [468, 33, 133]                              # 左虹膜 + 左眼内外角

# ---- 各参数取值范围（来自 Haru 实测，供 emotions.amplify 做 clamp）----
RANGES = {
    "ParamEyeLOpen": (0, 2), "ParamEyeROpen": (0, 2),
    "ParamEyeLSmile": (0, 1), "ParamEyeRSmile": (0, 1),
    "ParamEyeBallX": (-1, 1), "ParamEyeBallY": (-1, 1),
    "ParamBrowLY": (-1, 1), "ParamBrowRY": (-1, 1),
    "ParamBrowLForm": (-1, 1), "ParamBrowRForm": (-1, 1),
    "ParamMouthForm": (-1, 1), "ParamMouthOpenY": (0, 1),
    "ParamAngleX": (-30, 30), "ParamAngleY": (-30, 30), "ParamAngleZ": (-30, 30),
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _head_pose(pts):
    """从特征点几何算 roll/yaw/pitch（度）。pts 对应 _HEAD 的 9 个点。"""
    le = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
    re = ((pts[2][0] + pts[3][0]) / 2, (pts[2][1] + pts[3][1]) / 2)
    roll = float(np.degrees(np.arctan((re[1] - le[1]) / (re[0] - le[0] + 1e-6))))
    nose_l = abs(pts[4][0] - pts[6][0])   # 鼻到左脸缘
    nose_r = abs(pts[5][0] - pts[4][0])   # 右脸缘到鼻
    yaw = float(np.degrees(np.arcsin(
        _clamp((nose_l - nose_r) / (nose_l + nose_r + 1e-6), -1, 1))))
    pitch = float(np.degrees(np.arctan(
        (pts[8][2] - pts[7][2]) / (pts[7][1] - pts[8][1] + 1e-6))))
    return roll, yaw, pitch


def _eye_ball_x(iris):
    """水平眼球方向（-1..1）。iris = [_L_IRIS, _R_IRIS] 共 6 点。"""
    l_iris, l_in, l_out = iris[0], iris[1], iris[2]
    r_iris, r_in, r_out = iris[3], iris[4], iris[5]
    lc = (l_in[0] + l_out[0]) / 2
    lx = (l_iris[0] - lc) / (l_out[0] - l_in[0] + 1e-6) * 2
    rc = (r_in[0] + r_out[0]) / 2
    rx = (r_iris[0] - rc) / (r_out[0] - r_in[0] + 1e-6) * 2
    return _clamp((lx + rx) / 2, -1, 1)


def base_map(f: Frame) -> dict:
    """一帧面捕 → 原始映射信号（无放大、无最终 clamp）。放大交给 emotions.amplify。"""
    out = {}
    if not f.lms:
        return out
    g = f.bs_get

    def p(idx):             # 取第 idx 个特征点 (x,y,z)
        return f.lms[idx]

    # ---- 眼睛开合（眨眼）----
    out["ParamEyeLOpen"] = 1.0 - g("eyeBlinkLeft")
    out["ParamEyeROpen"] = 1.0 - g("eyeBlinkRight")
    # ---- 眼睛笑（眯眼）----
    out["ParamEyeLSmile"] = g("eyeSquintLeft")
    out["ParamEyeRSmile"] = g("eyeSquintRight")
    # ---- 眼球方向 ----
    iris = [p(i) for i in (_L_IRIS + _R_IRIS)]
    out["ParamEyeBallX"] = _eye_ball_x(iris)
    # ---- 眉毛 ----
    brow_up_l = (g("browInnerUp") + g("browOuterUpLeft")) / 2
    brow_up_r = (g("browInnerUp") + g("browOuterUpRight")) / 2
    out["ParamBrowLY"] = brow_up_l - g("browDownLeft")
    out["ParamBrowRY"] = brow_up_r - g("browDownRight")
    out["ParamBrowLForm"] = -g("browDownLeft")
    out["ParamBrowRForm"] = -g("browDownRight")
    # ---- 嘴 ----
    smile = (g("mouthSmileLeft") + g("mouthSmileRight")) / 2
    frown = (g("mouthFrownLeft") + g("mouthFrownRight")) / 2
    out["ParamMouthForm"] = smile - frown
    out["ParamMouthOpenY"] = g("jawOpen")
    # ---- 头部姿态 ----
    hp = [p(i) for i in _HEAD]
    roll, yaw, pitch = _head_pose(hp)
    out["ParamAngleX"] = yaw
    out["ParamAngleY"] = pitch
    out["ParamAngleZ"] = roll
    return out
