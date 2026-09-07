"""VTS 输出：VTube Studio WebSocket 参数注入（Live2D 空间）。

重连策略归适配器自己（v0.2.0 从 gui worker 收回来）：inject 遇 ConnectionError
时指数退避重试 3 次（1s/2s/4s），全失败才向上抛——调用方只需捕获并停用/提示，
不再自己重建适配器。
"""
import time

from ..vts_bridge import VTSBridge


class VTSOutput:
    kind = "vts"

    def __init__(self):
        self.bridge = VTSBridge()

    def start(self):
        self.bridge.start()          # connect + auth + discover + ensure_custom_params

    def inject(self, params, bs_params=None, face_found=True):
        """逐帧注入 Live2D 参数（bs_params 忽略——VTS 吃参数不吃 blendshape）。
        掉线自动重连；重试耗尽 raise ConnectionError。"""
        if not params:
            return
        try:
            self.bridge.inject(params, face_found=face_found)
            return
        except ConnectionError:
            pass
        last_err = None
        for attempt in range(3):
            time.sleep(2 ** attempt)   # 1s, 2s, 4s
            try:
                try:
                    self.bridge.close()
                except Exception:
                    pass
                self.bridge = VTSBridge()
                self.bridge.start()
                self.bridge.inject(params, face_found=face_found)
                return
            except ConnectionError as e:
                last_err = e
        raise ConnectionError(f"VTS 重连失败（重试 3 次）：{last_err}")

    def list_hotkeys(self):
        """当前模型的热键列表（供情绪触发配置）。"""
        return self.bridge.list_hotkeys()

    def trigger_hotkey(self, hotkey_id):
        self.bridge.trigger_hotkey(hotkey_id)

    def close(self):
        self.bridge.close()
