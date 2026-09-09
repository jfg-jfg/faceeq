"""营销素材：TrueDepth 实录回放 → 「原始 1:1 vs FaceEQ EQ」双面板 Live2D 对比 GIF。

单 glfw 窗口每帧双绘制（同上下文，规避 live2d 二次初始化问题）：
  A. 原始 1:1        = base_map(bs_raw)
  B. FaceEQ EQ(元气) = base_map(bs_amplify(bs_raw, 元气增益))
数据：iPad 录制导出的 FBX（真实 TrueDepth 表情曲线）。
用法： PYTHONUTF8=1 .venv/Scripts/python.exe probes/make_compare_gif.py <take.fbx> [--zoom 1.9]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fbx_scan import load  # noqa: E402

MODEL = os.path.join("models", "Resources", "v3", "Haru", "Haru.model3.json")
FPS = 30
W, H = 460, 720
DRAMATIC = {"happy": 1.0, "angry": 0.8, "sad": 0.6, "surprised": 1.0, "disgust": 0.3}
DRAMATIC_GAIN = 2.4


_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
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


def resample(shapes, t):
    bs = {}
    for name, (kt, kv) in shapes.items():
        if not kt:
            continue
        lo, hi = kt[0], kt[-1]
        tt = min(max(t, lo), hi)
        i = min(range(len(kt)), key=lambda k: abs(kt[k] - tt))
        bs[name] = kv[i] / 100.0
    return bs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fbx")
    ap.add_argument("--out", default=os.path.join("assets", "eq-demo.gif"))
    ap.add_argument("--seconds", type=float, default=0)
    ap.add_argument("--weak", type=float, default=0.35,
                    help="输入弱读缩放(模拟欠读追踪源:0.35=只有 35% 幅度)")
    ap.add_argument("--speed", type=float, default=0.5, help="GIF 播放速率(0.5=慢一倍)")
    args = ap.parse_args()

    import glfw
    import live2d.v3 as live2d
    from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
    from PIL import Image

    rot, shapes = load(args.fbx)
    t0 = min(kt[0] for kt, _ in shapes.values() if kt)
    t1 = max(kt[-1] for kt, _ in shapes.values() if kt)
    if args.seconds > 0:
        t1 = min(t1, t0 + args.seconds)
    n_frames = int((t1 - t0) * FPS)
    streams = []
    for i in range(n_frames):
        t = t0 + i / FPS
        bs_full = resample(shapes, t)
        streams.append({k: v * args.weak for k, v in bs_full.items()})   # 弱读输入
    print(f"回放 {t0:.1f}s–{t1:.1f}s → {n_frames} 帧 @ {FPS}fps")

    from PIL import Image, ImageDraw
    from faceeq.frame import Frame
    from faceeq.mapping import base_map
    from faceeq.smooth import Smoother
    from faceeq import emotions

    if not glfw.init():
        raise RuntimeError("glfw.init 失败")
    win = glfw.create_window(W, H, "render", None, None)
    glfw.make_context_current(win)
    live2d.init()
    live2d.glInit()
    model = live2d.LAppModel()
    model.LoadModelJson(os.path.abspath(MODEL))
    model.Resize(W, H)
    model.SetAutoBlinkEnable(False)
    model.SetAutoBreathEnable(False)
    try:
        n = model.GetParameterCount()
        known = {model.GetParameter(i).id for i in range(n)}
    except Exception:
        known = None
    glfw.swap_interval(0)

    sm_raw, sm_eq = Smoother(0.35), Smoother(0.35)
    tmp = os.path.join(os.path.dirname(os.path.abspath(args.out)), "_gif_frames")
    os.makedirs(os.path.join(tmp, "raw"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "eq"), exist_ok=True)

    CROP = (100, 20, 370, 320)   # 脸部/肩部区域(zoom1.0 全身取景下)
    CROP_W, CROP_H = CROP[2] - CROP[0], CROP[3] - CROP[1]
    OUT_W = 460
    OUT_H = int(CROP_H * OUT_W / CROP_W)

    readouts = []   # 每帧 (raw读数, eq读数) 用于角标

    def draw_capture(params, sm, path, readout=""):
        glfw.poll_events()
        live2d.clearBuffer()
        for name, val in sm.step(params).items():
            if known is None or name in known:
                model.SetParameterValue(name, val, 1)
        model.Update()
        model.Draw()
        data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
        img = Image.frombytes("RGB", (W, H), data).transpose(Image.FLIP_TOP_BOTTOM)
        face = img.crop(CROP).resize((OUT_W, OUT_H), Image.LANCZOS)
        d = ImageDraw.Draw(face)
        if readout:
            d.text((10, OUT_H - 30), readout, font=_font(20), fill=(120, 210, 250))
        face.save(path)
        glfw.swap_buffers(win)

    for i, bs_in in enumerate(streams):
        if glfw.window_should_close(win):
            n_frames = i
            break
        emo = emotions.signals(bs_in)
        bs_eq = emotions.bs_amplify(bs_in, emo, DRAMATIC_GAIN, DRAMATIC)
        key = "mouthSmileLeft" if emo["happy"] >= max(emo["sad"], emo["disgust"]) else "mouthFrownLeft"
        ro_raw = f"{key} {bs_in.get(key, 0):.2f}"
        ro_eq = f"{key} {bs_eq.get(key, 0):.2f}"
        readouts.append((ro_raw, ro_eq))
        draw_capture(base_map(Frame(bs=bs_in)), sm_raw,
                     os.path.join(tmp, "raw", f"raw_{i:04d}.png"), ro_raw)
        draw_capture(base_map(Frame(bs=bs_eq)), sm_eq,
                     os.path.join(tmp, "eq", f"eq_{i:04d}.png"), ro_eq)
    live2d.dispose()
    glfw.terminate()
    print(f"[render] {n_frames} 帧 ×2 面板完成")

    # —— 合成 ——
    import subprocess
    os.makedirs(os.path.join(tmp, "combo"), exist_ok=True)
    delay_ms = int(1000 / FPS / args.speed)
    for i in range(n_frames):
        a = Image.open(os.path.join(tmp, "raw", f"raw_{i:04d}.png"))
        b = Image.open(os.path.join(tmp, "eq", f"eq_{i:04d}.png"))
        bar = Image.new("RGB", (OUT_W * 2, 42), (16, 18, 24))
        d = ImageDraw.Draw(bar)
        d.text((OUT_W // 2 - 46, 13), "WEAK TRACKER  1:1", fill=(170, 170, 170))
        d.text((OUT_W + OUT_W // 2 - 78, 13), "FaceEQ EQ (Dramatic)", fill=(90, 200, 250))
        combo = Image.new("RGB", (OUT_W * 2, OUT_H + 42), (16, 18, 24))
        combo.paste(bar, (0, 0))
        combo.paste(a, (0, 42))
        combo.paste(b, (OUT_W, 42))
        combo.save(os.path.join(tmp, "combo", f"c_{i:04d}.png"))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-framerate", "1000", "-i", args.out.replace(".gif", ".png"),
        "-loop", "0", args.out], check=True, capture_output=True) if False else None
    # PIL 直接拼 GIF(逐帧 delay,支持慢放)
    frames_c = [Image.open(os.path.join(tmp, "combo", f"c_{i:04d}.png"))
                for i in range(n_frames)]
    frames_c[0].save(args.out, save_all=True, append_images=frames_c[1:],
                     duration=delay_ms, loop=0, optimize=True)
    print(f"[gif] {args.out} ({os.path.getsize(args.out) / 1e6:.1f} MB)")
    # MP4(B站/推特定稿):mpeg4 编码(本机 ffmpeg 的 libx264/h264_mf 构建异常,-22)
    mp4 = os.path.splitext(args.out)[0] + ".mp4"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", os.path.join(tmp, "combo", "c_%04d.png"),
        "-c:v", "mpeg4", "-q:v", "3", mp4], check=True, capture_output=True)
    print(f"[mp4] {mp4} ({os.path.getsize(mp4) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
