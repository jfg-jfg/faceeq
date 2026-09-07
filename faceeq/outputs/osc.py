"""通用 OSC 输出：给没有 VMC 的目标（如 VRChat FT 桥）。

无映射文件：每形状发 <prefix>/bs/<ARKit名>；有 osc_mapping.json
（{blendshape 名: 完整 OSC 地址}）：只发映射了的形状（精确对接目标参数）。
"""
import json
import os

from pythonosc.udp_client import SimpleUDPClient

OSC_MAPPING_FILE = "osc_mapping.json"   # OscRawOutput 的可选名字映射


class OscRawOutput:
    kind = "osc"
    DEFAULT_PORT = 9000     # VRChat OSC 惯例端口

    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, prefix="/faceeq",
                 mapping=None):
        self._client = SimpleUDPClient(host, int(port))
        self._prefix = prefix.rstrip("/") or "/faceeq"
        self._mapping = dict(mapping or {})

    def start(self):
        pass

    def inject(self, params, bs_params=None, face_found=True):
        if not bs_params:
            return
        if self._mapping:
            for src, addr in self._mapping.items():
                if src in bs_params:
                    self._client.send_message(addr, float(bs_params[src]))
        else:
            for name, w in bs_params.items():
                self._client.send_message(f"{self._prefix}/bs/{name}", float(w))

    def close(self):
        pass


def load_osc_mapping(path=OSC_MAPPING_FILE):
    """读 osc_mapping.json（容错：缺失/坏 JSON → 无映射，用 prefix 模式）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if k and v}
