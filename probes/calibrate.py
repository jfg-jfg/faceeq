"""引导式 AU 校正向导：每个 AU 配【中英文文字提示 + 摄像头实时值】，照提示做表情、
保持、按空格采样 ~1 秒 → 自动算每 AU 增益 → 写 per-user profile JSON。

FaceEQ 上手的核心（"简简单单上手"）：把 per-AU 欠读补偿从硬编码 → 你这张脸的实测值。

UI 演进：①早期 Live2D Haru 示范（精度不够：browIn/browUp 同参、press/sneer 无参、形变粗）
→ ②cv2 自绘方向箭头（仍不够直观）→ ③现用 **PIL 渲染的中英文文字提示**（最明确）。单 cv2 窗：
左摄像头 + 右文字面板（PIL+中文字体，cv2 本身渲染不了中文）。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/calibrate.py
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/calibrate.py --out profiles/me.json
    PYTHONUTF8=1 .venv/Scripts/python.exe probes/calibrate.py --source phone   # 手机面捕
按键：保持表情后 SPACE 采样当前 AU；ESC 跳过当前（该 AU 用默认增益 1.0，不判死）；q 退出。
产出：写 --out（默认 profiles/calibration.json）+ 同目录 calibration_result.txt，打印用法命令。
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from faceeq import emotions, profile
from faceeq.capture import PHONE_PORT, open_source

# (raw 键, 中文标题, 中文动作, 英文动作). raw 键对应 signals_with_raw 的 raw / profile.RAW_KEYS。
POSES = [
    ("neutral", "中性 · NEUTRAL",   "放松，无表情",          "relax, no expression"),
    ("smile",   "微笑 · AU12",      "嘴角上扬（大笑）",      "mouth corners UP (big smile)"),
    ("frown",   "嘴角下垂 · AU15",  "嘴角往下拉",            "pull corners DOWN (sad mouth)"),
    ("squint",  "眯眼 · AU6",       "眼角用力挤",            "squeeze eyes at corners"),
    ("browDn",  "皱眉 · AU4",       "眉头往下挤",            "brows DOWN & together (angry)"),
    ("press",   "抿唇 · AU24",      "嘴唇用力抿紧",          "press lips tight together"),
    ("browIn",  "内眉抬 · AU1",     "抬内眉（八字眉）",      "raise INNER brows (puppy brow)"),
    ("browUp",  "挑眉 · AU2",       "抬外眉",                "raise OUTER brows"),
    ("eyeWide", "瞪眼 · AU5",       "眼睛瞪大",              "open eyes WIDE (surprise)"),
    ("sneer",   "皱鼻 · AU9",       "皱鼻 / 撇上唇",         "wrinkle nose / sneer (disgust)"),
    ("jawOpen", "张嘴 · AU26",      "张大嘴",                "open mouth WIDE (surprise)"),
]

CAPTURE_FRAMES = 30
TARGET_DELTA = 0.5
DEAD_DELTA = 0.05
GREEN, YELLOW, WHITE, GRAY = (80, 220, 80), (0, 220, 220), (235, 235, 235), (150, 150, 150)
PANEL_W, PANEL_H = 380, 480

# 中文字体（跨平台候选；首个存在的用）。⚠️ 无中文字体的系统会退化为 PIL 默认字体（中文显示不出）。
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
_FONT_PATH = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)


def _font(size):
    from PIL import ImageFont
    if _FONT_PATH:
        try:
            return ImageFont.truetype(_FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _prompt_panel(zh_title, zh_desc, en_desc):
    """PIL 渲染中英文提示面板 → numpy(BGR) 供 cv2 显示。"""
    from PIL import Image, ImageDraw
    pil = Image.new("RGB", (PANEL_W, PANEL_H), (0, 0, 0))
    d = ImageDraw.Draw(pil)
    d.text((18, 28), zh_title, font=_font(36), fill=GREEN)
    d.text((18, 110), "做这个表情：", font=_font(24), fill=GRAY)
    d.text((18, 150), zh_desc, font=_font(40), fill=WHITE)
    d.text((18, 235), en_desc, font=_font(22), fill=YELLOW)
    d.text((18, PANEL_H - 110), "保持住表情", font=_font(26), fill=(220, 220, 220))
    d.text((18, PANEL_H - 60), "→ 按 SPACE 采样", font=_font(24), fill=GRAY)
    return np.array(pil)[:, :, ::-1].copy()   # RGB→BGR


def build_profile_dict(records, target_delta, source, demographic, skipped=()):
    """从 records（每 pose 的平均 raw 字典）构建 profile dict（schema v1）。无 neutral → None。
    skipped = ESC 跳过的 pose 键。「没测」≠「测不到」：跳过的 AU 不判死，写默认增益 1.0；
    只有实测 delta≤DEAD_DELTA 才判死（null）。"""
    if "neutral" not in records:
        return None
    base = records["neutral"]
    captures, au_gains = {}, {}
    for k in profile.RAW_KEYS:
        neu = base.get(k, 0.0)
        if k in skipped:
            captures[k] = {"neutral": round(neu, 4), "max": None,
                           "delta": None, "gain": 1.0}
            au_gains[k] = 1.0
            continue
        mx = records.get(k, {}).get(k, neu)
        delta = mx - neu
        gain = (target_delta / delta) if delta > DEAD_DELTA else None
        captures[k] = {"neutral": round(neu, 4), "max": round(mx, 4),
                       "delta": round(delta, 4),
                       "gain": (round(gain, 3) if gain is not None else None)}
        au_gains[k] = (round(gain, 3) if gain is not None else None)
    return {
        "schema_version": profile.SCHEMA_VERSION,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "camera": {"source": source},
        "demographic": demographic,
        "target_delta": target_delta,
        "neutral": {k: round(base.get(k, 0.0), 4) for k in profile.RAW_KEYS},
        "captures": captures,
        "au_gains": au_gains,
        "global_gain": None, "smooth": None, "emotion_gains": None,
    }


def build_report(records, target_delta, skipped=()):
    if "neutral" not in records:
        return "no NEUTRAL baseline recorded - rerun and capture NEUTRAL first."
    base = records["neutral"]
    lines = ["=== FaceEQ AU calibration ===",
             "baseline(neutral): " + ", ".join(f"{k}={base[k]:.3f}" for k in profile.RAW_KEYS), "",
             f"{'AU':10s} {'neutral':>8s} {'max':>8s} {'delta':>8s} {'gain':>8s}"]
    dead = []
    for k in profile.RAW_KEYS:
        neu = base.get(k, 0.0)
        if k in skipped:
            lines.append(f"{k:10s} {neu:8.3f} {'-':>8s} {'-':>8s}    1.0 (skipped)")
            continue
        mx = records.get(k, {}).get(k, neu)
        delta = mx - neu
        if delta > DEAD_DELTA:
            lines.append(f"{k:10s} {neu:8.3f} {mx:8.3f} {delta:8.3f} {target_delta/delta:8.3f}")
        else:
            lines.append(f"{k:10s} {neu:8.3f} {mx:8.3f} {delta:8.3f}     dead")
            dead.append(k)
    if skipped:
        lines.append("")
        lines.append("skipped AUs (not measured; default gain 1.0, NOT dead): "
                     + ", ".join(k for k in profile.RAW_KEYS if k in skipped))
    if dead:
        lines.append("")
        lines.append("dead AUs (detector can't read on your face): " + ", ".join(dead))
    high_neutral = [k for k in profile.RAW_KEYS if base.get(k, 0.0) > 0.15]
    neg = [k for k in profile.RAW_KEYS
           if (records.get(k, {}).get(k, base.get(k, 0.0)) - base.get(k, 0.0)) < 0]
    if high_neutral:
        lines.append("")
        lines.append("⚠ neutral 偏高（neutral 时没放松?）: " + ", ".join(high_neutral)
                     + " — 放松脸重测 neutral 可提增益可靠性")
    if neg:
        lines.append("⚠ 做表情时读数反而更低（做反了? 或 neutral 脏）: " + ", ".join(neg)
                     + " — 重测该 pose / neutral")
    return "\n".join(lines)


def show_report(win, report, hint):
    lines = report.split("\n")
    img = np.zeros((max(480, 30 * len(lines) + 50), 860, 3), dtype="uint8")
    for i, ln in enumerate(lines):
        cv2.putText(img, ln[:100], (12, 30 + i * 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, GREEN if i < 3 else WHITE, 1, cv2.LINE_AA)
    cv2.putText(img, hint, (12, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, GRAY, 1, cv2.LINE_AA)
    cv2.imshow(win, img)
    cv2.waitKey(0)


def _phone_canvas(f):
    """手机源无摄像头画面 → 黑底状态画布，保持校准窗口布局可用。"""
    img = np.zeros((240, 320, 3), dtype="uint8")
    cv2.putText(img, "PHONE SOURCE (UDP)", (14, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, GREEN, 2, cv2.LINE_AA)
    if f.bs:
        cv2.putText(img, "receiving ...", (14, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 1, cv2.LINE_AA)
    else:
        cv2.putText(img, "waiting for data ...", (14, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 1, cv2.LINE_AA)
        cv2.putText(img, "check app IP / firewall", (14, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, GRAY, 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser(description="FaceEQ 引导式 AU 校正向导")
    ap.add_argument("--source", type=str, default="0",
                    help="摄像头序号；或 \"phone\" 用手机面捕（iFacialMocap/MeowFace）")
    ap.add_argument("--phone-port", type=int, default=PHONE_PORT,
                    help="手机 UDP 端口（仅 --source phone 时生效）")
    ap.add_argument("--out", default=os.path.join("profiles", "calibration.json"),
                    help="profile 输出路径")
    args = ap.parse_args()

    cap = open_source(args.source, args.phone_port)
    cam_win = "FaceEQ calibrate (SPACE=capture / ESC=skip / q=quit)"
    cv2.namedWindow(cam_win, cv2.WINDOW_AUTOSIZE)
    if args.source == "phone":
        print("手机源：在手机 app（iFacialMocap/MeowFace）里填本机 IP 与端口后开始发送；"
              "无摄像头画面预览，黑底画布显示收流状态。")
    print("看右侧中英文提示 + 左侧 live 值，保持表情后按 SPACE 采样。")

    records = {}
    skipped = set()      # ESC 跳过的 pose 键（不判死，写默认增益 1.0）
    i = 0
    state = "prompt"     # prompt | capturing
    buf = []
    last_msg = ""
    panel = _prompt_panel(*POSES[0][1:])

    try:
        while i < len(POSES):
            f = cap.read()
            img = f.img
            if img is None:
                img = _phone_canvas(f)   # 手机源：无摄像头画面 → 状态画布
            key_name, zh_title, zh_desc, en_desc = POSES[i]
            raw = emotions.signals_with_raw(f.bs)[1] if f.bs else {}
            panel = _prompt_panel(zh_title, zh_desc, en_desc)

            # 顶部信息条（摄像头画面上）
            ov = img.copy()
            cv2.rectangle(ov, (0, 0), (img.shape[1], 60), (0, 0, 0), -1)
            cv2.addWeighted(ov, 0.6, img, 0.4, 0, img)
            cv2.putText(img, f"[{i+1}/{len(POSES)}] {key_name.upper()}", (10, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, GREEN, 2, cv2.LINE_AA)
            if state == "prompt":
                if last_msg:
                    cv2.putText(img, last_msg, (10, img.shape[0] - 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 1, cv2.LINE_AA)
            else:  # capturing
                if f.bs:
                    buf.append(raw)
                cv2.putText(img, f"CAPTURING {len(buf)}/{CAPTURE_FRAMES} ... hold steady",
                            (10, img.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, YELLOW, 2, cv2.LINE_AA)
                if len(buf) >= CAPTURE_FRAMES:
                    # 按键取有效帧平均：某键个别帧缺失时不以 0.0 稀释均值
                    avg = {}
                    for kk in buf[0]:
                        vals = [d[kk] for d in buf if kk in d]
                        avg[kk] = sum(vals) / len(vals) if vals else 0.0
                    records[key_name] = avg
                    last_msg = (f"recorded {key_name} = {avg.get(key_name, 0.0):.3f}"
                                if key_name != "neutral" else "baseline recorded")
                    buf, state = [], "prompt"
                    i += 1
                    continue
            if key_name != "neutral" and key_name in raw:
                cv2.putText(img, f"live {key_name} = {raw[key_name]:.3f}",
                            (img.shape[1] - 270, 34),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1, cv2.LINE_AA)

            canvas = np.hstack([img, panel])  # 左摄像头 + 右中英文提示，单窗
            cv2.imshow(cam_win, canvas)
            k = cv2.waitKey(1) & 0xFF
            if k == ord('q'):
                break
            elif k == 27:            # ESC 跳过当前（=未测，gain 默认 1.0，不判死）
                last_msg = f"skipped {key_name}"
                skipped.add(key_name)
                buf, state = [], "prompt"
                i += 1
            elif k == 32 and state == "prompt" and f.bs:   # SPACE 采样
                state = "capturing"
                buf = []

        # —— 产出 profile + 人读报告 ——
        src_val = args.source if args.source == "phone" else int(args.source)
        report = build_report(records, TARGET_DELTA, skipped)
        prof_dict = build_profile_dict(records, TARGET_DELTA, src_val, None, skipped)
        if prof_dict:
            out_dir = os.path.dirname(os.path.abspath(args.out))
            os.makedirs(out_dir, exist_ok=True)
            profile.write_profile(args.out, prof_dict)
            report_path = os.path.join(out_dir, "calibration_result.txt")
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write(report + "\n\nprofile: " + args.out + "\n")
            n = sum(1 for v in prof_dict["au_gains"].values() if v is not None)
            print(report)
            print(f"\n[calibrate] profile 写入 {args.out}（{n} 个 AU 有增益）")
            print(f"[calibrate] 报告写入 {report_path}")
            print(f"[calibrate] 用法：PYTHONUTF8=1 .venv/Scripts/python.exe main.py --profile {args.out}")
            sys.stdout.flush()
            show_report(cam_win, report, f"profile: {args.out}  (any key to close)")
        else:
            print(report)
            sys.stdout.flush()
            show_report(cam_win, report, "(no profile written; any key to close)")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        # Windows 上 cv2/mediapipe 残留线程会卡住正常退出 → 仍用 os._exit 硬退，
        # 但保留真实退出码：异常路径打印 traceback 并以非零码退出，
        # GUI(CalibrateRunner 的返回码)/CLI 才能感知校准中途崩溃。
        exc = sys.exc_info()[1]
        if exc is not None:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
            sys.stdout.flush()
            os._exit(1)
        os._exit(0)


if __name__ == "__main__":
    main()
