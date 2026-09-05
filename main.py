"""
FaceEQ 主程序：摄像头 → blendshape 映射 + 按情绪差异化放大 → 驱动 Live2D。

单线程循环：每帧 读摄像头 → base_map(原始映射) → emotions.signals(情绪) →
emotions.amplify(全局gain + 按情绪差异化) → 平滑 → 渲染/注入。

两种出画面方式（可共存）：
  - 本地预览（默认）：glfw 窗口里画 Haru。--no-preview 关掉。
  - 注入 VTube Studio：--vts，把放大+平滑后的参数经 WebSocket 喂给 VTS，
    由 VTS 渲染主播自己的模型（路径 A）。需 pip install websocket-client。

用法:
    PYTHONUTF8=1 .venv/Scripts/python.exe main.py                      # 仅本地预览
    PYTHONUTF8=1 .venv/Scripts/python.exe main.py --vts                # 预览 + 注入 VTS
    PYTHONUTF8=1 .venv/Scripts/python.exe main.py --vts --no-preview   # 纯 VTS
    PYTHONUTF8=1 .venv/Scripts/python.exe main.py --gain 1.8 --happy 1.0 --angry -0.5
ESC/关窗（有预览时）或 Ctrl-C（纯 VTS 时）退出。
"""
import argparse
import os
import sys
import time

from faceeq import emotions, engine
from faceeq.capture import PHONE_PORT, open_source
from faceeq.mapping import base_map
from faceeq.render import Live2DRenderer

DEFAULT_MODEL = os.path.join("models", "Resources", "v3", "Haru", "Haru.model3.json")
DEFAULT_PROFILE = os.path.join("profiles", "calibration.json")   # 自动探测 / 首跑生成
CALIBRATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes", "calibrate.py")


def _run_wizard(source, phone_port=PHONE_PORT):
    """subprocess 启动校正向导（首跑 / 重校），等它跑完返回。"""
    import subprocess
    cmd = [sys.executable, CALIBRATE, "--source", str(source)]
    if source == "phone":
        cmd += ["--phone-port", str(phone_port)]
    print(f"[FaceEQ] 启动校正向导：{' '.join(cmd)}")
    subprocess.run(cmd, check=False)


