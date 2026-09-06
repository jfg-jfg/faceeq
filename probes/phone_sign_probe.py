"""手机/平板面捕符号验收探针（冲刺①专用）。

iFacialMocap（iPad/iPhone）或 MeowFace（安卓）→ 实时打印头部旋转/眼球/关键
blendshape/情绪估计，供验收卡记录方向符号与 TrueDepth 读数。
先启动本探针再启动 app 即可（PhoneCapture 会自动广播握手触发 iFacialMocap）。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/phone_sign_probe.py
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/phone_sign_probe.py --port 49983
Ctrl+C 退出。注意：探针占用 UDP 端口，运行期间别同时开 FaceEQ GUI。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq import emotions
from faceeq.capture import PhoneCapture

HEADER = """━━━ 符号验收探针 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
逐个做动作，把打印行里的符号 (+/-) 抄进 docs/acceptance-sprint1.md 的表：
  头：水平左转/右转 → yaw      低头/抬头 → pitch      左/右歪头 → roll
  眼：左/右/上/下看 → eyeX / eyeY（动眼睛别动头）
  表情：撇嘴(sad)/皱眉+内眉抬(sad)/皱鼻抬上唇(disgust) → 记 sad/disgust 峰值
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def g(bs, *names):
    vals = [bs.get(n, 0.0) for n in names]
    return sum(vals) / len(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=49983)
    ap.add_argument("--interval", type=float, default=0.3, help="打印间隔秒")
    args = ap.parse_args()

    print(HEADER)
    print(f"监听 UDP {args.port}，等 app 数据…（iFacialMocap 填本机 IP + 此端口）\n")
    cap = PhoneCapture(port=args.port)
    try:
        while True:
            f = cap.read()
            if not f.bs and f.rot is None:
                print("…断流/未连接（检查 app 是否在发送、防火墙）", end="\r")
                time.sleep(0.5)
                continue
            yaw, pitch, roll = f.rot if f.rot else (0.0, 0.0, 0.0)
            lx, ly, rx, ry = f.eye if f.eye else (0.0, 0.0, 0.0, 0.0)
            bs = f.bs
            emo = emotions.signals(bs) if bs else {}
            line = (f"yaw{yaw:+7.1f} pitch{pitch:+7.1f} roll{roll:+7.1f} | "
                    f"eyeX{lx:+5.2f}/{rx:+5.2f} eyeY{ly:+5.2f}/{ry:+5.2f} | "
                    f"browIn{g(bs, 'browInnerUp'):.2f} frown{g(bs, 'mouthFrownLeft', 'mouthFrownRight'):.2f} "
                    f"sneer{g(bs, 'noseSneerLeft', 'noseSneerRight'):.2f} "
                    f"jaw{g(bs, 'jawOpen'):.2f} smile{g(bs, 'mouthSmileLeft', 'mouthSmileRight'):.2f} | "
                    f"happy{emo.get('happy', 0):.2f} angry{emo.get('angry', 0):.2f} "
                    f"sad{emo.get('sad', 0):.2f} surp{emo.get('surprised', 0):.2f} "
                    f"disg{emo.get('disgust', 0):.2f}")
            print(line)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n退出。")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
