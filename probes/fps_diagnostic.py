"""
FPS 诊断：交互探针端到端只有 ~7.5 FPS，本脚本把瓶颈定位到具体环节。

把每帧拆成三段计时：
  - cap.read()   摄像头取帧（若 ≈133ms 说明摄像头本身只给 7.5FPS）
  - detect       MediaPipe 推理（应远小于取帧）
  - imshow/wait  显示（对比开关，判断是不是显示拖慢）
并尝试强制 FPS=30 + 640x480，看后端买不买账。

用法: .venv\\Scripts\\python.exe probes\\fps_diagnostic.py
（无窗口，约 8-10 秒自动结束。）
"""

import sys
import time
import statistics

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_PATH = "models/face_landmarker.task"
N_FRAMES = 40


def measure(cap, lm, n=N_FRAMES, show=False, ts_start=0):
    read_ms, detect_ms = [], []
    start = time.perf_counter()
    frames = 0
    ts = ts_start
    for i in range(n):
        t0 = time.perf_counter()
        ok, frame = cap.read()
        t1 = time.perf_counter()
        if not ok:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        t2 = time.perf_counter()
        lm.detect_for_video(mp_image, ts)
        ts += 33
        t3 = time.perf_counter()
        read_ms.append((t1 - t0) * 1000.0)
        detect_ms.append((t3 - t2) * 1000.0)
        frames += 1
        if show:
            cv2.imshow("d", frame)
            cv2.waitKey(1)
    if show:
        cv2.destroyAllWindows()
    wall = time.perf_counter() - start
    return frames, wall, read_ms, detect_ms, ts


def stats(xs):
    if not xs:
        return "n/a"
    return f"mean={statistics.mean(xs):6.1f}ms  median={statistics.median(xs):6.1f}ms"


def main():
    opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO, num_faces=1,
        output_face_blendshapes=True)
    lm = vision.FaceLandmarker.create_from_options(opts)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("CAMERA_FAIL: 打不开摄像头 index 0"); sys.exit(1)

    print("== 摄像头默认信息 ==")
    print("  backend :", cap.getBackendName())
    print("  FPS     :", cap.get(cv2.CAP_PROP_FPS))
    print("  分辨率  :", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
          "x", int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    print("\n== A: 无显示(无窗口)，默认设置 ==")
    f, w, rm, dm, ts = measure(cap, lm, show=False, ts_start=0)
    print(f"  {f}帧 / {w:.2f}s -> 端到端 {f/w:.1f} FPS")
    print(f"  cap.read : {stats(rm)}")
    print(f"  detect   : {stats(dm)}")

    print("\n== B: 尝试强制 FPS=30 + 640x480 ==")
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("  设置后 -> FPS:", cap.get(cv2.CAP_PROP_FPS),
          " 分辨率:", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
          "x", int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    f, w, rm, dm, ts = measure(cap, lm, show=False, ts_start=ts + 33)
    print(f"  {f}帧 / {w:.2f}s -> 端到端 {f/w:.1f} FPS")
    print(f"  cap.read : {stats(rm)}")
    print(f"  detect   : {stats(dm)}")

    cap.release(); lm.close()
    print("\n（解读：若 cap.read 的 median ≈ 130ms 且 B 没改善，说明摄像头硬件/驱动只给 7.5FPS；"
          "若 B 升到 ~30FPS，那默认设置就是元凶，正式代码里 set 一下即可。）")


if __name__ == "__main__":
    main()
