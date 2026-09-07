"""引导式 AU 校正向导：每个 AU 配【中英文文字提示 + 摄像头实时值】，照提示做表情、
保持、按空格采样 ~1 秒 → 自动算每 AU 增益 → 写 per-user profile JSON。

FaceEQ 上手的核心（"简简单单上手"）：把 per-AU 欠读补偿从硬编码 → 你这张脸的实测值。

UI：**PIL 渲染的中英文文字提示**（左状态区 + 右提示面板，tkinter 窗口）。
v0.2.0 起不再依赖 cv2（省 138MB 打包体积）。

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
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq import emotions, profile
from faceeq.inputs.phone import PHONE_PORT
from faceeq.inputs import create_input

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


class _Wizard:
    """tkinter 校准向导：左状态区（进度/live 值/消息）+ 右 PIL 中英文提示面板。

    事件驱动（root.after 30ms tick）：prompt 态显示 live 值，capturing 态按 tick
    采 CAPTURE_FRAMES 帧取均值。按键：SPACE 采样 / ESC 跳过 / q 退出。
    """

    def __init__(self, root, cap, poses, panel_w=380, panel_h=480):
        from PIL import Image, ImageTk
        self._Image, self._ImageTk = Image, ImageTk
        self.root = root
        self.cap = cap
        self.poses = poses
        self.panel_w, self.panel_h = panel_w, panel_h
        self.records, self.skipped = {}, set()
        self.i, self.state, self.buf = 0, "prompt", []
        self.last_msg = ""
        self.rc = 0
        self.out_path = os.path.join("profiles", "calibration.json")
        self._frame_bs = {}

        root.title("FaceEQ calibrate (SPACE=采样 / ESC=跳过 / q=退出)")
        left = tk.Frame(root, width=340, height=panel_h, bg="#101010")
        left.pack(side="left", fill="y")
        self._v_progress = self._lbl(left, 22, "#50dc50", 16)
        self._v_recv = self._lbl(left, 64, "#50dc50", 12)
        self._v_live = self._lbl(left, 96, "#ebebeb", 13)
        self._v_msg = self._lbl(left, 180, "#dcdcdc", 12)
        self._canvas = tk.Label(root, bg="#000000")
        self._canvas.pack(side="right", fill="both", expand=True)

        for seq, fn in (("<space>", self._capture), ("<Escape>", self._skip),
                        ("<KeyPress-q>", self._quit)):
            root.bind(seq, fn)
        root.focus_force()
        self._set_panel(0)
        root.after(30, self._tick)

    def _lbl(self, parent, y, color, size):
        return tk.Label(parent, bg="#101010", fg=color, font=("Microsoft YaHei", size),
                        anchor="w", justify="left", wraplength=320)

    def _place(self, w, y):
        w.place(x=14, y=y, width=310)

    # —— 右侧 PIL 提示面板 ——
    def _set_panel(self, idx):
        from PIL import Image, ImageDraw
        zh_title, zh_desc, en_desc = self.poses[idx][1:]
        img = self._Image.new("RGB", (self.panel_w, self.panel_h), (0, 0, 0))
        d = ImageDraw.Draw(img)
        W, H = self.panel_w, self.panel_h
        d.text((18, 28), zh_title, font=_font(36), fill=(80, 220, 80))
        d.text((18, 110), "做这个表情：", font=_font(24), fill=(150, 150, 150))
        d.text((18, 150), zh_desc, font=_font(40), fill=(235, 235, 235))
        d.text((18, 235), en_desc, font=_font(22), fill=(0, 220, 220))
        d.text((18, H - 110), "保持住表情", font=_font(26), fill=(220, 220, 220))
        d.text((18, H - 60), "→ 按 SPACE 采样", font=_font(24), fill=(150, 150, 150))
        self._photo = self._ImageTk.PhotoImage(img)
        self._canvas.configure(image=self._photo)

    def _set_panel_text(self, lines, hint):
        from PIL import Image, ImageDraw
        H = max(self.panel_h, 26 * len(lines) + 60)
        img = self._Image.new("RGB", (760, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        for i, ln in enumerate(lines):
            d.text((12, 24 + i * 26), ln[:96], font=_font(15),
                   fill=(80, 220, 80) if i < 3 else (235, 235, 235))
        d.text((12, H - 40), hint, font=_font(14), fill=(150, 150, 150))
        self._photo = self._ImageTk.PhotoImage(img)
        self._canvas.configure(image=self._photo)

    def _capture(self, _e=None):
        if self.state == "prompt" and self._frame_bs:
            self.state = "capturing"
            self.buf = []

    def _skip(self, _e=None):
        if self.i < len(self.poses):
            self.last_msg = "skipped " + self.poses[self.i][0]
            self.skipped.add(self.poses[self.i][0])
            self.buf, self.state = [], "prompt"
            self.i += 1
            if self.i < len(self.poses):
                self._set_panel(self.i)

    def _quit(self, _e=None):
        self.root.destroy()

    def _tick(self):
        try:
            f = self.cap.read()
            self._frame_bs = f.bs
            key_name = self.poses[self.i][0] if self.i < len(self.poses) else None
            raw = emotions.signals_with_raw(f.bs)[1] if f.bs else {}
            self._v_progress.configure(text="[{}/{}] {}".format(
                self.i + 1, len(self.poses), key_name.upper() if key_name else "DONE"))
            self._v_recv.configure(text="receiving ..." if f.bs
                                   else "waiting for data ... (check app IP / firewall)")
            if key_name and key_name != "neutral":
                self._v_live.configure(text="live {} = {:.3f}".format(key_name, raw.get(key_name, 0.0)))
            else:
                self._v_live.configure(text="")
            if self.state == "capturing":
                if f.bs:
                    self.buf.append(raw)
                self._v_msg.configure(text="CAPTURING {}/{} ... hold steady".format(
                    len(self.buf), CAPTURE_FRAMES))
                if len(self.buf) >= CAPTURE_FRAMES:
                    avg = {}
                    for kk in self.buf[0]:
                        vals = [d[kk] for d in self.buf if kk in d]
                        avg[kk] = sum(vals) / len(vals) if vals else 0.0
                    self.records[key_name] = avg
                    self.last_msg = ("baseline recorded" if key_name == "neutral"
                                     else "recorded {} = {:.3f}".format(key_name, avg.get(key_name, 0.0)))
                    self.buf, self.state = [], "prompt"
                    self.i += 1
                    if self.i < len(self.poses):
                        self._set_panel(self.i)
            else:
                self._v_msg.configure(text=self.last_msg)
            if self.i < len(self.poses):
                self.root.after(30, self._tick)
            else:
                self._finish()
        except Exception:
            self.rc = 1
            import traceback
            traceback.print_exc()
            self.root.destroy()

    def _finish(self):
        report = build_report(self.records, TARGET_DELTA, self.skipped)
        prof_dict = build_profile_dict(self.records, TARGET_DELTA,
                                       self.cap.label, None, self.skipped)
        lines = report.split("\n")
        if prof_dict:
            out_dir = os.path.dirname(os.path.abspath(self.out_path))
            os.makedirs(out_dir, exist_ok=True)
            profile.write_profile(self.out_path, prof_dict)
            report_path = os.path.join(out_dir, "calibration_result.txt")
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write(report + "\n\nprofile: " + self.out_path + "\n")
            print(report)
            print("\n[calibrate] profile 写入 " + self.out_path)
            print("[calibrate] 报告写入 " + report_path)
            hint = "profile: " + self.out_path + "  (按任意键/q 关闭)"
        else:
            print(report)
            hint = "(no profile written; 按任意键关闭)"
        self._set_panel_text(lines, hint)
        self.root.bind("<Any-KeyPress>", lambda _e: self.root.destroy())
        self.root.bind("<Button-1>", lambda _e: self.root.destroy())


def main():
    ap = argparse.ArgumentParser(description="FaceEQ 引导式 AU 校正向导")
    ap.add_argument("--source", type=str, default="phone",
                    help="输入源：phone（iFacialMocap/MeowFace UDP）或 vmc（PC 追踪软件）")
    ap.add_argument("--phone-port", type=int, default=PHONE_PORT,
                    help="手机 UDP 端口（仅 --source phone 时生效）")
    ap.add_argument("--vmc-port", type=int, default=39539,
                    help="VMC 输入监听端口（仅 --source vmc 时生效）")
    ap.add_argument("--out", default=os.path.join("profiles", "calibration.json"),
                    help="profile 输出路径")
    args = ap.parse_args()

    kw = {"port": args.phone_port if args.source == "phone" else args.vmc_port}
    cap = create_input(args.source, **kw)
    cap.start()
    print("看右侧中英文提示 + 左侧 live 值，保持表情后按 SPACE 采样。")

    rc = 0
    try:
        root = tk.Tk()
        wiz = _Wizard(root, cap, POSES)
        wiz.out_path = args.out
        root.mainloop()
        rc = wiz.rc
    finally:
        cap.release()
    return rc


if __name__ == "__main__":
    sys.exit(main())
