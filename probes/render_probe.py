"""
Phase 1 渲染探针：用 live2d-py 加载并渲染 Haru，证明本机能跑通
「init → 加载模型 → 设参数 → 渲染」这条链。

默认(交互)：开窗口渲染 Haru，嘴张开度/嘴形按正弦摆动，ESC 或关窗退出。
--smoke：只初始化 + 加载 + 打印参数表后立刻退出（不开渲染循环），
         用来验证 GL/模型加载 + 看 Haru 暴露了哪些参数（后续映射要用）。

用法:
    .venv\\Scripts\\python.exe probes\\render_probe.py --smoke
    .venv\\Scripts\\python.exe probes\\render_probe.py
"""
import os
import sys
import time
import math

import glfw
import OpenGL.GL as GL
import live2d.v3 as live2d
from live2d.v3.params import StandardParams

MODEL = os.path.join("models", "Resources", "v3", "Haru", "Haru.model3.json")


def list_params(model) -> None:
    """打印模型所有参数及其范围——后续 blendshape→参数映射的依据。
    LAppModel 用 GetParameterCount() + GetParameter(i)，每个 param 带
    .id/.type/.value/.min/.max/.default。
    """
    try:
        n = model.GetParameterCount()
        print(f"== 模型参数 ({n}) ==")
        for i in range(n):
            p = model.GetParameter(i)
            print(f"  {p.id:34s} [{p.min:6.2f} .. {p.max:6.2f}]  默认={p.default:.2f}")
    except Exception as e:
        print("参数列表读取失败:", e)


def main(smoke: bool = False, seconds: float = 0) -> None:
    if not glfw.init():
        raise RuntimeError("glfw.init 失败")
    w, h = 450, 700
    window = glfw.create_window(w, h, "Haru render probe (ESC 退出)", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("创建窗口失败（显卡/驱动不支持 OpenGL？）")
    glfw.make_context_current(window)

    live2d.init()
    live2d.glInit()

    model = live2d.LAppModel()
    model.LoadModelJson(os.path.abspath(MODEL))
    model.Resize(w, h)
    model.SetAutoBreathEnable(False)
    model.SetAutoBlinkEnable(False)

    list_params(model)
    print("Canvas size:", model.GetCanvasSize())

    if smoke:
        print("\nSMOKE_OK：GL 初始化 + 模型加载 + 参数读取全部通过。")
        live2d.dispose()
        glfw.terminate()
        return

    glfw.swap_interval(1)
    fps = 0
    timer = time.time()
    t_start = time.time()

    while not glfw.window_should_close(window):
        glfw.poll_events()

        # 用正弦驱动嘴部两个参数，肉眼确认"我们能设参数"
        s = (math.sin(time.time() * 2.0) + 1) / 2    # 0..1  → 嘴张开度
        f = math.sin(time.time() * 1.5)              # -1..1 → 嘴形（撇↔笑）
        model.SetParameterValue(StandardParams.ParamMouthOpenY, s, 1)
        model.SetParameterValue(StandardParams.ParamMouthForm, f, 1)

        live2d.clearBuffer()
        model.Update()
        model.Draw()
        glfw.swap_buffers(window)

        fps += 1
        if glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS:
            break
        if seconds and (time.time() - t_start) >= seconds:
            break
        if time.time() - timer >= 1.0:
            glfw.set_window_title(window, f"Haru render probe - {fps} FPS")
            fps = 0
            timer = time.time()

    print(f"渲染循环结束，存活 {time.time() - t_start:.2f}s")
    live2d.dispose()
    glfw.terminate()


if __name__ == "__main__":
    secs = 0
    for a in sys.argv:
        if a.startswith("--seconds="):
            secs = float(a.split("=", 1)[1])
    main(smoke="--smoke" in sys.argv, seconds=secs)
