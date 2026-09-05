"""
摄像头面捕模块：MediaPipe FaceLandmarker → 每帧返回 (blendshape 字典, 特征点列表)。

两个捕捉源，同一 Frame 接口（GUI/CLI/校准经 open_source 工厂选择）：
- Capture：webcam → MediaPipe（blendshape + 478 特征点；头部姿态/眼球靠特征点几何）。
- PhoneCapture：手机 app（iFacialMocap / MeowFace 兼容 UDP 协议）→ 52 blendshape
  + 头部旋转 + 眼球欧拉。TrueDepth 精度能读到 webcam 欠读的细微 AU（sad/disgust 的
  AU15/AU1/AU9），且不占摄像头（VTS 摄像头冲突随之消失）。

webcam 源设计要点
- running_mode=VIDEO + detect_for_video（同步），单线程渲染循环里直接调用。
  延迟探针已证实在 CPU 上约 10ms/帧、30FPS 可达。
- mediapipe 1.0 API：必须用 mp.Image 包帧；时间戳用单调递增的帧计数（不能用
  time.monotonic()*1000，高速下会撞到相同毫秒值报错）。
- 输出 52 个 ARKit blendshape（表情用）+ 478 个特征点（头部姿态/眼球方向用）。
  这是设计里定的「混合输入」：表情走 blendshape，姿态走特征点几何。
"""
import os
import socket
import sys
import time
from dataclasses import dataclass, field

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)

# 默认 landmarker 模型（延迟探针已下载到这里）
DEFAULT_TASK = os.path.join("models", "face_landmarker.task")

# ---- 手机源（iFacialMocap / MeowFace 兼容）----
PHONE_PORT = 49983          # 生态默认 UDP 端口（MeowFace 可在 app 里改，CLI/GUI 可配）
_PHONE_MAGIC = "iFacialMocap_sahuasouryya9218sauhuiayeta91555dy3719"   # 官方握手串
_EYE_MAX_DEG = 40.0         # 眼球最大转角（度），用于把眼欧拉归一到 -1..1
# 轴映射/符号是按 Live2D 语义定的一版假设（yaw/pitch/roll、眼球正方向），
# 真机验收时若方向不对，只改这里两个元组，别动解析逻辑。
_ROT_SIGN = (1.0, 1.0, 1.0)   # (yaw, pitch, roll) 符号
_EYE_SIGN = (1.0, 1.0)        # (眼球X, 眼球Y) 符号


@dataclass
class Frame:
    """一帧面捕结果。bs: blendshape 名->权重[0,1]; lms: [(x,y,z), ...] 归一化坐标
    (仅 webcam 源); img: BGR 画面（探针叠加用，仅 webcam 源）;
    rot: (yaw,pitch,roll) 度（仅手机源）; eye: (lx,ly,rx,ry) ∈-1..1（仅手机源）。"""
    bs: dict = field(default_factory=dict)
    lms: list = field(default_factory=list)
    img: object = None
    rot: tuple | None = None
    eye: tuple | None = None

    def bs_get(self, name: str) -> float:
        return self.bs.get(name, 0.0)


def open_source(source, phone_port: int = PHONE_PORT):
    """捕捉源工厂：source 为 int = 摄像头序号；"phone" = 手机 UDP。
    GUI / main.py / calibrate.py 共用，保证三个入口行为一致。"""
    if source == "phone":
        return PhoneCapture(port=phone_port)
    return Capture(source=int(source))


# ---- 手机 UDP 协议解析（纯函数，probes/phone_smoke.py 直接测试）----

def _phone_name_to_mp(name: str) -> str:
    """iFacialMocap 的 _L/_R 后缀 → MediaPipe 的 Left/Right（基础名两生态一致）。"""
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
    未知节跳过。eyeWide 手机端有通道（webcam 检测器没有的问题在手机源不存在）。
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
        eye = (_clamp(sx * l_y / _EYE_MAX_DEG), _clamp(-sy * l_x / _EYE_MAX_DEG),
               _clamp(sx * r_y / _EYE_MAX_DEG), _clamp(-sy * r_x / _EYE_MAX_DEG))
    else:
        eye = None
    if not bs and rot is None and eye is None:
        return None
    return {"bs": bs, "rot": rot, "eye": eye}


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


