"""
VTube Studio 桥：把放大后的 Live2D 参数喂给 VTube Studio 渲染。

路径 A（见 [[face-project-design]] / [[vts-api-reference]]）：
FaceEQ 不自己渲染直播画面，而是把放大值经 VTube Studio 公开 WebSocket API
(InjectParameterDataRequest, mode=set) 逐帧注入。set 模式会覆盖 VTS 自带的
摄像头跟踪（每秒至少喂一次即可持续接管；停喂则参数自动回退），所以
FaceEQ = "会放大的跟踪源"，主播的模型/物理/OBS 全不动。

两类注入：
  1) VTS 默认输入参数（FaceAngleX/EyeOpenLeft/MouthOpen/MouthSmile/BrowLeftY…）：
     零配置——VTS 自动把它们映射到标准模型参数。笑/惊讶完整放大。
  2) FaceEQ 自建自定义参数（faceeqEyeSmile/BrowForm/MouthFrown/BrowDown）：
     VTS 默认输入没有这些通道（眼笑/眉形/嘴角下垂/压眉），自建后由用户在模型里
     映射一次 → 补全 怒/悲/厌恶。见 docs/vts-setup.md。

设计要点：
- 同步（websocket-client），贴合 main.py 的阻塞 30fps 循环，无需 asyncio。
- 注入 fire-and-forget：每帧只 send，不等响应；_drain 丢回包/事件。
- 语义变换而非量程缩放：默认参数里同尺度的透传（VTS 自 clamp），双极→单极的
  （嘴笑、眉）用 max(0,v)。自定义参数直接给放大后的原始值（用户映射时定方向）。
"""
import json
import os
import time

import websocket  # pip install websocket-client


def _id(v):
    """同尺度透传（角度/眼开合/嘴开合/眼球：FaceEQ 与 VTS 单位一致，VTS 自行 clamp）。"""
    return v


def _pos(v):
    """双极(±1)→单极(0..1) 的正半：笑/挑眉保留，皱嘴/压眉归 0（VTS 无负向输入）。"""
    return v if v > 0 else 0.0


def _avg(a, b):
    return (a + b) / 2.0


# FaceEQ Live2D 参数 → (VTS 默认输入参数名或名列表, 值变换)。
# 名字/量程已据 VTS 实测订正。
LIVE2D_TO_VTS = {
    "ParamAngleX":     ("FaceAngleX", _id),
    "ParamAngleY":     ("FaceAngleY", _id),
    "ParamAngleZ":     ("FaceAngleZ", _id),
    "ParamEyeLOpen":   ("EyeOpenLeft", _id),
    "ParamEyeROpen":   ("EyeOpenRight", _id),
    "ParamEyeBallX":   (["EyeLeftX", "EyeRightX"], _id),   # 水平眼球 → 双眼同向
    "ParamMouthOpenY": ("MouthOpen", _id),
    "ParamMouthForm":  ("MouthSmile", _pos),               # 笑保留，皱嘴丢（皱嘴走自定义）
    "ParamBrowLY":     ("BrowLeftY", _pos),                # 挑眉保留，压眉丢（压眉走自定义）
    "ParamBrowRY":     ("BrowRightY", _pos),
    # ParamEyeLSmile/RSmile、ParamBrowLForm/RForm：VTS 无默认输入 → 走下面的自定义参数。
}

# 自建 VTS 自定义参数（VTS 默认输入没这些通道）。每条：
#   (参数名, min, max, 默认值, 说明, 从【已放大+平滑】的 params 派生值的函数)
# 参数名须字母/数字、4~32 字符（VTS 规定；不用下划线以免被判非法）。
# 值直接取放大后的 Live2D 值，用户在 VTS 映射时定方向/倍率。
CUSTOM_PARAMS = [
    ("faceeqEyeSmile", 0.0, 1.0, 0.0,
     "眼笑/眯眼强度(已放大)。映射到 ParamEyeLSmile/RSmile。",
     lambda p: _avg(p.get("ParamEyeLSmile", 0.0), p.get("ParamEyeRSmile", 0.0))),
    ("faceeqBrowForm", -1.0, 1.0, 0.0,
     "眉形/眉角(已放大,负=怒眉内聚)。映射到 ParamBrowLForm/RForm。",
     lambda p: _avg(p.get("ParamBrowLForm", 0.0), p.get("ParamBrowRForm", 0.0))),
    ("faceeqMouthFrown", 0.0, 1.0, 0.0,
     "嘴角下垂强度(已放大,悲/厌恶)。模型若有独立下垂参数则映射之。",
     lambda p: max(0.0, -(p.get("ParamMouthForm", 0.0)))),
    ("faceeqBrowDown", 0.0, 1.0, 0.0,
     "压眉强度(已放大,怒)。模型若有独立压眉参数则映射之。",
     lambda p: max(0.0, -_avg(p.get("ParamBrowLY", 0.0), p.get("ParamBrowRY", 0.0)))),
]

