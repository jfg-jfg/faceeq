"""输出适配层：把 EQ 后的参数喂给不同目标软件（多输出支持）。

三种输出适配器，同一 inject 语义（每帧一次）：
- VTSOutput：VTube Studio（Live2D 参数空间注入，包装 vts_bridge.VTSBridge）
- VmcOutput：VMC 协议（OSC over UDP）→ Warudo / VNyan / VSeeFace / VRM 系 3D 工具，
  发送放大后的 ARKit blendshape（/VMC/ext/blend/val，字符串名 + blend/apply 收帧，
  与 VSeeFace 发送端实现和官方规范一致）
- OscRawOutput：通用 OSC（VRChat FT 等）：默认 prefix/bs/<ARKit名>，可选
  osc_mapping.json（{blendshape 名: 完整 OSC 地址}）精确映射到目标参数。

工厂 create_output(kind, host, port) 供 GUI/CLI 统一创建。
容错语义：VMC/OSC 是无连接 UDP，inject 不抛连接错误；VTS 断线由 VTSBridge
抛 ConnectionError（调用方据此重连）。
"""
import json
import math
import os

from .vts_bridge import VTSBridge

OSC_MAPPING_FILE = "osc_mapping.json"   # OscRawOutput 的可选名字映射


class OutputAdapter:
    kind = "?"

    def start(self):
        """建立连接/初始化。阻塞型目标（VTS）在此做鉴权等。"""

    def inject(self, params: dict, bs_params: dict, face_found: bool = True):
        """每帧注入。params=Live2D 参数空间（VTS 用），bs_params=放大后 ARKit
        blendshape（VMC/OSC 用）。"""

    def close(self):
        pass


class VTSOutput(OutputAdapter):
    """VTube Studio 输出：包装既有 VTSBridge，行为与历史版本一致。"""

    kind = "vts"

    def __init__(self):
        self.bridge = VTSBridge()

    def start(self):
        self.bridge.start()          # connect + auth + discover + ensure_custom_params

    def inject(self, params, bs_params=None, face_found=True):
        if params:
            self.bridge.inject(params, face_found=face_found)

    def list_hotkeys(self):
        """当前模型的热键列表（供情绪触发配置）。"""
        return self.bridge.list_hotkeys()

    def trigger_hotkey(self, hotkey_id):
        self.bridge.trigger_hotkey(hotkey_id)

    def close(self):
        self.bridge.close()


class VmcOutput(OutputAdapter):
    """VMC 协议输出：把放大后的 ARKit blendshape 发给任何收 VMC 的 3D 软件。

    帧 = 一个 OSC bundle（1 UDP 包）：N 条 /VMC/ext/blend/val + 1 条 /VMC/ext/blend/apply。
    名字用 ARKit camelCase 字符串（eyeBlinkLeft…，与 MediaPipe 检测键一致；VSeeFace
    发送端同款约定）。VRM0/VRM1 名称差异由接收端转换（VMagicMirror/Warudo 均内置）。
    """

    kind = "vmc"
    DEFAULT_PORT = 39540   # VMC 规范默认端口

    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT,
                 send_head=False):
        from pythonosc.udp_client import SimpleUDPClient
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
        from pythonosc import osc_bundle_builder, osc_message_builder
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


class OscRawOutput(OutputAdapter):
    """通用 OSC 输出：给没有 VMC 的目标（如 VRChat FT 桥）。

    无映射文件：每形状发 <prefix>/bs/<ARKit名>；有 osc_mapping.json
    （{blendshape 名: 完整 OSC 地址}）：只发映射了的形状（精确对接目标参数）。
    """

    kind = "osc"
    DEFAULT_PORT = 9000     # VRChat OSC 惯例端口

    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, prefix="/faceeq",
                 mapping=None):
        from pythonosc.udp_client import SimpleUDPClient
        self._client = SimpleUDPClient(host, int(port))
        self._prefix = prefix.rstrip("/") or "/faceeq"
        self._mapping = dict(mapping or {})

    def start(self):
        pass

    def inject(self, params, bs_params=None, face_found=True):
        if not bs_params:
            return
        if self._mapping:
            for src, addr in self._mapping.items():
                if src in bs_params:
                    self._client.send_message(addr, float(bs_params[src]))
        else:
            for name, w in bs_params.items():
                self._client.send_message(f"{self._prefix}/bs/{name}", float(w))

    def close(self):
        pass


def load_osc_mapping(path=OSC_MAPPING_FILE):
    """读 osc_mapping.json（容错：缺失/坏 JSON → 无映射，用 prefix 模式）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if k and v}


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