def main():
    ap = argparse.ArgumentParser(description="FaceEQ —— VTuber 表情增益器")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="model3.json 路径")
    ap.add_argument("--source", type=int, default=0, help="摄像头序号")
    ap.add_argument("--phone", action="store_true",
                    help="用手机面捕（iFacialMocap/MeowFace 兼容 UDP）代替摄像头，"
                         "详见 docs/phone-tracking.md")
    ap.add_argument("--phone-port", type=int, default=PHONE_PORT,
                    help="手机 UDP 端口（默认 49983，与手机 app 里填的一致）")
    ap.add_argument("--gain", type=float, default=None,
                    help="表情参数全局放大倍数（1.0=1:1，越大越夸张）；None=用 profile 或默认 1.4")
    ap.add_argument("--smooth", type=float, default=None,
                    help="平滑强度 0~1，越大越稳（消抖），越小越跟手；对口型自动减半；None=用 profile 或默认 0.4")
    ap.add_argument("--seconds", type=float, default=0,
                    help=">0 时运行指定秒数后自动退出（自动化测试用）")
    ap.add_argument("--vts", action="store_true",
                    help="把放大+平滑后的参数注入 VTube Studio (ws://localhost:8001)")
    ap.add_argument("--no-preview", action="store_true",
                    help="不开本地 Live2D 预览窗口（纯 VTS 模式）")
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

    # 捕捉源：--phone 走手机 UDP，否则摄像头序号（工厂 open_source 统一创建）
    src = "phone" if args.phone else args.source

    # profile 路径决策：--legacy 无；--recalibrate 先重校；--profile 显式；否则自动探测(首跑→校准)。
    from faceeq import profile as profile_mod
    if args.legacy:
        profile_path = None
    elif args.recalibrate:
        _run_wizard(src, args.phone_port)
        if not os.path.exists(DEFAULT_PROFILE):
            print(f"[FaceEQ] 重校未生成 {DEFAULT_PROFILE}，退出。", file=sys.stderr)
            sys.exit(1)
        profile_path = DEFAULT_PROFILE
    elif args.profile is not None:
        profile_path = args.profile
    elif os.path.exists(DEFAULT_PROFILE):
        profile_path = DEFAULT_PROFILE            # 自动用已有 profile
    else:
        print("[FaceEQ] 首次使用：先校准你的脸（照右侧中英文提示做 11 个表情，约 2 分钟）。")
        _run_wizard(src, args.phone_port)
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
    eg = cfg.emotion_gains
    if prof:
        n = sum(1 for v in prof.au_gains.values() if abs(v - 1.0) > 1e-9)
        print(f"[profile] 已加载 {profile_path}：au_gains 激活（{n} 个非 1.0）")
    elif args.legacy:
        print("[profile] --legacy：用硬编码默认（无 profile）。")

    cap = open_source(src, args.phone_port)

    ren = None
    if not args.no_preview:
        ren = Live2DRenderer(args.model,
                             title=f"FaceEQ gain={cfg.global_gain} (ESC 退出)",
                             smooth=cfg.smooth)

    bridge = None
    bridge_smoother = None
    if args.vts:
        # 懒加载：没有 websocket-client 时，纯预览路径完全不受影响
        from faceeq.smooth import Smoother
        from faceeq.vts_bridge import VTSBridge
        bridge = VTSBridge()
        bridge.start()                       # 连接 + 鉴权 + discover
        bridge_smoother = Smoother(cfg.smooth)

    if ren:
        print(f"模型参数集: {len(ren.param_ids) if ren.param_ids else '?'} 个")
    if bridge:
        print("[vts] 已接管 VTS 参数注入（set 模式，覆盖 VTS 自带跟踪）")
    print(f"全局 gain={cfg.global_gain}，平滑 smooth={cfg.smooth}，情绪倍数={eg}")
    print("对着摄像头做表情（笑/怒/惊讶/悲伤…）。ESC/Ctrl-C 退出。\n")

    fps = 0
    timer = time.time()
    t_start = time.time()
    last_params = {}
    vts_down = False
    dom = "neutral"

    try:
        while True:
            if args.seconds and (time.time() - t_start) >= args.seconds:
                break
            if ren and ren.should_close():
                break
            f = cap.read()
            params, new_dom, face_found = engine.process_frame(
                f, cfg.global_gain, eg, cfg.calib, shaping=cfg.shaping)
            if params:                       # 检测到脸 → 更新；否则保持上一帧
                last_params = params
                dom = new_dom

            if ren:
                ren.set_params(last_params)  # 预览：renderer 内部自带 EMA
                ren.frame()
            if bridge and last_params:
                # 注入前过和预览一致的 EMA（对口型减半）：VTS 里嘴不延迟、表情不抖
                try:
                    bridge.inject(bridge_smoother.step(last_params), face_found=face_found)
                    vts_down = False
                except ConnectionError as e:
                    if not vts_down:      # 只在掉线瞬间提示一次，避免每帧刷屏
                        print(f"[vts] 注入失败（VTS 掉线？）: {e}")
                        vts_down = True

            fps += 1
            if time.time() - timer >= 1.0:
                line = f"FaceEQ gain={cfg.global_gain} [{dom}] - {fps} FPS"
                if ren:
                    ren.set_title(line)
                else:
                    print(line)
                fps = 0
                timer = time.time()
    finally:
        if ren:
            ren.shutdown()                   # 关窗口 + 释放 GL
        if bridge:
            bridge.close()
        cap.release()                        # 摄像头/landmarker 释放（内部已超时兜底）
        # Windows 上 cv2/mediapipe 释放偶发卡死，被看门狗放弃的守护线程会拖住进程退出。
        # os._exit 绕过残留清理，确保进程立即结束（句柄由 OS 回收）。
        os._exit(0)


if __name__ == "__main__":
    main()
