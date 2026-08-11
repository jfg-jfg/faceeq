"""
Phase 0 延迟探针 —— 测量 MediaPipe FaceLandmarker（52 blendshape）在本机的
推理延迟与帧率。

这是整个项目的「存亡线」：如果在普通主播电脑（还要跑 OBS/游戏/推流编码）上
端到端延迟太高，「实时表情放大」这条路线就活不下去。先测，再写产品代码。

用法（在项目根目录）:
    .venv\\Scripts\\python.exe probes\\blendshape_latency.py
按 ESC 或 q 退出，或自动跑满 15 秒。
"""

import os
import sys
import time
import statistics
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# ---- 配置 ----
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "face_landmarker.task")
CAMERA_INDEX = 0       # 默认摄像头；多摄像头时改 1/2
DURATION_SEC = 15      # 自动结束秒数
WARMUP_FRAMES = 10     # 前若干帧不计入统计（模型/相机预热）


def ensure_model() -> str:
    """首次运行时下载 face_landmarker.task 模型。"""
    if os.path.exists(MODEL_PATH):
        return MODEL_PATH
    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"首次运行，下载模型到 {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("下载完成。")
    return MODEL_PATH


def make_landmarker(model_path: str) -> vision.FaceLandmarker:
    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=False,
    )
    return vision.FaceLandmarker.create_from_options(options)


def percentile(data: list[float], pct: float) -> float:
    if not data:
        return float("nan")
    s = sorted(data)
    k = (len(s) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def main() -> None:
    model_path = ensure_model()
    landmarker = make_landmarker(model_path)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"错误：打不开摄像头 (index={CAMERA_INDEX})。检查是否被其他程序占用。",
              file=sys.stderr)
        sys.exit(1)

    print(f"摄像头已打开。开始测量 {DURATION_SEC} 秒（或按 ESC/q 提前退出）...")
    print("对着摄像头做表情（笑 / 挑眉 / 惊讶），确认检测正常。\n")

    timings_ms: list[float] = []   # 每帧推理耗时（只测 detect_for_video 本身）
    wall_start = time.perf_counter()
    frame_index = 0
    last_top_print = wall_start

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("读帧失败。", file=sys.stderr)
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            ts_ms = frame_index * 33  # VIDEO 模式要求时间戳单调递增，用帧计数即可

            # —— 计时核心：只测 FaceLandmarker 推理本身 ——
            t0 = time.perf_counter()
            result = landmarker.detect_for_video(mp_image, ts_ms)
            t1 = time.perf_counter()
            infer_ms = (t1 - t0) * 1000.0

            frame_index += 1
            if frame_index > WARMUP_FRAMES:
                timings_ms.append(infer_ms)

            # 画面上叠加实时耗时，方便肉眼判断
            cv2.putText(frame, f"infer: {infer_ms:.1f} ms",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, f"frames: {frame_index}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow("blendshape latency probe (ESC to quit)", frame)

            # 每 ~2 秒打印当前最强的几个 blendshape，确认检测正常
            now = time.perf_counter()
            if now - last_top_print > 2.0 and result.face_blendshapes:
                bs = result.face_blendshapes[0]          # list[Category]
                top = sorted(bs, key=lambda c: c.score, reverse=True)[:6]
                names = ", ".join(f"{c.category_name}={c.score:.2f}" for c in top)
                print(f"  当前最强: {names}")
                last_top_print = now

            if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                break
            if now - wall_start > DURATION_SEC:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()

    # ---- 汇报 ----
    wall = time.perf_counter() - wall_start
    print("\n========== 测量结果 ==========")
    if not timings_ms:
        print("没有有效样本（摄像头没读到脸，或时长太短）。")
        return

    median = statistics.median(timings_ms)
    print(f"样本数（去掉 {WARMUP_FRAMES} 帧预热）: {len(timings_ms)}")
    print(f"推理耗时  mean={statistics.mean(timings_ms):.2f} ms  "
          f"median={median:.2f} ms  "
          f"p95={percentile(timings_ms, 95):.2f} ms  "
          f"max={max(timings_ms):.2f} ms")
    print(f"纯推理理论上限 ≈ {1000.0 / median:.1f} FPS")
    print(f"端到端（含取帧+推理+显示）≈ {frame_index / wall:.1f} FPS")
    print("==============================")

    print("\n判决：")
    if median < 20:
        print("✅ 很轻 —— 纯推理留得出余量给情绪/曲线层和渲染。")
    elif median < 40:
        print("🟡 还行 —— 能跑实时，但 OBS + 游戏一起开时要复测。")
    else:
        print("🔴 偏重 —— OBS + 游戏加压后大概率掉帧，考虑 GPU 加速或降分辨率。")

    print("\n下一步：在【同时开着 OBS + 游戏】的环境下再跑一次，对比数字。")


if __name__ == "__main__":
    main()
