"""
可复用 Live2D 渲染器：glfw 窗口 + live2d.v3 加载/渲染 + 每参数 EMA 平滑。

平滑逻辑统一用 smooth.Smoother（与 VTS 注入路径同一份实现，改规则只动一处）：
每帧把当前值朝目标值收敛，嘴参数（对口型）平滑减半保低延迟。smooth∈[0,1] 是总强度。
"""
import os

import glfw
import live2d.v3 as live2d

from .smooth import Smoother


class Live2DRenderer:
    def __init__(self, model_json: str, width: int = 450, height: int = 700,
                 title: str = "FaceEQ", smooth: float = 0.7):
        if not glfw.init():
            raise RuntimeError("glfw.init 失败")
        self._win = glfw.create_window(width, height, title, None, None)
        if not self._win:
            glfw.terminate()
            raise RuntimeError("创建窗口失败（显卡/驱动不支持 OpenGL？）")
        glfw.make_context_current(self._win)

        live2d.init()
        live2d.glInit()

        self._model = live2d.LAppModel()
        self._model.LoadModelJson(os.path.abspath(model_json))
        self._model.Resize(width, height)
        # 关掉自动眨眼/呼吸，由我们完全接管参数（保证映射可预测）
        self._model.SetAutoBlinkEnable(False)
        self._model.SetAutoBreathEnable(False)

        # 缓存模型实际拥有的参数 id，跳过不存在的（不同模型参数集不同）
        try:
            n = self._model.GetParameterCount()
            self._known = {self._model.GetParameter(i).id for i in range(n)}
        except Exception:
            self._known = None  # 读取失败则不过滤

        glfw.swap_interval(1)

        self._smoother = Smoother(smooth)

    @property
    def param_ids(self):
        return self._known

    def set_params(self, params: dict) -> None:
        """把 {参数名: 目标值} 写到模型上，途中经 Smoother 做每参数 EMA（嘴减半）。"""
        for name, val in self._smoother.step(params).items():
            if self._known is not None and name not in self._known:
                continue
            self._model.SetParameterValue(name, val, 1)

    def frame(self) -> None:
        """一帧：清屏 → 更新 → 绘制 → 交换缓冲。"""
        glfw.poll_events()
        live2d.clearBuffer()
        self._model.Update()
        self._model.Draw()
        glfw.swap_buffers(self._win)

    def set_title(self, title: str) -> None:
        glfw.set_window_title(self._win, title)

    def should_close(self) -> bool:
        if glfw.window_should_close(self._win):
            return True
        if glfw.get_key(self._win, glfw.KEY_ESCAPE) == glfw.PRESS:
            return True
        return False

    def shutdown(self) -> None:
        live2d.dispose()
        glfw.terminate()
