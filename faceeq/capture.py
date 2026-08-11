"""
摄像头面捕模块：MediaPipe FaceLandmarker → 每帧返回 (blendshape 字典, 特征点列表)。

设计要点
- running_mode=VIDEO + detect_for_video（同步），单线程渲染循环里直接调用。
  延迟探针已证实在 CPU 上约 10ms/帧、30FPS 可达。
- mediapipe 1.0 API：必须用 mp.Image 包帧；时间戳用单调递增的帧计数（不能用
  time.monotonic()*1000，高速下会撞到相同毫秒值报错）。
- 输出 52 个 ARKit blendshape（表情用）+ 478 个特征点（头部姿态/眼球方向用）。
  这是设计里定的「混合输入」：表情走 blendshape，姿态走特征点几何。
"""
import os
import sys
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


@dataclass
class Frame:
    """一帧面捕结果。bs: blendshape 名->权重[0,1]; lms: [(x,y,z), ...] 归一化坐标;
    img: BGR 画面（探针叠加用，main 主流程不用）。"""
    bs: dict = field(default_factory=dict)
    lms: list = field(default_factory=list)
    img: object = None

    def bs_get(self, name: str) -> float:
        return self.bs.get(name, 0.0)


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
