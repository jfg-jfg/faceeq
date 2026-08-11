"""信号自校准探针：摄像头 → emotions.signals_with_raw → 把 5 个情绪强度 +
原始 blendshape 输入实时叠在画面上。

用途：对着摄像头做每个表情，看哪个情绪在动、强度多少、有没有误触发/串味，
照着自己的脸校准 emotions.signals() 的权重（处理 grill Q1+Q3：现在的魔法权重
是在 Haru 上拍脑袋的，从没拿真人脸校准过）。无需 Live2D / VTS。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/signal_probe.py
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/signal_probe.py --source 0
ESC 退出。

判读：
  - 做厌恶脸，看 sad 是否被误点亮（frown 共享串味）；
  - 做惊讶，看 surprised 是否上得来（当前无 jawOpen，纯靠 eyeWide+browUp）；
  - 微笑，看 happy 与 squint(=AU6 眼笑) 的关系，调 0.4*squint 那个权重。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from faceeq import emotions
from faceeq.capture import Capture

EMOS = emotions.EMOTIONS  # ["happy","angry","sad","surprised","disgust"]
RAW_ORDER = ["smile", "frown", "squint", "browDn", "press",
             "browIn", "browUp", "eyeWide", "sneer", "jawOpen"]

# 颜色 (BGR)
C_BG = (40, 40, 40)
C_DOM = (80, 220, 80)       # 主导情绪：绿
C_OFF = (180, 160, 0)       # 非主导：蓝
C_RAW = (0, 180, 220)       # 原始输入：橙
C_TXT = (235, 235, 235)
C_DIM = (110, 110, 110)


def _bar(img, x, y, w, h, val, color, label, value):
    """画 [label |████| value]，val∈[0,1]。"""
    v = max(0.0, min(1.0, val))
    cv2.rectangle(img, (x, y), (x + w, y + h), C_BG, -1)
    cv2.rectangle(img, (x, y), (x + int(w * v), y + h), color, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), C_DIM, 1)
    cv2.putText(img, label, (x - 95, y + h - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, C_TXT, 1, cv2.LINE_AA)
    cv2.putText(img, value, (x + w + 6, y + h - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, C_TXT, 1, cv2.LINE_AA)


def draw_overlay(img, emo, raw, dom, fps):
    h, w = img.shape[:2]
    # 左侧半透明底板，让文字可读（脸主要在画面中右部，仍可见）
    panel = img.copy()
    cv2.rectangle(panel, (0, 0), (380, h), (0, 0, 0), -1)
    cv2.addWeighted(panel, 0.45, img, 0.55, 0, img)

    cv2.putText(img, f"signal_probe [{dom}] {fps}fps  ESC quit",
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, C_TXT, 1, cv2.LINE_AA)
    cv2.line(img, (8, 30), (372, 30), C_DIM, 1)

    # 情绪条（主导=绿）
    cv2.putText(img, "EMOTION", (8, 47), cv2.FONT_HERSHEY_SIMPLEX,
                0.4, C_DIM, 1, cv2.LINE_AA)
    for i, name in enumerate(EMOS):
        y = 55 + i * 28
        color = C_DOM if name == dom and dom != "neutral" else C_OFF
        _bar(img, 105, y, 210, 16, emo.get(name, 0.0), color,
             f"{name:9s}", f"{emo.get(name, 0.0):.2f}")

    # 原始输入条（单列 9 行）
    cv2.putText(img, "RAW INPUT", (8, 222), cv2.FONT_HERSHEY_SIMPLEX,
                0.4, C_DIM, 1, cv2.LINE_AA)
    for i, name in enumerate(RAW_ORDER):
        y = 230 + i * 22
        _bar(img, 105, y, 180, 14, raw.get(name, 0.0), C_RAW,
             f"{name:7s}", f"{raw.get(name, 0.0):.2f}")


def main():
    ap = argparse.ArgumentParser(description="FaceEQ 信号自校准探针")
    ap.add_argument("--source", type=int, default=0, help="摄像头序号")
    args = ap.parse_args()

    cap = Capture(source=args.source)
    print("对着摄像头做表情（笑/怒/惊讶/悲伤/厌恶）。看左侧情绪条 + 原始输入。ESC 退出。")

    fps = 0
    frames = 0
    timer = time.time()
    win = "FaceEQ signal_probe"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            f = cap.read()
            img = f.img
            if img is None:
                continue
            if f.bs:
                emo, raw = emotions.signals_with_raw(f.bs)
                dom = emotions.dominant(emo)
                draw_overlay(img, emo, raw, dom, fps)
            else:
                cv2.putText(img, "NO FACE", (8, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 220), 2)

            cv2.imshow(win, img)
            if (cv2.waitKey(1) & 0xFF) == 27:   # ESC
                break

            frames += 1
            if time.time() - timer >= 1.0:
                fps = frames
                frames = 0
                timer = time.time()
    finally:
        cap.release()
        cv2.destroyAllWindows()
        # Windows 上 cv2/mediapipe 释放偶发卡死（见 capture.release 注释），
        # os._exit 绕过残留清理，确保进程立即结束（与 main.py 同样的处理）。
        os._exit(0)


if __name__ == "__main__":
    main()
