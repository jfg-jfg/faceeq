"""VMC 输出：把 EQ 后的 ARKit blendshape 发给任何收 VMC 的 3D 软件。

帧 = 一个 OSC bundle（1 UDP 包）：N 条 /VMC/ext/blend/val + 1 条 /VMC/ext/blend/apply。
名字用 ARKit camelCase 字符串（eyeBlinkLeft…，与各发送端同款约定）；VRM0/VRM1 名称
差异由接收端转换（VMagicMirror/Warudo 均内置）。
"""
import math

from pythonosc import osc_bundle_builder, osc_message_builder
from pythonosc.udp_client import SimpleUDPClient


class VmcOutput:
    kind = "vmc"
    DEFAULT_PORT = 39540   # VMC 规范默认端口

    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, send_head=False):
        self._client = SimpleUDPClient(host, int(port))
        self._send_head = send_head
        self._last_rot = None

    def set_head_rot(self, rot):
        """(yaw,pitch,roll) 度，来自捕捉源；send_head 开启时随帧发送。"""
        self._last_rot = rot

    def start(self):
        pass   # 无连接

    def inject(self, params, bs_params=None, face_found=True):
        if not bs_params:
            return
        bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
        for name, w in bs_params.items():
            msg = osc_message_builder.OscMessageBuilder(address="/VMC/ext/blend/val")
            msg.add_arg(str(name))
            msg.add_arg(float(w))
            bundle.add_content(msg.build())
        end = osc_message_builder.OscMessageBuilder(address="/VMC/ext/blend/apply")
        bundle.add_content(end.build())
        if self._send_head and self._last_rot:
            qx, qy, qz, qw = _euler_deg_to_quat(*self._last_rot)
            msg = osc_message_builder.OscMessageBuilder(address="/VMC/ext/face/pos")
            for v in (0.0, 0.0, 0.0, qx, qy, qz, qw):
                msg.add_arg(float(v))
            bundle.add_content(msg.build())
        self._client.send(bundle.build())

    def close(self):
        pass


def _euler_deg_to_quat(yaw, pitch, roll):
    """欧拉角(度) → 四元数 (x,y,z,w)。YXZ 顺序的常规近似；不同软件手性/顺序
    可能要翻符号——真机验收时按需调，不影响 blendshape 主通路。"""
    y = math.radians(yaw) / 2
    p = math.radians(pitch) / 2
    r = math.radians(roll) / 2
    cy, sy = math.cos(y), math.sin(y)
    cp, sp = math.cos(p), math.sin(p)
    cr, sr = math.cos(r), math.sin(r)
    x = sy * cp * cr + cy * sp * sr
    yq = cy * sp * cr + sy * cp * sr
    z = cy * cp * sr - sy * sp * cr
    w = cy * cp * cr - sy * sp * sr
    return x, yq, z, w