class PhoneCapture:
    """手机面捕源：绑定 UDP 端口收 iFacialMocap/MeowFace 兼容流。

    用法：手机与 PC 同一局域网 → 手机 app 填本机 IP、端口 49983 开始发送
    （首次可能弹 Windows 防火墙允许框，放行 UDP）。本类只收不渲染：
    read() 吐最新解析帧；断流超过 stale_after 秒 → 空 Frame（走 face_found=False）。
    无数据时每 2s 广播一次官方握手串（iFacialMocap 需要握手触发；MeowFace 直发也不冲突）。
    """

    label = "phone-udp"

    def __init__(self, port: int = PHONE_PORT, stale_after: float = 1.0):
        self._port = port
        self._stale_after = stale_after
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(("", port))
        except OSError as e:
            self._sock.close()
            raise RuntimeError(
                f"UDP 端口 {port} 绑定失败（被占用？防火墙？换 --phone-port）: {e}") from e
        self._sock.setblocking(False)
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        self._latest = None
        self._last_recv = 0.0
        self._next_handshake = 0.0

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
            return Frame()
        p = self._latest
        return Frame(bs=p["bs"], rot=p["rot"], eye=p["eye"])

    def is_stale(self) -> bool:
        """是否未连接/断流（GUI 状态提示用）。"""
        return self._latest is None or (time.time() - self._last_recv) > self._stale_after

    def release(self):
        try:
            self._sock.close()
        except OSError:
            pass


class Capture:
    def __init__(self, source=0, task_path: str = DEFAULT_TASK):
        if not os.path.exists(task_path):
            raise FileNotFoundError(
                f"找不到 landmarker 模型 {task_path}；先运行 probes/blendshape_latency.py 下载。"
            )
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=task_path),
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=False,
            # face_landmarker.task 默认输出 478 点（含虹膜 468-477），无需 refine
        )
        self._lm = FaceLandmarker.create_from_options(options)
        # Windows 上用 DirectShow 后端：MSMF 的 release() 在部分摄像头驱动上会死锁
        if sys.platform == "win32":
            self._cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
        else:
            self._cap = cv2.VideoCapture(source)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap.set(cv2.CAP_PROP_FPS, 30)
        if not self._cap.isOpened():
            raise RuntimeError(f"打不开摄像头 source={source}")
        self._frame_idx = 0

    label = "webcam"

    def read(self) -> Frame:
        """读一帧 → 面捕 → 解析。无脸时返回空 Frame。"""
        ok, frame = self._cap.read()
        if not ok:
            return Frame()
        frame = cv2.flip(frame, 1)  # 镜像，符合「像照镜子」的直觉
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # 单调递增时间戳（毫秒）——帧计数法，避免高速下时间戳重复
        ts = self._frame_idx * 33
        self._frame_idx += 1
        res = self._lm.detect_for_video(mp_img, ts)

        f = Frame()
        if res.face_landmarks:
            lms = res.face_landmarks[0]
            f.lms = [(p.x, p.y, p.z) for p in lms]
        if res.face_blendshapes:
            f.bs = {c.category_name: float(c.score)
                    for c in res.face_blendshapes[0]}
        f.img = frame
        return f

    def release(self):
        """尽力释放资源。Windows 上 cv2 / mediapipe 的释放偶发卡死，
        各自放守护线程 + 2 秒超时兜底；放不掉就放弃，进程退出时 OS 回收句柄。"""
        import threading

        def _guarded(fn, timeout):
            done = threading.Event()

            def _run():
                try:
                    fn()
                except Exception:
                    pass
                finally:
                    done.set()

            threading.Thread(target=_run, daemon=True).start()
            return done.wait(timeout=timeout)

        _guarded(self._cap.release, 2.0)
        _guarded(self._lm.close, 2.0)


def list_sources(max_check=4):
    """快速探测可用摄像头序号列表（DSHOW isOpened 法）。"""
    sources = []
    for i in range(max_check):
        if sys.platform == "win32":
            c = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        else:
            c = cv2.VideoCapture(i)
        if c.isOpened():
            sources.append(i)
        c.release()
    return sources or [0]
