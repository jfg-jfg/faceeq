"""iFacialMocap / MeowFace 兼容 UDP 面捕源（iOS TrueDepth / 安卓）。

用：iPad/手机与 PC 同一局域网 → app 里填本机 IP、端口 49983 开始发送
（首次可能弹 Windows 防火墙允许框，放行 UDP）。本类只收不渲染：
read() 吐最新解析帧；断流超过 stale_after 秒 → 空 Frame（带节流）。
无数据时每 2s 广播一次官方握手串（iFacialMocap 需要握手触发；MeowFace 直发也不冲突）。
"""
import os
import socket
import sys
import time

from ..frame import Frame

PHONE_PORT = 49983          # 生态默认 UDP 端口（MeowFace 可在 app 里改，CLI/GUI 可配）
_PHONE_MAGIC = "iFacialMocap_sahuasouryya9218sauhuiayeta91555dy3719"   # 官方握手串
_EYE_MAX_DEG = 40.0         # 眼球最大转角（度），用于把眼欧拉归一到 -1..1
# 轴映射/符号是按 Live2D 语义定的一版假设（yaw/pitch/roll、眼球正方向）。
# 真机验收时若方向不对，只改这里两个元组，别动解析逻辑。
# （冲刺① iPad 离线验收已确认 TrueDepth 读数质量；符号绑定验收待实时流。）
_ROT_SIGN = (1.0, 1.0, 1.0)   # (yaw, pitch, roll) 符号
_EYE_SIGN = (1.0, 1.0)        # (眼球X, 眼球Y) 符号


def _phone_name_to_mp(name: str) -> str:
    """iFacialMocap 的 _L/_R 后缀 → MediaPipe 生态的 Left/Right（基础名两生态一致）。"""
    if name.endswith("_L"):
        return name[:-2] + "Left"
    if name.endswith("_R"):
        return name[:-2] + "Right"
    return name


def _floats(s: str) -> list:
    out = []
    for x in s.split(","):
        try:
            out.append(float(x))
        except ValueError:
            continue
    return out


def parse_phone_packet(data: bytes) -> dict | None:
    """解析一帧 iFacialMocap/MeowFace UDP 文本帧 → {"bs","rot","eye"}；无法解析返回 None。

    帧结构（官方 v1 原样，`|` 分节）：blendshape 各占一节 `名称-数值`（数值 0~100，
    后缀 _L/_R），末尾三节 `=head#欧拉X,Y,Z(度),位置X,Y,Z`、`rightEye#欧拉X,Y,Z`、
    `leftEye#欧拉X,Y,Z`。v2 请求帧的键值分隔为 `&`（数值可负），这里两种都容忍、
    未知节跳过。eyeWide 手机端有独立通道。
    """
    s = data.decode("utf-8", errors="ignore") if isinstance(data, (bytes, bytearray)) else ""
    if not s:
        return None
    bs = {}
    rot = None
    l_eye = r_eye = None
    for part in s.split("|"):
        if not part:
            continue
        if part.startswith("=head#"):
            vals = _floats(part[6:])
            if len(vals) >= 3:
                ex, ey, ez = vals[0], vals[1], vals[2]
                # 欧拉 X=点头(pitch) Y=转头(yaw) Z=歪头(roll)
                rot = (_ROT_SIGN[0] * ey, _ROT_SIGN[1] * ex, _ROT_SIGN[2] * ez)
        elif part.startswith("leftEye#"):
            vals = _floats(part[8:])
            if len(vals) >= 2:
                l_eye = vals
        elif part.startswith("rightEye#"):
            vals = _floats(part[9:])
            if len(vals) >= 2:
                r_eye = vals
        else:
            # blendshape 节：v1 `名称-数值`；v2 `名称&数值`（数值可负 → 不用 rsplit）
            if "&" in part:
                name, raw = part.split("&", 1)
            elif "-" in part:
                name, raw = part.rsplit("-", 1)
            else:
                continue
            try:
                v = float(raw) / 100.0
            except ValueError:
                continue
            bs[_phone_name_to_mp(name.strip())] = max(0.0, min(1.0, v))
    if l_eye is not None or r_eye is not None:
        sx, sy = _EYE_SIGN
        l_x, l_y = (l_eye[0], l_eye[1]) if l_eye and len(l_eye) >= 2 else (0.0, 0.0)
        r_x, r_y = (r_eye[0], r_eye[1]) if r_eye and len(r_eye) >= 2 else (0.0, 0.0)
        # 欧拉 Y=左右 → 眼球 X；X=上下 → 眼球 Y（符号真机可校）
        eye = (max(-1.0, min(1.0, sx * l_y / _EYE_MAX_DEG)),
               max(-1.0, min(1.0, -sy * l_x / _EYE_MAX_DEG)),
               max(-1.0, min(1.0, sx * r_y / _EYE_MAX_DEG)),
               max(-1.0, min(1.0, -sy * r_x / _EYE_MAX_DEG)))
    else:
        eye = None
    if not bs and rot is None and eye is None:
        return None
    return {"bs": bs, "rot": rot, "eye": eye}


