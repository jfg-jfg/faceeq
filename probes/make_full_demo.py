"""完整版 EQ 演示视频:多段真实 TrueDepth 录像拼接,覆盖五情绪+眨眼透传。

每段: (fbx 路径, 源时间窗 t0-t1, 显示时长, 标签)。弱读输入 ×0.35 + 戏剧化预设,
双面板(原始 1:1 vs FaceEQ EQ)渲染,段内平滑、段间重置。
输出: assets/eq-demo-long.mp4
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fbx_scan import load  # noqa: E402

MODEL = os.path.abspath(os.path.join("models", "Resources", "v3", "Haru", "Haru.model3.json"))
FPS = 30
W, H = 460, 720
CROP = (100, 20, 370, 320)
OUT_W = 460
WEAK = 0.35
T17 = r"C:\Users\jiafei\AppData\Local\Temp\facemotion_inspect\take47\facemotion-09-07-08-47\facemotion-09-07-08-47.fbx"
T18 = r"C:\Users\jiafei\AppData\Local\Temp\facemotion_inspect\facemotion-09-07-08-18\facemotion-09-07-08-18.fbx"

# (fbx, 源t0, 源t1, 显示时长, 标签)
SEGMENTS = [
    (T18, 2.9, 4.2, 1.6, "中性 baseline"),
    (T17, 3.7, 4.7, 2.4, "大笑 · happy (smile)"),
    (T17, 1.3, 2.4, 2.4, "撇嘴 · sad (frown)"),
    (T17, 4.7, 6.0, 2.2, "皱鼻 · disgust (sneer)"),
    (T18, 4.4, 6.4, 2.4, "皱眉 · angry (browDown)"),
    (T18, 7.2, 8.0, 1.6, "眨眼 · 透传 1:1 (blink)"),
]

DRAMATIC = {"happy": 1.0, "angry": 0.8, "sad": 0.6, "surprised": 1.0, "disgust": 0.3}
DRAMATIC_GAIN = 2.4


def main():
    import glfw
    import live2d.v3 as live2d
    from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
    from PIL import Image, ImageDraw, ImageFont

    _FC = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"]
    _FP = next((p for p in _FC if os.path.exists(p)), None)

    def font(sz):
        from PIL import ImageFont
        if _FP:
            try:
                return ImageFont.truetype(_FP, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    OUT_H = int((CROP[3] - CROP[1]) * OUT_W / (CROP[2] - CROP[0]))
    total_frames = sum(int(dur * FPS) for *_t, dur, _l in
                       [(a, b, c, d, e) for a, b, c, d, e in
                        [(s[0], s[1], s[2], s[3], s[4]) for s in SEGMENTS]]) if False else 0

    if not glfw.init():
        raise RuntimeError("glfw.init 失败")
    win = glfw.create_window(W, H, "render", None, None)
    glfw.make_context_current(win)
    live2d.init()
    live2d.glInit()
    model = live2d.LAppModel()
    model.LoadModelJson(MODEL)
    model.Resize(W, H)
    model.SetAutoBlinkEnable(False)
    model.SetAutoBreathEnable(False)
    try:
        n = model.GetParameterCount()
        known = {model.GetParameter(i).id for i in range(n)}
    except Exception:
        known = None
    glfw.swap_interval(0)

    from faceeq.frame import Frame
    from faceeq.mapping import base_map
    from faceeq.smooth import Smoother
    from faceeq import emotions

    cache = {}
    def get_shapes(path):
        if path not in cache:
            _, shapes = load(path)
            cache[path] = shapes
        return cache[path]

    def resample(shapes, t):
        bs = {}
        for name, (kt, kv) in shapes.items():
            if not kt:
                continue
            tt = min(max(t, kt[0]), kt[-1])
            i = min(range(len(kt)), key=lambda k: abs(kt[k] - tt))
            bs[name] = kv[i] / 100.0 * WEAK
        return bs

    tmp = os.path.join("assets", "_demo_frames")
    os.makedirs(tmp, exist_ok=True)
    combo_idx = 0

    for (fbx, st0, st1, disp_dur, seg_label) in SEGMENTS:
        shapes = get_shapes(fbx)
        sm_raw, sm_eq = Smoother(0.35), Smoother(0.35)
        n = int(disp_dur * FPS)
        key = "mouthSmileLeft" if "happy" in seg_label or "笑" in seg_label else "mouthFrownLeft"
        if "皱" in seg_label and "鼻" in seg_label:
            key = "noseSneerLeft"
        if "眉" in seg_label and "angry" in seg_label:
            key = "browDownLeft"
        if "眨" in seg_label:
            key = "eyeBlinkLeft"

        for k in range(n):
            frac = k / max(1, n - 1)
            src_t = st0 + (st1 - st0) * frac
            bs_in = resample(shapes, src_t)
            emo = emotions.signals(bs_in)
            bs_eq = emotions.bs_amplify(bs_in, emo, DRAMATIC_GAIN, DRAMATIC)
            if glfw.window_should_close(win):
                raise SystemExit("window closed")

            glfw.poll_events()
            live2d.clearBuffer()
            for name, val in sm_raw.step(base_map(Frame(bs=bs_in))).items():
                if known is None or name in known:
                    model.SetParameterValue(name, val, 1)
            model.Update()
            model.Draw()
            data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
            a = Image.frombytes("RGB", (W, H), data).transpose(Image.FLIP_TOP_BOTTOM)
            a = a.crop(CROP).resize((OUT_W, OUT_H), Image.LANCZOS)

            live2d.clearBuffer()
            for name, val in sm_eq.step(base_map(Frame(bs=bs_eq))).items():
                if known is None or name in known:
                    model.SetParameterValue(name, val, 1)
            model.Update()
            model.Draw()
            data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
            b = Image.frombytes("RGB", (W, H), data).transpose(Image.FLIP_TOP_BOTTOM)
            b = b.crop(CROP).resize((OUT_W, OUT_H), Image.LANCZOS)

            bar = Image.new("RGB", (OUT_W * 2, 46), (16, 18, 24))
            d = ImageDraw.Draw(bar)
            d.text((OUT_W // 2 - 60, 14), "WEAK TRACKER 1:1", fill=(170, 170, 170))
            d.text((OUT_W + OUT_W // 2 - 70, 14), "FaceEQ EQ (Dramatic)", fill=(90, 200, 250))
            d.text((12, 34), seg_label + "  ·  " + f"{key} {bs_in.get(key, 0):.2f}",
                   font=font(15), fill=(120, 210, 250))
            d.text((OUT_W + 12, 34), seg_label + "  ·  " + f"{key} {bs_eq.get(key, 0):.2f}",
                   font=font(15), fill=(120, 210, 250))
            combo = Image.new("RGB", (OUT_W * 2, OUT_H + 46), (16, 18, 24))
            combo.paste(bar, (0, 0))
            combo.paste(a, (0, 46))
            combo.paste(b, (OUT_W, 46))
            combo.save(os.path.join(tmp, f"f_{combo_idx:05d}.png"))
            combo_idx += 1
        print(f"[seg] {seg_label} 完成 ({n} 帧)")

    live2d.dispose()
    glfw.terminate()

    import subprocess
    mp4 = os.path.join("assets", "eq-demo-long.mp4")
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS),
                    "-i", os.path.join(tmp, "f_%05d.png"),
                    "-c:v", "mpeg4", "-q:v", "3", mp4],
                   check=True, capture_output=True)
    print(f"[mp4] {mp4} ({os.path.getsize(mp4) / 1e6:.1f} MB, {combo_idx} 帧)")


if __name__ == "__main__":
    main()
