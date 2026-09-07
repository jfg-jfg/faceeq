"""面捕一帧数据：所有输入适配器（手机 UDP / VMC）的统一产出。

bs=ARKit blendshape 名→权重[0,1]（检测器原始读数，EQ 的唯一作用对象）；
rot=(yaw,pitch,roll) 度（头旋转，协议直传）；eye=(lx,ly,rx,ry) ∈-1..1（眼球）。
v0.2.0 起不再有 webcam/特征点：表情永远走协议 blendshape，头/眼永远协议直传。
"""
from dataclasses import dataclass, field


@dataclass
class Frame:
    bs: dict = field(default_factory=dict)
    rot: tuple | None = None
    eye: tuple | None = None

    def bs_get(self, name: str, default: float = 0.0) -> float:
        """按名取 blendshape（缺失键=0），映射层统一入口。"""
        return self.bs.get(name, default)

    def __bool__(self) -> bool:
        """有脸 = 有 blendshape 数据（断流/未连接时为空 Frame）。"""
        return bool(self.bs)


def empty_frame() -> Frame:
    return Frame()
