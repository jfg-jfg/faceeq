"""FaceEQ CLI：面捕输入 → EQ 管线 → 输出目标（自动化/调试入口，产品主入口是 gui.py）。

v0.2.0 纯协议管线：
    输入（--input phone|vmc）→ Pipeline.step（signals → bs EQ → 映射 → 平滑）
    → 输出（--output vts|vmc|osc，可多选并发）。

用法:
    PYTHONUTF8=1 .venv\Scripts\python.exe main.py --input phone --output vts
    PYTHONUTF8=1 .venv\Scripts\python.exe main.py --input vmc --output vts vmc
    PYTHONUTF8=1 .venv\Scripts\python.exe main.py --input phone --gain 1.8 --happy 1.0 --angry -0.5
Ctrl-C 退出。
"""
import argparse
import os
import sys
import time

from faceeq import emotions
from faceeq.core import Pipeline, PipelineConfig

DEFAULT_PROFILE = os.path.join("profiles", "calibration.json")   # 自动探测 / 首跑生成
CALIBRATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes", "calibrate.py")


def _run_wizard(input_kind, input_kw):
    """subprocess 启动校正向导（首跑 / 重校），等它跑完返回。"""
    import subprocess
    cmd = [sys.executable, CALIBRATE, "--source", input_kind]
    if input_kind == "phone":
        cmd += ["--phone-port", str(input_kw.get("port", 49983))]
    elif input_kind == "vmc":
        cmd += ["--vmc-port", str(input_kw.get("port", 39539))]
    print(f"[FaceEQ] 启动校正向导：{' '.join(cmd)}")
    subprocess.run(cmd, check=False)