class PhoneInput:
    """手机面捕源：绑定 UDP 端口收 iFacialMocap/MeowFace 兼容流。"""

    label = "phone-udp"

    def __init__(self, port: int = PHONE_PORT, stale_after: float = 1.0):
        self._port = port
        self._stale_after = stale_after
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(("0.0.0.0", self._port))
        except OSError:
            sys.stderr.write(f"[phone] UDP {self._port} 绑定失败（被占用？）\n")
            raise
        self._latest = None
        self._last_recv = 0.0
        self._next_handshake = 0.0
        # 用户方向系数 (yaw, pitch, roll, eyeX, eyeY)：+1 正常 / -1 镜像 / 0 冻结 / 中间=阻尼
        self.orientation = [1.0, 1.0, 1.0, 1.0, 1.0]

    def set_orientation(self, yaw=1.0, pitch=1.0, roll=1.0, eye_x=1.0, eye_y=1.0):
        """GUI 方向滑块实时写入（乘法系数，叠在 _ROT_SIGN/_EYE_SIGN 硬件基线之上）。"""
        self.orientation = [yaw, pitch, roll, eye_x, eye_y]

    def start(self):
        pass   # __init__ 已绑定

    def read(self) -> Frame:
        now = time.time()
        if self._latest is None and now >= self._next_handshake:
            self._next_handshake = now + 2.0
            try:
                self._sock.sendto(_PHONE_MAGIC.encode("utf-8"),
                                  ("255.255.255.255", self._port))
            except OSError:
                pass
        while True:   # 排空到最新一帧：手机 60FPS > 处理 30FPS，防积压拖延迟
            try:
                data, _addr = self._sock.recvfrom(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            parsed = parse_phone_packet(data)
            if parsed:
                self._latest = parsed
                self._last_recv = time.time()
        if self._latest is None or (time.time() - self._last_recv) > self._stale_after:
            # 断流/未连接时空帧节流到 ~30fps：read() 非阻塞，不节流会让 GUI/CLI
            # worker 忙循环烧 CPU（实测空转上万 fps）。
            time.sleep(1.0 / 30)
            return Frame()
        p = self._latest
        oy, op, orr, exs, eys = self.orientation
        rot = tuple(c * v for c, v in zip((oy, op, orr), p["rot"])) if p["rot"] else None
        eye = ((exs * p["eye"][0], eys * p["eye"][1],
                exs * p["eye"][2], eys * p["eye"][3])) if p["eye"] else None
        return Frame(bs=p["bs"], rot=rot, eye=eye)

    def is_stale(self) -> bool:
        """是否未连接/断流（GUI 状态提示用）。"""
        return self._latest is None or (time.time() - self._last_recv) > self._stale_after

    def release(self):
        try:
            self._sock.close()
        except OSError:
            pass
