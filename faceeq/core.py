"""单趟管线核心：Frame → signals → bs EQ → 映射 → 平滑 → 各输出空间。

v0.2.0 换轴后的唯一逐帧入口（替代 v0.1.0 的 engine.process_frame）：

    ① emotions.signals(原始 bs) → 情绪向量（+自定义复合表情 +语音偏置）
    ② emotions.bs_amplify(原始 bs, emo) → bs'      ← EQ 唯一发生地
    ③ mapping.base_map(bs', rot, eye) → Live2D 参数  ← 映射后置
    ④ Smoother（核内持有，状态显式）→ 各输出空间的最终值

调用方（GUI worker / CLI）只负责：喂数帧 → 把 StepResult 发给启用的输出。
平滑在核内做，第三个消费端永远不会忘记平滑规则；对口型/眨眼的平滑策略
由 smooth.py 统一（嘴部开合减半）。
"""
from dataclasses import dataclass, field

from .frame import Frame
from .mapping import base_map
from .smooth import Smoother
from . import emotions


@dataclass
class PipelineConfig:
    """一帧的全部可调参数（GUI 每帧覆写对应字段即可实时生效）。"""
    gain: float = 1.4
    smooth: float = 0.4
    emotion_gains: dict = None
    calib: object = None                 # profile.Calib | None
    shaping: object = None               # emotions.Shaping | None
    test_emotion: tuple | None = None    # (情绪名, 强度) 「试表情」
    custom_exprs: dict = None
    custom_act: dict = None
    voice_bias: dict = None


@dataclass
class StepResult:
    params: dict = field(default_factory=dict)    # Live2D 参数（平滑后，VTS 用）
    bs: dict = field(default_factory=dict)        # ARKit blendshape（平滑后，VMC/OSC 用）
    emotions: dict = field(default_factory=dict)  # 情绪向量（监视器/触发用）
    dominant: str = ""                            # 主导情绪（无脸=""）
    face_found: bool = False


class Pipeline:
    """逐帧管线。状态（EMA 平滑 + 断脸保持的最后值）显式挂在实例上。"""

    def __init__(self, config: PipelineConfig | None = None):
        self.cfg = config or PipelineConfig()
        self._sm_params = Smoother(self.cfg.smooth)
        self._sm_bs = Smoother(self.cfg.smooth)
        self._last_params: dict = {}
        self._last_bs: dict = {}
        self._last_emo: dict = {}

    def step(self, frame: Frame) -> StepResult:
        cfg = self.cfg
        self._sm_params.set_strength(cfg.smooth)   # 滑块实时改平滑
        self._sm_bs.set_strength(cfg.smooth)

        if cfg.test_emotion is not None:
            name, strength = cfg.test_emotion
            emo = {e: (strength if e == name else 0.0) for e in emotions.EMOTIONS}
            bs_eq = emotions.bs_amplify(emotions.reference_bs(), emo, cfg.gain,
                                        cfg.emotion_gains, cfg.shaping)
            params = base_map(Frame(bs=bs_eq))
            self._last_params, self._last_bs, self._last_emo = params, bs_eq, emo
            return StepResult(params=self._sm_params.step(params),
                              bs=self._sm_bs.step(bs_eq),
                              emotions=emo, dominant=name, face_found=True)

        # ① 情绪检测（永远吃原始 bs，防 EQ 回灌）
        emo = emotions.signals(frame.bs, calib=cfg.calib) if frame.bs else {}
        dom_custom = None
        if cfg.custom_exprs and cfg.custom_act:
            emo, dom_custom = emotions.apply_custom(emo, cfg.custom_exprs, cfg.custom_act)
        if cfg.voice_bias:
            for e, v in cfg.voice_bias.items():
                if e in emotions.EMOTIONS and v > 0:
                    emo[e] = min(1.0, emo.get(e, 0.0) + v)

        # ② EQ（blendshape 空间，唯一放大处）
        bs_eq = emotions.bs_amplify(frame.bs or {}, emo, cfg.gain,
                                    cfg.emotion_gains, cfg.shaping)

        # ③ 映射后置：Live2D 参数从 EQ 后的 bs' 翻译（头/眼协议直传）
        params = base_map(Frame(bs=bs_eq, rot=frame.rot, eye=frame.eye))

        # 断脸保持：无脸时沿用最后一帧目标（平滑值缓慢收敛在原地，语义与 v0.1.0 一致）
        face_found = bool(frame.bs)
        if face_found:
            self._last_params = params
            self._last_bs = bs_eq
            self._last_emo = emo

        dom = dom_custom or (emotions.dominant(self._last_emo) if face_found else "")
        return StepResult(params=self._sm_params.step(self._last_params),
                          bs=self._sm_bs.step(self._last_bs),
                          emotions=self._last_emo, dominant=dom, face_found=face_found)
