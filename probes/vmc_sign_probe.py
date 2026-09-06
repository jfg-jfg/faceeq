r"""VMC 输入验收探针（冲刺①·PC 摄像头替代路径）。

监听 VMC 协议（/VMC/ext/blend/val），实时打印关键 AU 与情绪估计——用
VSeeFace/Warudo 等 PC 追踪软件做「好 RGB 能否读到 sad/disgust」的 C 段实测。
与 probes/phone_sign_probe.py 的指标一致，记录方式相同。

用法：
    PYTHONUTF8=1 .venv\Scripts\python.exe -u probes\vmc_sign_probe.py [--port 39539]

发送端配置（二选一，地址都填 127.0.0.1、端口 39539）：
  - Warudo：左侧设置 → VMC → 开启发送（BlendShape）；
  - VSeeFace：Settings → VMC → Enable + 勾 blendshape 发送。
    注意 VSeeFace 完整 52 形状需要 Perfect Sync 模型，无模型时值可能稀疏。
Ctrl+C 退出。
"""
import argparse
import math
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pythonosc import dispatcher, osc_server

from faceeq import emotions

HEADER = """━━━ VMC 输入验收探针 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
发送端（Warudo / VSeeFace）开启 VMC 发送，地址 127.0.0.1 端口 39539。
逐个做动作，把 +/- 与峰值抄进 docs/acceptance-sprint1.md 的 C 段表：
  撇嘴(sad) / 皱眉+内眉抬(sad) / 皱鼻抬上唇(disgust) / 微笑(对照)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

bs_lock = threading.Lock()
bs: dict = {}
rot = (0.0, 0.0, 0.0)   # (yaw, pitch, roll) 度,由 /VMC/ext/face/pos 四元数解码
last_apply = 0.0


def on_blend_val(_addr, name: str, weight: float):
    with bs_lock:
        bs[str(name)] = float(weight)


def on_face_pos(_addr, *vals):
    """/VMC/ext/face/pos <px,py,pz> <qx,qy,qz,qw> → 欧拉角(度)。
    YXZ 提取(Unity 系惯例),符号仅供验收参考。"""
    global rot
    try:
        qx, qy, qz, qw = (float(v) for v in vals[3:7])
    except (ValueError, IndexError):
        return
    yaw = math.degrees(math.atan2(2 * (qw * qy + qx * qz),
                                  1 - 2 * (qy * qy + qz * qz)))
    t = max(-1.0, min(1.0, 2 * (qw * qx - qy * qz)))
    pitch = math.degrees(math.asin(t))
    roll = math.degrees(math.atan2(2 * (qw * qz + qx * qy),
                                   1 - 2 * (qx * qx + qy * qy)))
    with bs_lock:
        rot = (yaw, pitch, roll)


def on_apply(_addr):
    global last_apply
    last_apply = time.time()


def g(d, *names):
    vals = [d.get(n, 0.0) for n in names]
    return sum(vals) / len(vals) if vals else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=39539)
    ap.add_argument("--interval", type=float, default=0.3)
    args = ap.parse_args()

    print(HEADER)
    print(f"监听 UDP {args.port}，等 VMC 数据…\n")
    disp = dispatcher.Dispatcher()
    disp.map("/VMC/ext/blend/val", on_blend_val)
    disp.map("/VMC/ext/blend/apply", on_apply)
    disp.map("/VMC/ext/face/pos", on_face_pos)
    server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", args.port), disp)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        while True:
            with bs_lock:
                snap = dict(bs)
                idle = time.time() - max(last_apply, 1e-9)
            if not snap or idle > 5:
                print(f"…等 VMC 数据（{'已连但 ' + format(idle, '.0f') + 's 无 apply' if snap else '未收到'}）", end="\r")
            else:
                emo = emotions.signals(snap)
                yaw, pitch, roll = rot
                line = (f"yaw{yaw:+7.1f} pitch{pitch:+7.1f} roll{roll:+7.1f} | "
                        f"browIn{g(snap, 'browInnerUp'):.2f} browDn{g(snap, 'browDownLeft', 'browDownRight'):.2f} "
                        f"frown{g(snap, 'mouthFrownLeft', 'mouthFrownRight'):.2f} "
                        f"sneer{g(snap, 'noseSneerLeft', 'noseSneerRight'):.2f} "
                        f"jaw{g(snap, 'jawOpen'):.2f} smile{g(snap, 'mouthSmileLeft', 'mouthSmileRight'):.2f} | "
                        f"happy{emo.get('happy', 0):.2f} angry{emo.get('angry', 0):.2f} "
                        f"sad{emo.get('sad', 0):.2f} surp{emo.get('surprised', 0):.2f} "
                        f"disg{emo.get('disgust', 0):.2f}")
                print(line)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n退出。")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
