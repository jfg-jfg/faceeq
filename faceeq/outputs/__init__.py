"""输出适配层：FaceEQ 处理结果 → 各目标软件。

三个实现（可多选并发，worker 逐个 inject）：
- VTSOutput：VTube Studio WebSocket 参数注入（Live2D；断线自动指数退避重连）
- VmcOutput：VMC 协议（OSC/UDP 39540，ARKit blendshape → Warudo/VNyans/VSeeFace/VRM 系）
- OscRawOutput：通用 OSC（prefix 或 osc_mapping.json 精确映射）
"""
from .vts import VTSOutput
from .vmc import VmcOutput
from .osc import OscRawOutput, load_osc_mapping


def create_output(kind, host=None, port=None):
    """按 GUI/CLI 的输出目标建适配器。kind: vts | vmc | osc。"""
    if kind == "vts":
        return VTSOutput()
    if kind == "vmc":
        return VmcOutput(host or "127.0.0.1", int(port or VmcOutput.DEFAULT_PORT))
    if kind == "osc":
        return OscRawOutput(host or "127.0.0.1", int(port or OscRawOutput.DEFAULT_PORT),
                            mapping=load_osc_mapping())
    raise ValueError(f"未知输出目标: {kind}")
