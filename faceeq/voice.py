"""语音情绪引擎（实验特性）：麦克风声学特征 → 情绪偏置向量。

v1 是可解释的规则映射，不依赖训练模型（无几十 MB 的 SER 依赖）：
- 能量（RMS×灵敏度）= 唤醒度——说话越大声，情绪注入越强；
- 频谱质心（亮度）= 效价——明亮（笑闹/上扬）偏 happy/surprised，低沉偏 angry；
- 语音活动门限：安静/环境音 → 零偏置，不影响面捕 EQ；
- 快攻慢放 EMA：偏置瞬时抬升、松开后 ~0.5s 衰减，不闪烁。

输出经 engine.voice_bias 通道 additive 叠进情绪向量（persona 滑块照常生效）。
纯函数（features_from_pcm / bias_from_features）与采集类分离，smoke 可测。
"""
import threading
from collections import deque

import numpy as np

_GATE = 0.05          # 能量门限：以下视为静音/环境音
_BRIGHT_LO, _BRIGHT_HI = 300.0, 3500.0   # 频谱质心归一范围（Hz），覆盖人声主能量区
_ATTACK, _RELEASE = 1.0, 0.85           # EMA：瞬时抬升 / 每次读数衰减


def _clamp01(v):
    return max(0.0, min(1.0, v))


def features_from_pcm(pcm, samplerate: int):
    """一帧 PCM(float32, -1..1) → (energy, brightness)，均 0..1。

    energy=RMS；brightness=频谱质心归一（300~3500Hz）。空帧/短帧 → (0, 0)。
    """
    pcm = np.asarray(pcm, dtype=np.float32)
    if pcm.size < 32:
        return 0.0, 0.0
    rms = float(np.sqrt(np.mean(pcm * pcm)))
    win = np.hanning(pcm.size).astype(np.float32)
    spec = np.abs(np.fft.rfft(pcm * win))
    freqs = np.fft.rfftfreq(pcm.size, 1.0 / samplerate)
    total = float(spec.sum())
    centroid = float((spec * freqs).sum() / total) if total > 1e-9 else 0.0
    brightness = _clamp01((centroid - _BRIGHT_LO) / (_BRIGHT_HI - _BRIGHT_LO))
    return rms, brightness


def bias_from_features(energy: float, brightness: float, sensitivity: float = 1.0) -> dict:
    """(能量, 亮度) → {情绪: 偏置 0..1}。

    energy 先乘 sensitivity 再过门限（门限以下 = 静音 → 空 dict）。
    亮度高于中带 → happy（很亮再加 surprised）；低于中带 → angry。
    """
    e = _clamp01(energy * sensitivity - _GATE)
    if e <= 0.0:
        return {}
    bright_margin_hi = max(0.0, brightness - 0.45)
    bright_margin_lo = max(0.0, 0.42 - brightness)
    out = {
        "happy": _clamp01(e * bright_margin_hi * 1.8),
        "surprised": _clamp01(e * max(0.0, brightness - 0.68) * 1.2),
        "angry": _clamp01(e * bright_margin_lo * 1.8),
    }
    return {k: v for k, v in out.items() if v > 0.0}


def smooth_bias(prev: dict, target: dict, strength: float = 1.0) -> dict:
    """快攻慢放：新偏置 = max(目标值×strength, 旧值×衰减)。纯函数。

    说话时瞬时抬升（attack=1），安静后按 0.85/帧 衰减（release），视觉上不闪烁。
    """
    t = {e: v * strength for e, v in (target or {}).items()}
    out = {}
    for e in set(prev or {}) | set(t):
        v = max(t.get(e, 0.0), (prev or {}).get(e, 0.0) * _RELEASE)
        if v > 1e-4:
            out[e] = v
    return out


class VoiceCapture:
    """sounddevice 输入流：callback 攒特征帧，read_bias() 由 worker 每帧调用（非阻塞）。

    依赖 sounddevice（pip install sounddevice，Windows wheel 自带 PortAudio）。
    设备缺钻石化/流打开失败 → raise，由调用方容错（GUI 提示，EQ 主链路不受影响）。
    """

    def __init__(self, device=None, samplerate: int = 16000, block_ms: int = 100,
                 sensitivity: float = 1.0):
        import sounddevice as sd
        self._sr = samplerate
        self._sensitivity = sensitivity
        self._lock = threading.Lock()
        self._buf = deque(maxlen=10)          # 最近 ~1s 的 (energy, brightness)
        self._smooth = {}                     # 情绪 → 衰减中的偏置
        self._stream = sd.InputStream(
            device=device, samplerate=samplerate, channels=1, dtype="float32",
            blocksize=max(1, int(samplerate * block_ms / 1000)), callback=self._cb)
        self._stream.start()

    def _cb(self, indata, frames, time_info, status):   # sounddevice 音频线程
        try:
            en, br = features_from_pcm(indata[:, 0], self._sr)
            with self._lock:
                self._buf.append((en, br))
        except Exception:
            pass   # 音频线程绝不上抛

    def set_sensitivity(self, s: float):
        with self._lock:
            self._sensitivity = max(0.1, float(s))

    def read_bias(self, strength: float = 1.0) -> dict:
        """聚合缓冲 → 快攻慢放偏置 {情绪: 0..1}（已乘 strength 0..1）。"""
        with self._lock:
            frames = list(self._buf)
            self._buf.clear()
            sens = self._sensitivity
        target = {}
        if frames:
            energy = max(en for en, _ in frames)          # 说话爆发取峰值
            brightness = sum(br for _, br in frames) / len(frames)
            target = bias_from_features(energy, brightness, sens)
        self._smooth = smooth_bias(self._smooth, target, strength)
        return self._smooth

    def close(self):
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass


def list_input_devices():
    """枚举输入设备 [(index, name)]。sounddevice 缺失/无设备 → []。"""
    try:
        import sounddevice as sd
    except Exception:
        return []
    try:
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                out.append((i, str(d.get("name", f"device {i}"))))
        return out
    except Exception:
        return []
