"""共享引擎：逐帧处理核心（capture→base_map→signals→amplify）。

供 main.py（CLI）和 gui.py（FaceEQWorker）共用，避免循环逻辑两份漂移。
注入（VTS inject / 本地预览）由调用方各自处理（gui 有重连、main 有预览）。
"""
from .mapping import base_map
from . import emotions


def process_frame(f, gain, emotion_gains, calib=None):
    """处理一帧面捕数据。

    f: Capture.read() 返回的 Frame（含 .bs blendshape 字典 + .img 画面）。
    gain: 全局放大倍数。emotion_gains: {情绪: -1..1}。calib: profile.Calib|None。
    返回 (params, dominant, face_found)：
      params: 放大后的 Live2D 参数字典（可能全 0 如无脸）。
      dominant: 主导情绪名（无脸时 ""）。
      face_found: 是否检测到脸。
    """
    base = base_map(f)
    emo = emotions.signals(f.bs, calib=calib) if f.bs else {}
    params = emotions.amplify(base, emo, global_gain=gain, emotion_gains=emotion_gains)
    dom = emotions.dominant(emo) if f.bs else ""
    return params, dom, bool(f.bs)