def main():
    ap = argparse.ArgumentParser(description="FaceEQ —— VTuber 表情情绪 EQ（纯协议中间件）")
    ap.add_argument("--input", choices=["phone", "vmc"], default="phone",
                    help="输入源：phone=iFacialMocap/MeowFace UDP；vmc=VMC 协议"
                         "（VSeeFace/Warudo 等 PC 追踪软件发来的 blendshape）")
    ap.add_argument("--phone-port", type=int, default=49983,
                    help="手机 UDP 端口（默认 49983，与手机 app 里填的一致）")
    ap.add_argument("--vmc-port", type=int, default=39539,
                    help="VMC 输入监听端口（默认 39539，发送端软件里对齐）")
    ap.add_argument("--gain", type=float, default=None,
                    help="表情全局放大倍数（1.0=1:1，越大越夸张）；None=用 profile 或默认 1.4")
    ap.add_argument("--smooth", type=float, default=None,
                    help="平滑强度 0~1，越大越稳（消抖），越小越跟手；对口型自动减半；None=用 profile 或默认 0.4")
    ap.add_argument("--seconds", type=float, default=0,
                    help=">0 时运行指定秒数后自动退出（自动化测试用）")
    ap.add_argument("--vts", action="store_true",
                    help="[兼容旧参数] 等价 --output vts")
    ap.add_argument("--output", nargs="+", choices=["vts", "vmc", "osc"], default=[],
                    help="输出目标（可多选并发）：vts=VTube Studio(Live2D 注入)；vmc=VMC 协议"
                         "(Warudo/VNyans 等 3D 工具)；osc=通用 OSC")
    ap.add_argument("--osc-host", default="127.0.0.1", help="vmc/osc 输出的目标 IP")
    ap.add_argument("--osc-port", type=int, default=None,
                    help="vmc/osc 输出的目标端口（vmc 默认 39540，osc 默认 9000）")
    ap.add_argument("--profile", default=None,
                    help="加载校准 profile（JSON）；不传=自动用 profiles/calibration.json，没有就首跑校准")
    ap.add_argument("--recalibrate", action="store_true",
                    help="先重跑校正向导（覆盖 profiles/calibration.json），再继续")
    ap.add_argument("--legacy", action="store_true",
                    help="强制用硬编码默认、不找 profile（调试/对比）")
    # 逐情绪强度（有符号 -1..1）：1.0=全量夸张(默认)，0=不塑造，负=抑制该情绪(persona)
    for e in emotions.EMOTIONS:
        ap.add_argument(f"--{e}", type=float, default=None,
                        help=f"{e} 情绪强度 -1..1：1.0=全量夸张(默认)，0=不额外塑造，负=抑制该情绪往中性压")
    args = ap.parse_args()

    input_kind = args.input
    input_kw = {"port": args.phone_port if input_kind == "phone" else args.vmc_port}

    # profile 路径决策：--legacy 无；--recalibrate 先重校；--profile 显式；否则自动探测(首跑→校准)。
    from faceeq import profile as profile_mod
    if args.legacy:
        profile_path = None
    elif args.recalibrate:
        _run_wizard(input_kind, input_kw)
        if not os.path.exists(DEFAULT_PROFILE):
            print(f"[FaceEQ] 重校未生成 {DEFAULT_PROFILE}，退出。", file=sys.stderr)
            sys.exit(1)
        profile_path = DEFAULT_PROFILE
    elif args.profile is not None:
        profile_path = args.profile
    elif os.path.exists(DEFAULT_PROFILE):
        profile_path = DEFAULT_PROFILE            # 自动用已有 profile
    else:
        print("[FaceEQ] 首次使用：先校准你的脸（照提示做 11 个表情，约 2 分钟）。")
        _run_wizard(input_kind, input_kw)
        profile_path = DEFAULT_PROFILE if os.path.exists(DEFAULT_PROFILE) else None
        if profile_path is None:
            print("[FaceEQ] 校准未完成（没生成 profile）。重跑 probes/calibrate.py，或用 --legacy。",
                  file=sys.stderr)
            sys.exit(1)

    try:
        prof = profile_mod.load_profile(profile_path)   # None→legacy；坏文件 raise
    except (FileNotFoundError, ValueError) as e:
        print(f"[profile] 加载失败 {profile_path}：{e}", file=sys.stderr)
        sys.exit(1)
    cfg = profile_mod.resolve(args, prof)
    if prof:
        n = sum(1 for v in prof.au_gains.values() if abs(v - 1.0) > 1e-9)
        print(f"[profile] 已加载 {profile_path}：au_gains 激活（{n} 个非 1.0）")
    elif args.legacy:
        print("[profile] --legacy：用硬编码默认（无 profile）。")

    from faceeq.inputs import create_input
    cap = create_input(input_kind, port=input_kw["port"])
    cap.start()

    outputs = []
    kinds = list(args.output)
    if args.vts and "vts" not in kinds:
        kinds.insert(0, "vts")
    if kinds:
        from faceeq.outputs import create_output
        for kind in kinds:
            adapter = create_output(kind, args.osc_host, args.osc_port)
            adapter.start()
            outputs.append((kind, adapter))
            print(f"[output] {kind} 已接管（覆盖目标软件自带跟踪）")
    print(f"全局 gain={cfg.global_gain}，平滑 smooth={cfg.smooth}，情绪倍数={cfg.emotion_gains}")
    print(f"输入源 {input_kind}。做表情即可，Ctrl-C 退出。\n")

    pipeline = Pipeline(PipelineConfig(gain=cfg.global_gain, smooth=cfg.smooth,
                                       emotion_gains=cfg.emotion_gains, calib=cfg.calib,
                                       shaping=cfg.shaping))
    fps = 0
    timer = time.time()
    t_start = time.time()
    down = set()

    try:
        while True:
            if args.seconds and (time.time() - t_start) >= args.seconds:
                break
            res = pipeline.step(cap.read())
            for kind, adapter in outputs:
                try:
                    adapter.inject(res.params, res.bs, face_found=res.face_found)
                    down.discard(kind)
                except ConnectionError as e:
                    if kind not in down:      # 只在掉线瞬间提示一次，避免每帧刷屏
                        print(f"[{kind}] 注入失败（目标掉线？）: {e}")
                        down.add(kind)

            fps += 1
            if time.time() - timer >= 1.0:
                print(f"FaceEQ gain={cfg.global_gain} [{res.dominant or 'neutral'}] - {fps} FPS")
                fps = 0
                timer = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        for _kind, adapter in outputs:
            try:
                adapter.close()
            except Exception:
                pass
        cap.release()
        os._exit(0)   # 接收线程是守护线程；直接结束进程最干净


if __name__ == "__main__":
    main()
