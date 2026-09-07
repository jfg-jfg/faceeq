"""VMC 协议面捕输入：接收 VSeeFace / Warudo 等 PC 追踪软件发出的 blendshape 流。

FaceEQ 作为 VMC 接收端（端口默认 39539，避开自家 VMC 输出默认的 39540）：
- /VMC/ext/blend/val <ARKit名> <权重0..1>  → 累积到最新帧
- /VMC/ext/blend/apply                     → 帧结束标记
- /VMC/ext/face/pos <px,py,pz> <qx,qy,qz,qw> → 头旋转（四元数→欧拉，度）

VSeeFace 注意：完整 52 形状需要 Perfect Sync 模型，否则 frown/sneer 等值可能稀疏。
"""
import math
import socket
import threading
import time

from pythonosc import dispatcher, osc_server

from ..frame import Frame

VMC_INPUT_PORT = 39539


def _quat_to_euler(qx, qy, qz, qw):
    """四元数 → (yaw, pitch, roll) 度，YXZ 提取（Unity 系惯例）。符号真机可校。"""
    yaw = math.degrees(math.atan2(2 * (qw * qy + qx * qz),
                                  1 - 2 * (qy * qy + qz * qz)))
    t = max(-1.0, min(1.0, 2 * (qw * qx - qy * qz)))
    pitch = math.degrees(math.asin(t))
    roll = math.degrees(math.atan2(2 * (qw * qz + qx * qy),
                                   1 - 2 * (qx * qx + qy * qy)))
    return yaw, pitch, roll


class VmcInput:
    """VMC 面捕源：绑定 UDP 端口，收 blendshape + 头旋转，吐 Frame。"""

    label = "vmc-udp"

    def __init__(self, port: int = VMC_INPUT_PORT, stale_after: float = 1.0):
        self._port = port
        self._stale_after = stale_after
        self._lock = threading.Lock()
        self._bs: dict = {}
        self._rot = None
        self._last_recv = 0.0
        self._server = None
        # 用户方向系数 (yaw, pitch, roll)：+1 正常 / -1 镜像 / 0 冻结（eye 通道 VMC 无）
        self.orientation = [1.0, 1.0, 1.0]

    def set_orientation(self, yaw=1.0, pitch=1.0, roll=1.0, eye_x=1.0, eye_y=1.0):
        self.orientation = [yaw, pitch, roll]

    def start(self):
        disp = dispatcher.Dispatcher()
        disp.map("/VMC/ext/blend/val", self._on_blend_val)
        disp.map("/VMC/ext/face/pos", self._on_face_pos)

        class _Server(osc_server.ThreadingOSCUDPServer):
            allow_reuse_addr = True   # 快速重启不撞 TIME_WAIT

        self._server = _Server(("0.0.0.0", self._port), disp)
        threading.Thread(target=self._server.serve_forever, daemon=True,
                         name="vmc-input").start()

    def _on_blend_val(self, _addr, name: str, weight: float):
        with self._lock:
            self._bs[str(name)] = max(0.0, min(1.0, float(weight)))
            self._last_recv = time.time()

    def _on_face_pos(self, _addr, *vals):
        try:
            qx, qy, qz, qw = (float(v) for v in vals[3:7])
        except (ValueError, IndexError, TypeError):
            return
        with self._lock:
            self._rot = _quat_to_euler(qx, qy, qz, qw)
            self._last_recv = time.time()

    def read(self) -> Frame:
        now = time.time()
        with self._lock:
            bs = dict(self._bs)
            rot0 = self._rot
            stale = (now - self._last_recv) > self._stale_after if self._last_recv else True
        if stale:
            # 断流空帧节流（与手机源一致，防调用方忙循环）
            time.sleep(1.0 / 30)
            return Frame()
        oy, op, orr = self.orientation
        rot = tuple(c * v for c, v in zip((oy, op, orr), rot0)) if rot0 else None
        return Frame(bs=bs, rot=rot)

    def is_stale(self) -> bool:
        with self._lock:
            return (not self._bs) or (time.time() - self._last_recv) > self._stale_after

    def release(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
