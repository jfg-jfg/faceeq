"""每参数 EMA 平滑：消抖又保低延迟。

和 render.py 里的平滑同算法、同参数（为避免动 render.py 拖累已验证的预览路径，
这里复制一份给 VTS 注入路径用；两条路径输入相同 → 收敛到同一组值，预览和 VTS 一致）。

- 对口型参数（ParamMouthOpenY）平滑减半：快车道，嘴要零延迟。
- strength∈[0,1] 是总强度；a = max(0.05, 1 - 强度) 是每帧收敛比例。
"""
_MOUTH = {"ParamMouthOpenY"}


class Smoother:
    def __init__(self, strength: float = 0.7):
        self._s = strength
        self._cur = {}   # 参数名 -> 当前平滑后的值

    def set_strength(self, s: float):
        """实时改平滑强度（GUI worker 每帧调用）。"""
        self._s = s

    def step(self, targets: dict) -> dict:
        """把 {参数名: 目标值} 做一步 EMA，返回平滑后的同名字典。"""
        out = {}
        for name, val in targets.items():
            s = self._s * (0.5 if name in _MOUTH else 1.0)
            a = max(0.05, 1.0 - s)
            if name in self._cur:
                val = self._cur[name] + a * (val - self._cur[name])
            self._cur[name] = val
            out[name] = val
        return out
