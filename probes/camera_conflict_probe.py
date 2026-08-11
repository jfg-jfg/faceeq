"""摄像头冲突探针：当 VTube Studio 占着摄像头时，FaceEQ（走 DSHOW 后端）还能不能
打开同一个摄像头。这是开源给别的用户时的已知风险点——能否共享取决于驱动/API。

前置：**先启动 VTube Studio 并开启摄像头跟踪**（让它占着摄像头），再跑本探针。
用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/camera_conflict_probe.py        # 默认 source 0
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/camera_conflict_probe.py 1      # 指定 source
判读：
    打开成功 + 读到帧 → 你这套不冲突（VTS 与 FaceEQ 可共享同一摄像头）。
    打不开 / 读不到帧 → 冲突，需虚拟摄像头（OBS Virtual Camera）或把 VTS 摄像头设 none。
"""
import os
import sys
import time

import cv2

src = int(sys.argv[1]) if len(sys.argv) > 1 else 0
print(f"[probe] VTS 应已在跑并占着摄像头。尝试以 DSHOW 打开 source={src} ...")
try:
    cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("[probe] FAIL：打不开（很可能被 VTS 独占）。"
              "→ 解法：OBS 虚拟摄像头，或在 VTS 把摄像头设成 none 让 FaceEQ 独占。")
        raise SystemExit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    for _ in range(5):            # 预热（前几帧常慢）
        cap.grab()
    n = 0
    t0 = time.time()
    for _ in range(30):
        ret, _ = cap.read()      # 用 read（含解码），反映真实可得帧率；grab 只排空缓冲会假高
        if ret:
            n += 1
    dt = time.time() - t0
    cap.release()
    if n == 0:
        print("[probe] FAIL：打开但读不到帧（被抢占？）。同上解法。")
        raise SystemExit(1)
    fps = n / dt if dt > 0 else 0.0
    verdict = ("不冲突（可用）" if fps >= 20
               else "慢但勉强" if fps >= 10
               else "冲突/太慢（需虚拟摄像头 或 VTS 摄像头设 none）")
    print(f"[probe] 读到 {n}/30 帧，{dt:.1f}s → {fps:.1f} fps。→ {verdict}")
except SystemExit:
    raise
except Exception as e:
    print(f"[probe] 异常：{e}")
finally:
    # 不涉及 mediapipe，普通 cv2 release 一般不卡；os._exit 保险。
    os._exit(0)
