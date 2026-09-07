"""输入适配层：所有面捕源的统一接口（与 outputs 对称）。

FaceEQ v0.2.0 是纯协议 EQ 中间件——输入永远是「已经追踪好的 blendshape 流」，
自己不做任何面部检测。两个实现：
- PhoneInput：iFacialMocap / MeowFace 兼容 UDP（iOS TrueDepth / 安卓）；
- VmcInput：VMC 协议输入（VSeeFace / Warudo 等 PC 追踪软件，blendshape + 头旋转）。
"""
from ..frame import Frame


class InputAdapter:
    """面捕源接口。start() 后 read() 每帧调用；断流时 read() 返回空 Frame
    （带 ~30fps 节流，防调用方忙循环烧 CPU）。"""

    label = "?"

    def start(self):
        """绑定端口/启动接收线程。阻塞型初始化在这里做。"""

    def read(self) -> Frame:
        """取最新一帧（非阻塞）。无数据/断流 → 空 Frame。"""
        return Frame()

    def is_stale(self) -> bool:
        """是否未连接/断流（GUI 状态提示用）。"""
        return False

    def set_orientation(self, yaw=1.0, pitch=1.0, roll=1.0, eye_x=1.0, eye_y=1.0):
        """方向系数（-1..1 滑块）：镜像/冻结/阻尼各轴。不支持 eye 的源忽略 eye_*。"""

    def release(self):
        """释放端口/线程。"""


def create_input(kind: str, **kw) -> InputAdapter:
    """输入源工厂：kind = "phone" | "vmc"。GUI / main.py / calibrate 共用。"""
    if kind == "phone":
        from .phone import PhoneInput
        return PhoneInput(**kw)
    if kind == "vmc":
        from .vmc import VmcInput
        return VmcInput(**kw)
    raise ValueError(f"未知输入源: {kind}")
