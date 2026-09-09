r"""A/B 对比演示录制器:一遍表演,程序按时间表自动切换两个预设。

面向营销素材录制:你在 OBS 里只录形象软件窗口,程序按时间表在每个表情段内
自动切换「A=1比1(原始)」和「B=EQ 预设」,置顶小窗提示当前表情/预设/倒计时,
切换时蜂鸣。结束写 ab_schedule.json(分段边界),供剪辑程序精确对齐。

时间表:3s 中性热身 → [表情段 6s(前 3s=A / 后 3s=B) + 2s 中性] × N

用法:
    PYTHONUTF8=1 .venv\Scripts\python.exe probes\ab_recorder.py --input phone --output vts
    ... --a "★1比1对照 Reference" --b "★戏剧化 Dramatic"
"""
import argparse
import threading
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq import emotions
from faceeq.core import Pipeline, PipelineConfig

EXPR_EACH = 6.0    # 每个表情段时长(前半 A / 后半 B)
GAP = 2.0          # 表情间中性间隔
WARMUP = 3.0       # 开场中性热身

EXPRS = ["大笑(嘴角上扬+眯眼)", "撇嘴(嘴角下拉)", "皱鼻(皱鼻+抬上唇)", "惊讶(瞪眼+张嘴)"]


def load_preset_file(name):
    from faceeq import resource_path
    if name.startswith("★"):
        path = os.path.join(resource_path("presets", "builtin"), name[1:] + ".json")
    else:
        path = os.path.join("presets", name + ".json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_schedule(a_name, b_name):
    """段列表: {expr, preset('A'/'B'/'N'), gain, eg, smooth, t0, t1}。"""
    sched = []
    t = 0.0
    sched.append({"expr": "中性(热身)", "preset": "N", "t0": t, "t1": t + WARMUP})
    t += WARMUP
    for expr in EXPRS:
        sched.append({"expr": expr, "preset": "A", "t0": t, "t1": t + EXPR_EACH / 2})
        t += EXPR_EACH / 2
        sched.append({"expr": expr, "preset": "B", "t0": t, "t1": t + EXPR_EACH / 2})
        t += EXPR_EACH / 2
        sched.append({"expr": "中性(换气)", "preset": "N", "t0": t, "t1": t + GAP})
        t += GAP
    return sched, t


def main():
    ap = argparse.ArgumentParser(description="FaceEQ A/B 对比演示录制器")
    ap.add_argument("--input", choices=["phone", "vmc"], default="phone")
    ap.add_argument("--phone-port", type=int, default=49983)
    ap.add_argument("--vmc-port", type=int, default=39539)
    ap.add_argument("--output", nargs="+", choices=["vts", "vmc", "osc"], default=["vts"])
    ap.add_argument("--osc-host", default="127.0.0.1")
    ap.add_argument("--osc-port", type=int, default=None)
    ap.add_argument("--a", default="★1比1对照 Reference", help="A 段预设(=原始)")
    ap.add_argument("--b", default="★戏剧化 Dramatic", help="B 段预设(EQ 全开)")
    ap.add_argument("--profile", default=os.path.join("profiles", "calibration.json"))
    args = ap.parse_args()

    # 预设 → 管线参数
    def preset_cfg(name):
        data = load_preset_file(name)
        return {"gain": float(data.get("global_gain") or 1.4),
                "emotion_gains": {e: float((data.get("emotion_gains") or {}).get(e, 1.0))
                                  for e in emotions.EMOTIONS},
                "smooth": float(data.get("smooth") or 0.4)}

    cfg_a = preset_cfg(args.a)
    cfg_b = preset_cfg(args.b)
    cfg_n = {"gain": 1.0, "emotion_gains": {e: 0.0 for e in emotions.EMOTIONS}, "smooth": 0.4}

    from faceeq.inputs import create_input
    from faceeq.outputs import create_output

    kw = {"port": args.phone_port if args.input == "phone" else args.vmc_port}
    cap = create_input(args.input, **kw)
    cap.start()
    outputs = []
    for kind in args.output:
        ad = create_output(kind, args.osc_host, args.osc_port)
        ad.start()
        outputs.append(ad)

    pipeline = Pipeline(PipelineConfig(**cfg_a))
    prof = None
    if os.path.exists(args.profile):
        from faceeq import profile as profile_mod
        prof = profile_mod.load_profile(args.profile)
        calib = profile_mod.resolve(
            type("A", (), {"gain": None, "smooth": None,
                           **{e: None for e in emotions.EMOTIONS}})(), prof).calib
        pipeline.cfg.calib = calib
        print(f"[profile] {args.profile} 已加载")

    # —— 置顶提示小窗 ——
    import tkinter as tk
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.geometry("360x150+40+40")
    root.configure(bg="#101010")
    v_expr = tk.Label(root, text="准备…", bg="#101010", fg="#ebebeb",
                      font=("Microsoft YaHei", 20, "bold"))
    v_expr.pack(fill="x", pady=(10, 0))
    v_phase = tk.Label(root, text="A 原始", bg="#101010", fg="#50dc50",
                       font=("Microsoft YaHei", 26, "bold"))
    v_phase.pack(fill="x")
    v_count = tk.Label(root, text="", bg="#101010", fg="#dcdcdc",
                       font=("Microsoft YaHei", 14))
    v_count.pack(fill="x")
    v_hint = tk.Label(root, text="OBS 录形象窗口;听蜂鸣换气", bg="#101010",
                      fg="#909090", font=("Microsoft YaHei", 10))
    v_hint.pack(fill="x")
    print("[ab] 3 秒后开始;置顶小窗显示当前表情/预设/倒计时,蜂鸣=切换点")

    ui_state = {"expr": "准备…", "phase": "A 原始", "count": "", "done": False}

    def run_worker():
        time.sleep(3.0)
        sched, total = build_schedule(args.a, args.b)
        t_start = time.time()
        last_seg = None
        last_beep = -1.0
        while True:
            t = time.time() - t_start
            seg = None
            for s in sched:
                if s["t0"] <= t < s["t1"]:
                    seg = s
                    break
            if seg is None:
                break
            if seg is not last_seg:
                # 切换:管线参数 + 蜂鸣
                if seg["preset"] == "A":
                    pipeline.cfg.gain, pipeline.cfg.emotion_gains = cfg_a["gain"], cfg_a["emotion_gains"]
                    pipeline.cfg.smooth = cfg_a["smooth"]
                elif seg["preset"] == "B":
                    pipeline.cfg.gain, pipeline.cfg.emotion_gains = cfg_b["gain"], cfg_b["emotion_gains"]
                    pipeline.cfg.smooth = cfg_b["smooth"]
                else:
                    pipeline.cfg.gain, pipeline.cfg.emotion_gains = cfg_n["gain"], cfg_n["emotion_gains"]
                    pipeline.cfg.smooth = cfg_n["smooth"]
                try:
                    import winsound
                    winsound.Beep(1200 if seg["preset"] in ("A", "B") else 700, 150)
                except Exception:
                    pass
                last_seg = seg
            remain = seg["t1"] - t
            ui_state["expr"] = "做: " + seg["expr"]
            ui_state["phase"] = {"A": "A 原始 1:1", "B": "B FaceEQ EQ",
                                 "N": "中性"}[seg["preset"]]
            ui_state["count"] = f"{remain:.1f}s"
            f = cap.read()
            res = pipeline.step(f)
            for ad in outputs:
                try:
                    ad.inject(res.params, res.bs, face_found=res.face_found)
                except Exception:
                    pass
            if t >= total:
                break

    # tkinter 主线程跑 UI,worker 在后台线程
    err = {}

    def ui_tick():
        if "done" in ui_state:
            return
        v_expr.configure(text=ui_state["expr"])
        v_phase.configure(text=ui_state["phase"])
        v_count.configure(text=ui_state["count"])
        root.after(100, ui_tick)

    def worker_wrap():
        try:
            run_worker()
        except Exception as e:
            err["e"] = e
        finally:
            ui_state["done"] = True
            try:
                root.destroy()
            except Exception:
                pass

    threading.Thread(target=worker_wrap, daemon=True).start()
    ui_tick()
    root.mainloop()

    # —— 落分段表 ——
    sched, total = build_schedule(args.a, args.b)
    with open("ab_schedule.json", "w", encoding="utf-8") as fh:
        json.dump({"total": total, "a_preset": args.a, "b_preset": args.b,
                   "segments": sched}, fh, ensure_ascii=False, indent=2)
    print(f"[ab] 完成,分段表写入 ab_schedule.json(总时长 {total:.0f}s)")
    if "e" in err:
        print(f"[ab] 运行出错: {err['e']}", file=sys.stderr)

    for ad in outputs:
        try:
            ad.close()
        except Exception:
            pass
    cap.release()
    os._exit(0)


if __name__ == "__main__":
    main()
