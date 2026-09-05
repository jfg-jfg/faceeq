"""共享引擎：逐帧处理核心（capture→base_map→signals→amplify）。

供 main.py（CLI）和 gui.py（FaceEQWorker）共用，避免循环逻辑两份漂移。
注入（VTS/VMC/OSC 注入、本地预览）由调用方各自处理（gui 有重连、main 有预览）。
"""
from dataclasses import dataclass, field

from .mapping import base_map
from . import emotions


@dataclass
class FrameResult:
    """一帧处理产物。params=Live2D 参数空间（VTS 注入）；
    bs_params=ARKit blendshape 空间（VMC/OSC 输出）；emotions=情绪强度（监视器/触发）。"""
    params: dict = field(default_factory=dict)
    dominant: str = ""
    face_found: bool = False
    bs_params: dict = field(default_factory=dict)
    emotions: dict = field(default_factory=dict)


def process_frame(f, gain, emotion_gains, calib=None, shaping=None, test_emotion=None,
                  custom_exprs=None, custom_act=None, voice_bias=None) -> FrameResult:
    """处理一帧面捕数据。

    f: Capture.read() 返回的 Frame（含 .bs blendshape 字典 + .img 画面）。
    gain: 全局放大倍数。emotion_gains: {情绪: -1..1}。calib: profile.Calib|None。
    shaping: emotions.Shaping|None（None=默认塑造）。
    test_emotion: (情绪名, 强度) 或 None——「试表情」模式：跳过面捕，用参考底 pose +
      合成情绪值走 amplify，不照镜子预览塑造效果（GUI 调规则用）。
    custom_exprs/custom_act: 自定义复合表情定义 {名字: {情绪: 权重}} 与激活度
      {名字: 0..1}——加权叠加到检测情绪上再走 amplify（见 emotions.apply_custom）。
    voice_bias: {情绪: 偏置 0..1} 或 None——语音情绪引擎的注入（additive，见 voice.py）。
    返回 FrameResult：
      params: 放大后的 Live2D 参数字典（可能全 0 如无脸）——VTS 输出用。
      dominant: 主导情绪名（无脸时 ""；自定义注入主导时为其名字）。
      face_found: 是否检测到脸。
      bs_params: 放大后的 ARKit blendshape 字典——VMC/OSC 输出用（无脸时 {}）。
      emotions: 参与放大的情绪向量（监视器/触发用）。
    """
    if test_emotion is not None:
        name, strength = test_emotion
        emo = {e: (strength if e == name else 0.0) for e in emotions.EMOTIONS}
        params = emotions.amplify(emotions.reference_pose(), emo, global_gain=gain,
                                  emotion_gains=emotion_gains, shaping=shaping)
        bs_out = emotions.bs_amplify(emotions.reference_bs(), emo, global_gain=gain,
                                     emotion_gains=emotion_gains, shaping=shaping)
        return FrameResult(params=params, dominant=name, face_found=True,
                           bs_params=bs_out, emotions=emo)
    base = base_map(f)
    emo = emotions.signals(f.bs, calib=calib) if f.bs else {}
    dom_custom = None
    if custom_exprs and custom_act:
        emo, dom_custom = emotions.apply_custom(emo, custom_exprs, custom_act)
    if voice_bias:
        for e, v in voice_bias.items():
            if e in emotions.EMOTIONS and v > 0:
                emo[e] = min(1.0, emo.get(e, 0.0) + v)
    params = emotions.amplify(base, emo, global_gain=gain,
                              emotion_gains=emotion_gains, shaping=shaping)
    bs_out = emotions.bs_amplify(f.bs or {}, emo, global_gain=gain,
                                 emotion_gains=emotion_gains, shaping=shaping)
    dom = emotions.dominant(emo) if f.bs else ""
    if dom_custom:
        dom = dom_custom
    return FrameResult(params=params, dominant=dom, face_found=bool(f.bs),
                       bs_params=bs_out, emotions=emo)