# 每个自定义参数「对应的模型 Live2D 参数」——capability-aware：模型一个都没有 → 不创建。
_CUSTOM_TO_LIVE2D = {
    "faceeqEyeSmile":   ["ParamEyeLSmile", "ParamEyeRSmile"],
    "faceeqBrowForm":   ["ParamBrowLForm", "ParamBrowRForm"],
    "faceeqMouthFrown": ["ParamMouthForm"],
    "faceeqBrowDown":   ["ParamBrowLY", "ParamBrowRY"],
}

DEFAULT_URL = "ws://localhost:8001"
_API = "VTubeStudioPublicAPI"
_VER = "1.0"
_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", ".vts_token")


class VTSBridge:
    """同步 WebSocket 客户端：连接 + token 鉴权 + 发现/自建参数 + 逐帧注入。

    用法：
        br = VTSBridge()
        br.start()                # connect + authenticate + discover + ensure_custom_params
        br.inject(params, True)   # 每帧
        br.close()
    """

    def __init__(self, url=DEFAULT_URL, plugin_name="FaceEQ",
                 plugin_dev="FaceEQ"):
        self._url = url
        self._plugin_name = plugin_name
        self._plugin_dev = plugin_dev
        self._ws = None
        self._req_id = 0
        self._vts_names = set()   # VTS 实际存在/可注入的参数名（默认 + 自建）
        self._last_send = 0.0

    # ---------- 底层收发 ----------
    def _next_id(self):
        self._req_id += 1
        return f"faceeq-{self._req_id}"

    def _send(self, message_type, data=None, timeout=5.0):
        """发一条请求并阻塞等其 requestID 匹配的响应（中途丢弃无关消息）。
        响应超时（None）→ raise ConnectionError（VTS 掉线检测，供 GUI worker 重连）。"""
        payload = {"apiName": _API, "apiVersion": _VER,
                   "requestID": self._next_id(), "messageType": message_type}
        if data is not None:
            payload["data"] = data
        self._ws.send(json.dumps(payload))
        r = self._recv_match(payload["requestID"], timeout)
        if r is None:
            raise ConnectionError(f"VTS 无响应（超时 {timeout}s）")
        return r

    def _recv_match(self, req_id, timeout):
        self._ws.settimeout(2)
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("requestID") == req_id:
                return msg
        return None

    # ---------- 生命周期 ----------
    def start(self):
        """connect → authenticate → discover → ensure_custom_params。一键启动。"""
        self.connect()
        self.authenticate()
        self.discover()
        self.ensure_custom_params()

    def connect(self):
        try:
            self._ws = websocket.create_connection(self._url, timeout=5)
        except Exception as e:
            raise RuntimeError(
                f"连不上 {self._url}（VTS 没开？或没勾 Allow Plugin API access？）: {e}"
            ) from e
        st = self._send("APIStateRequest")
        if not st or not st.get("data", {}).get("active"):
            raise RuntimeError(
                f"VTS API 未激活（在 VTS 设置勾 Allow Plugin API access）: {st}"
            )

    def authenticate(self):
        token = self._load_token()
        if token and self._try_auth(token):
            return
        token = self._request_token()   # VTS 弹窗，用户点 Allow（给 60s）
        if not token:
            raise RuntimeError("VTS 鉴权被拒/超时")
        self._save_token(token)
        if not self._try_auth(token):
            raise RuntimeError("VTS AuthenticationRequest 失败")

    def _try_auth(self, token):
        r = self._send("AuthenticationRequest", {
            "pluginName": self._plugin_name,
            "pluginDeveloper": self._plugin_dev,
            "authenticationToken": token,
        })
        return bool(r and r.get("data", {}).get("authenticated"))

    def _request_token(self):
        r = self._send("AuthenticationTokenRequest", {
            "pluginName": self._plugin_name,
            "pluginDeveloper": self._plugin_dev,
        }, timeout=60)
        return r.get("data", {}).get("authenticationToken") if r else None

    def _load_token(self):
        try:
            with open(_TOKEN_FILE, "r", encoding="utf-8") as fh:
                return fh.read().strip() or None
        except OSError:
            return None

    def _save_token(self, token):
        try:
            with open(_TOKEN_FILE, "w", encoding="utf-8") as fh:
                fh.write(token)
        except OSError:
            pass

    # ---------- 发现默认参数 ----------
    def discover(self):
        r = self._send("InputParameterListRequest")
        if not r:
            self._vts_names = set()
            return set()
        names = set()
        data = r.get("data", {})
        for p in data.get("defaultParameters", []) + data.get("customParameters", []):
            names.add(p["name"])
        self._vts_names = names

        want = []
        for spec in LIVE2D_TO_VTS.values():
            ns = spec[0]
            want.extend(ns if isinstance(ns, (list, tuple)) else [ns])
        want = sorted(set(want))
        print(f"[vts] VTS 可注入参数 {len(names)} 个")
        print(f"[vts]   默认映射 VTS 认: {sorted(set(want) & names)}")
        miss = sorted(set(want) - names)
        if miss:
            print(f"[vts]   默认映射 VTS 不认: {miss}")
        return names

    def discover_model_params(self):
        """Live2DParameterListRequest → 当前模型的 Live2D 参数名集合。"""
        r = self._send("Live2DParameterListRequest")
        if not r:
            return set()
        return {p["name"] for p in r.get("data", {}).get("parameters", [])}

    # ---------- 自建自定义参数（补全怒/悲/厌恶）----------
    def ensure_custom_params(self):
        """创建 FaceEQ 自定义参数（capability-aware：模型无对应 Live2D 参数的跳过）。"""
        model_params = self.discover_model_params()
        created, skipped = [], []
        for name, lo, hi, dflt, expl, _ in CUSTOM_PARAMS:
            targets = _CUSTOM_TO_LIVE2D.get(name, [])
            if targets and not any(t in model_params for t in targets):
                skipped.append(name)
                continue
            r = self._send("ParameterCreationRequest", {
                "parameterName": name,
                "explanation": expl,
                "min": lo, "max": hi, "defaultValue": dflt,
            })
            if r and r.get("messageType") != "APIError":
                self._vts_names.add(name)
                created.append(name)
            else:
                print(f"[vts] 自建参数 {name} 失败: {r.get('data') if r else '无响应'}")
        if skipped:
            print(f"[vts] 跳过（模型无对应 Live2D 参数）: {skipped}")
        print(f"[vts] 自定义参数就绪: {created}")
        if created:
            print("[vts]   首次需在 VTS 模型参数映射里接到对应模型参数（见 docs/vts-setup.md）")

    # ---------- 注入 ----------
    def inject(self, live2d_params: dict, face_found: bool = True):
        """把 FaceEQ 的 Live2D 参数（已放大/平滑）注入 VTS。每帧调用。

        先注入 VTS 默认输入参数（语义变换），再注入自建自定义参数（派生值）。
        仅注入 VTS 实际存在的；fire-and-forget。
        """
        if self._ws is None:
            return
        vals = []
        # 默认输入参数
        for l2d, v in live2d_params.items():
            spec = LIVE2D_TO_VTS.get(l2d)
            if not spec:
                continue
            names, fn = spec
            if isinstance(names, str):
                names = [names]
            tv = float(fn(v))
            for nm in names:
                if nm in self._vts_names:
                    vals.append({"id": nm, "value": tv})
        # 自定义参数
        for name, lo, hi, dflt, expl, derive in CUSTOM_PARAMS:
            if name in self._vts_names:
                vals.append({"id": name, "value": float(derive(live2d_params))})
        if not vals:
            return
        msg = {"apiName": _API, "apiVersion": _VER,
               "requestID": self._next_id(),
               "messageType": "InjectParameterDataRequest",
               "data": {"faceFound": bool(face_found), "mode": "set",
                        "parameterValues": vals}}
        try:
            self._ws.send(json.dumps(msg))
            self._last_send = time.time()
            self._drain()   # 丢回包/事件，防止缓冲堆积
        except Exception as e:
            print(f"[vts] inject 失败: {e}")

    def _drain(self):
        self._ws.settimeout(0)
        try:
            while True:
                self._ws.recv()
        except Exception:
            pass
        self._ws.settimeout(2)

    def keepalive_ok(self) -> bool:
        """最近 1s 内是否喂过数据（VTS 要求≥1Hz 否则丢参数）。"""
        return (time.time() - self._last_send) < 1.0

    def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
