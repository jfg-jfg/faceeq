"""取景校准探针:不同 (zoom, offsetY) 组合渲染单帧 → 拼接 contact sheet。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import glfw
import live2d.v3 as live2d
from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
from PIL import Image, ImageDraw

MODEL = os.path.abspath(os.path.join("models", "Resources", "v3", "Hana", "Haru.model3.json"))
if not os.path.exists(MODEL):
    MODEL = os.path.abspath(os.path.join("models", "Resources", "v3", "Haru", "Haru.model3.json"))
W, H = 300, 460
BS = {"mouthSmileLeft": 0.8, "mouthSmileRight": 0.8, "eyeSquintLeft": 0.5,
      "eyeSquintRight": 0.5, "browOuterUpLeft": 0.3, "jawOpen": 0.3}

if not glfw.init():
    raise SystemExit("glfw fail")
win = glfw.create_window(W, H, "framing", None, None)
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

combos = [(1.6, 0.0), (1.6, 0.12), (1.6, 0.22), (2.0, 0.3), (2.0, 0.42), (2.0, 0.54)]
sheet = Image.new("RGB", (W * 3, (H + 24) * 3), (30, 30, 30))

for idx, (z, oy) in enumerate(combos):
    model.SetScale(z)
    model.SetOffsetY(int(H * oy))
    glfw.poll_events()
    live2d.clearBuffer()
    for name, v in BS.items():
        if known is None or name in known:
            model.SetParameterValue(name, v, 1)
    model.Update()
    model.Draw()
    data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = Image.frombytes("RGB", (W, H), data).transpose(Image.FLIP_TOP_BOTTOM)
    tile = Image.new("RGB", (W, H + 24), (0, 0, 0))
    tile.paste(img, (0, 24))
    d = ImageDraw.Draw(tile)
    d.text((6, 5), f"zoom={z} offY={oy:+.2f}", fill=(90, 200, 250))
    cx, cy = idx % 3, idx // 3
    sheet.paste(tile, (cx * W, cy * (H + 24)))
    print("rendered", z, oy)

live2d.dispose()
glfw.terminate()
sheet.save(os.path.join("assets", "_framing.png"))
print("saved assets/_framing.png")
