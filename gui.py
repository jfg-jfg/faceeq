"""FaceEQ GUI 控制面板（PySide6 + QSS，VTS 风格深色蓝高亮）。

用户面入口：滑块实时调每情绪增强/抑制 + 全局 gain + 平滑，按钮触发校准/开始/停止。
开始前提示关掉 VTS 摄像头让 FaceEQ 独占（避免 1fps 冲突）。核心引擎不变，GUI 是包装层。
CLI main.py 保留给自动化/调试。

跑：
    PYTHONUTF8=1 .venv/Scripts/python.exe gui.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace as NS

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QScrollArea,
                               QSlider, QTableWidget, QVBoxLayout, QWidget)

from faceeq import emotions, engine, profile as profile_mod
from faceeq.capture import PHONE_PORT, list_sources, open_source
from faceeq.mapping import base_map
from faceeq.smooth import Smoother
from faceeq.vts_bridge import VTSBridge

DEFAULT_PROFILE = os.path.join("profiles", "calibration.json")
PRESETS_DIR = "presets"
CUSTOM_EXPRS_FILE = "custom_expressions.json"   # 自定义复合表情定义（随仓库预置示例）


# —— 预设 I/O ——
def _sanitize_preset_name(name):
    """预设名消毒：过滤路径非法字符 + Windows 保留名 + 限长 64。
    预设文件是可分享物，消毒放 I/O 层统一把关（防穿越/非法名），不只存档入口。"""
    name = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip()[:64]
    if name and name.upper() in {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)}:
        name = "_" + name
    return name


def list_presets():
    if not os.path.isdir(PRESETS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(PRESETS_DIR) if f.endswith(".json"))


def save_preset(name, gain, emotion_gains, smooth, shaping=None, custom_exprs=None):
    name = _sanitize_preset_name(name)
    if not name:
        raise ValueError("预设名无效")
    os.makedirs(PRESETS_DIR, exist_ok=True)
    data = {"name": name, "global_gain": gain,
            "emotion_gains": emotion_gains, "smooth": smooth}
    if shaping is not None:
        data["shaping"] = emotions.shaping_to_dict(shaping)   # 预设 v2：含塑造配置
    if custom_exprs:
        data["custom_expressions"] = custom_exprs             # 预设 v2：含自定义表情定义
    with open(os.path.join(PRESETS_DIR, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_preset(name):
    name = _sanitize_preset_name(name)
    with open(os.path.join(PRESETS_DIR, name + ".json"), "r", encoding="utf-8") as f:
        return json.load(f)


def delete_preset(name):
    name = _sanitize_preset_name(name)
    os.remove(os.path.join(PRESETS_DIR, name + ".json"))


# —— 自定义复合表情 I/O ——
def sanitize_custom_exprs(raw):
    """{名字: {情绪: 权重}} 消毒：名字过预设名消毒、情绪限定 5 基础、权重钳 [-1,1]。"""
    out = {}
    for name, w in (raw or {}).items():
        nm = _sanitize_preset_name(name)
        if not nm or not isinstance(w, dict):
            continue
        clean = {}
        for e, v in w.items():
            if e in emotions.EMOTIONS:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv:
                    clean[e] = max(-1.0, min(1.0, fv))
        if clean:
            out[nm] = clean
    return out


def load_custom_exprs():
    """读自定义表情定义文件（容错：文件缺失/坏 JSON → 空定义）。"""
    try:
        with open(CUSTOM_EXPRS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return sanitize_custom_exprs(raw)


def save_custom_exprs(defs):
    with open(CUSTOM_EXPRS_FILE, "w", encoding="utf-8") as f:
        json.dump(defs, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _best_local_ip():
    """尽力取本机局域网 IP（手机 app 里要填的地址）；取不到给占位提示。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))   # UDP connect 不发包，只为定源地址
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "192.168.x.x（cmd 里运行 ipconfig 看 IPv4 地址）"

# —— VTS 风格 QSS（深色 / 圆角 / 蓝高亮）——
QSS = """
* { font-family: 'Segoe UI','Microsoft YaHei',sans-serif; font-size: 13px; color: #e0e0e0; }
QMainWindow, QWidget#central { background: #252a35; }
QScrollArea { background: #252a35; border: none; }
QScrollArea > QWidget > QWidget { background: #252a35; }
QGroupBox { border: 1px solid #3a4050; border-radius: 8px; margin-top: 16px; padding: 14px 10px 10px 10px; background: #2d3340; }
QGroupBox::title { color: #8a93a4; subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QLabel { background: transparent; color: #f0f0f0; }
QLabel#title { font-size: 22px; font-weight: 700; color: #ffffff; }
QLabel#subtitle { color: #a0a8b8; }
QLabel#val { color: #5ab0ff; font-weight: 600; }
QPushButton { background: #4a9eff; color: #ffffff; border: none; border-radius: 6px; padding: 9px 22px; font-weight: 600; }
QPushButton:hover { background: #62acff; }
QPushButton:pressed { background: #3a8eef; }
QPushButton:disabled { background: #3a4050; color: #6a7384; }
QPushButton#stopBtn { background: #e0566e; }
QPushButton#stopBtn:hover { background: #f0667e; }
QPushButton#stopBtn:disabled { background: #3a4050; color: #6a7384; }
QSlider::groove:horizontal { height: 6px; background: #3a4050; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #4a9eff; border-radius: 3px; }
QSlider::add-page:horizontal { background: #3a4050; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; background: #4a9eff; border-radius: 8px; }
QSlider::handle:horizontal:hover { background: #62acff; }
QComboBox { background: #3a4050; border: 1px solid #4a5060; border-radius: 4px; padding: 4px 8px; color: #f0f0f0; }
QComboBox:hover { border-color: #4a9eff; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background: #2d3340; color: #f0f0f0; selection-background-color: #4a9eff; outline: none; }
QStatusBar { background: #1e232e; }
QStatusBar QLabel { color: #a0a8b8; }
QMessageBox { background: #2d3340; }
QMessageBox QLabel { color: #f0f0f0; font-size: 14px; }
QMessageBox QPushButton { min-width: 64px; }
QInputDialog { background: #2d3340; }
QInputDialog QLabel { color: #f0f0f0; font-size: 14px; }
"""


class FloatSlider(QWidget):
    """浮点滑块行：[名] [────●────] [值]。整数 QSlider + scale 模拟浮点。"""
    valueChanged = Signal(float)

    def __init__(self, name, lo, hi, step, init, fmt="{:.2f}", parent=None):
        super().__init__(parent)
        self._scale = round(1.0 / step)
        self._fmt = fmt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.name_lbl = QLabel(name)
        self.name_lbl.setMinimumWidth(86)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(int(round(lo * self._scale)))
        self.slider.setMaximum(int(round(hi * self._scale)))
        self.slider.setValue(int(round(init * self._scale)))
        self.val_lbl = QLabel(self._fmt.format(self.value()))
        self.val_lbl.setObjectName("val")
        self.val_lbl.setMinimumWidth(48)
        self.val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.name_lbl)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.val_lbl)
        self.slider.valueChanged.connect(self._on_change)

    def _on_change(self, _):
        v = self.value()
        self.val_lbl.setText(self._fmt.format(v))
        self.valueChanged.emit(v)

    def value(self):
        return self.slider.value() / self._scale

    def setValue(self, v):
        self.slider.setValue(int(round(v * self._scale)))


class Params:
    """GUI 写、worker 读的共享参数。threading.Lock 守护（QThread 跑在真 Python 线程）。"""
    def __init__(self):
        self._lock = threading.Lock()
        self.global_gain = 1.4
        self.emotion_gains = {e: 0.0 for e in emotions.EMOTIONS}
        self.smooth = 0.4
        self.calib = None
        self.source = 0
        self.shaping = emotions.DEFAULT_SHAPING.copy()   # 塑造配置（boost 矩阵+耦合）
        self.test = None                                  # (情绪, 强度, 到期时刻) | None
        self.custom_exprs = {}                            # {名字: {情绪: 权重}}
        self.custom_act = {}                              # {名字: 激活度 0..1}

    def snapshot(self):
        with self._lock:
            return (self.global_gain, dict(self.emotion_gains), self.smooth,
                    self.calib, self.shaping, self.test,
                    dict(self.custom_exprs), dict(self.custom_act))

    def set_gain(self, v):
        with self._lock:
            self.global_gain = v

    def set_emotion(self, e, v):
        with self._lock:
            self.emotion_gains[e] = v

    def set_smooth(self, v):
        with self._lock:
            self.smooth = v

    def set_calib(self, c):
        with self._lock:
            self.calib = c

    def set_shaping(self, s):
        with self._lock:
            self.shaping = s

    def set_custom_exprs(self, defs):
        with self._lock:
            self.custom_exprs = dict(defs)
            # 定义被删的激活度一并清掉
            self.custom_act = {k: v for k, v in self.custom_act.items() if k in defs}

    def set_custom_act(self, name, v):
        with self._lock:
            self.custom_act[name] = v

    def set_test(self, e, strength, dur=1.5):
        with self._lock:
            self.test = (e, strength, time.time() + dur)

    def clear_test(self):
        with self._lock:
            self.test = None


class FaceEQWorker(QObject):
    """跑在 QThread，移植 main.py 主循环：capture→signals→amplify→Smoother→VTS.inject。
    每帧从 Params 读滑块值（实时生效）。"""
    status = Signal(str)
    dominant = Signal(str)
    fps = Signal(int)
    face_found = Signal(bool)
    error = Signal(str)
    finished = Signal()

    def __init__(self, params):
        super().__init__()
        self._params = params
        self._running = False

    def stop(self):
        self._running = False

    @Slot()
    def run(self):
        cap = None
        bridge = None
        try:
            source = self._params.source
            self.status.emit("等待手机 UDP 数据…" if source == "phone" else "正在打开摄像头…")
            cap = open_source(source)
            is_phone = (source == "phone")
            phone_ok = False
            self.status.emit("正在连接 VTS…")
            bridge = VTSBridge()
            bridge.start()                       # connect + auth + discover + ensure_custom_params
            _, _, smooth, _, _, _, _, _ = self._params.snapshot()
            smoother = Smoother(smooth)
            self.status.emit("运行中（注入 VTS）")
            last_params = {}
            frames = 0
            timer = time.time()
            last_dom = ""
            self._running = True
            while self._running:
                f = cap.read()
                gain, eg, smooth, calib, shaping, test, ce_defs, ce_act = self._params.snapshot()
                te = None
                if test:                          # 「试表情」到期清理
                    t_name, t_strength, t_expiry = test
                    if time.time() < t_expiry:
                        te = (t_name, t_strength)
                    else:
                        self._params.clear_test()
                params, dom_now, ff = engine.process_frame(
                    f, gain, eg, calib, shaping=shaping, test_emotion=te,
                    custom_exprs=ce_defs, custom_act=ce_act)
                if params:
                    last_params = params
                smoother.set_strength(smooth)        # 实时改平滑
                if last_params:
                    try:
                        bridge.inject(smoother.step(last_params), face_found=ff)
                    except Exception:
                        # VTS 掉线 → 重连（指数退避，3 次）
                        self.status.emit("VTS 断开，重连中…")
                        reconnected = False
                        for attempt in range(3):
                            time.sleep(2 ** attempt)  # 1s, 2s, 4s
                            try:
                                try:
                                    bridge.close()
                                except Exception:
                                    pass
                                bridge = VTSBridge()
                                bridge.start()
                                reconnected = True
                                self.status.emit("VTS 已重连。")
                                break
                            except Exception:
                                continue
                        if not reconnected:
                            raise RuntimeError("VTS 重连失败（重试 3 次后放弃）。")
                frames += 1
                now = time.time()
                if now - timer >= 1.0:
                    self.fps.emit(frames)
                    if ff and dom_now and dom_now != last_dom:
                        last_dom = dom_now
                        self.dominant.emit(dom_now)
                    if is_phone:   # 手机源状态提示（只在状态翻转时报）
                        stale = cap.is_stale()
                        if not stale and not phone_ok:
                            phone_ok = True
                            self.status.emit("运行中（注入 VTS，手机源）")
                        elif stale and phone_ok:
                            phone_ok = False
                            self.status.emit("手机数据断流（检查 app 发送与防火墙）")
                    frames = 0
                    timer = now
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
        finally:
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
            if bridge:
                try:
                    bridge.close()
                except Exception:
                    pass
            self._running = False
            self.finished.emit()


class CalibrateRunner(QObject):
    """在 QThread 里跑校准子进程，不阻塞 GUI。完成后 emit finished(ok)——ok=子进程正常退出。"""
    finished = Signal(bool)

    def __init__(self, source):
        super().__init__()
        self._source = source

    @Slot()
    def run(self):
        calibrate_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "probes", "calibrate.py")
        rc = subprocess.run([sys.executable, calibrate_path, "--source", str(self._source)],
                            check=False).returncode
        self.finished.emit(rc == 0)


class ShapingDialog(QDialog):
    """高级塑造编辑器：参数×情绪 boost 矩阵 + 耦合开关/强度 + 试表情 + 恢复默认。

    非模态——边调边在 VTS 里看效果。任何修改即时写入 Params（worker 逐帧读快照，
    不用重启）。「试表情」让引擎用参考底 pose + 合成情绪值跑 1.5 秒，不照镜子也能
    预览塑造效果。who-eats-global-gain 是结构项，不在此面板暴露。
    """

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.setWindowTitle("高级塑造 · 情绪→参数增强 / 耦合")
        self.setMinimumWidth(580)
        self._params = params
        self._base_couplings = [tuple(c) for c in emotions.DEFAULT_SHAPING.couplings]
        _, _, _, _, cur, _, _, _ = params.snapshot()
        # 当前塑造里不在默认集的耦合（如手工 JSON 加的）原样保留，不在本面板编辑
        self._extra_couplings = [tuple(c) for c in cur.couplings
                                 if not any(c[:3] == b[:3] for b in self._base_couplings)]

        root = QVBoxLayout(self)

        # —— boost 矩阵 ——
        gb = QGroupBox("情绪→参数 附加放大系数（0=不塑造该组合；正=增强；负=反向压）")
        QVBoxLayout(gb)
        params_order = list(emotions.DEFAULT_SHAPING.boosts.keys())
        self._table = QTableWidget(len(params_order), len(emotions.EMOTIONS))
        self._table.setHorizontalHeaderLabels(emotions.EMOTIONS)
        self._table.setVerticalHeaderLabels([p.replace("Param", "") for p in params_order])
        self._cells = {}
        for r, p in enumerate(params_order):
            for c, e in enumerate(emotions.EMOTIONS):
                sp = QDoubleSpinBox()
                sp.setRange(-2.0, 2.0)
                sp.setSingleStep(0.05)
                sp.setDecimals(2)
                sp.setValue(cur.boosts.get(p, {}).get(e, 0.0))
                sp.valueChanged.connect(self._apply)
                self._table.setCellWidget(r, c, sp)
                self._cells[(p, e)] = sp
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        gb.layout().addWidget(self._table)
        root.addWidget(gb)

        # —— 耦合 ——
        gc = QGroupBox("跨参数耦合（门情绪开火时把目标参数抬向源；只抬不压）")
        QVBoxLayout(gc)
        self._coup_checks, self._coup_spins = [], []
        for tgt, src, gate, k_def, _mb in self._base_couplings:
            row = QHBoxLayout()
            cb = QCheckBox(f"{tgt.replace('Param', '')} ← {src.replace('Param', '')}（门={gate}）")
            cur_k = next((c[3] for c in cur.couplings
                          if c[0] == tgt and c[1] == src and c[2] == gate), None)
            cb.setChecked(cur_k is not None)
            cb.stateChanged.connect(self._apply)
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 2.0)
            sp.setSingleStep(0.05)
            sp.setDecimals(2)
            sp.setValue(cur_k if cur_k is not None else k_def)
            sp.valueChanged.connect(self._apply)
            row.addWidget(cb, 1)
            row.addWidget(QLabel("强度"))
            row.addWidget(sp)
            gc.layout().addLayout(row)
            self._coup_checks.append(cb)
            self._coup_spins.append(sp)
        if self._extra_couplings:
            gc.layout().addWidget(QLabel(f"另有 {len(self._extra_couplings)} 条自定义耦合（JSON 配置）原样保留。"))
        root.addWidget(gc)

        # —— 试表情 ——
        gt = QGroupBox("试表情（注入合成情绪值 1.5 秒，在 VTS 里看塑造效果）")
        QHBoxLayout(gt)
        for e in emotions.EMOTIONS:
            b = QPushButton(e)
            b.clicked.connect(lambda _, ee=e: self._params.set_test(ee, 0.85, 1.5))
            gt.layout().addWidget(b)
        root.addWidget(gt)

        # —— 底部按钮 ——
        h = QHBoxLayout()
        btn_reset = QPushButton("↺ 恢复默认")
        btn_reset.clicked.connect(self._reset)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        h.addWidget(btn_reset)
        h.addStretch(1)
        h.addWidget(btn_close)
        root.addLayout(h)

    # —— 收集/应用 ——
    def _collect(self):
        boosts = {}
        for (p, e), sp in self._cells.items():
            if abs(sp.value()) > 1e-9:
                boosts.setdefault(p, {})[e] = sp.value()
        couplings = []
        for i, (tgt, src, gate, _k, mb) in enumerate(self._base_couplings):
            if self._coup_checks[i].isChecked():
                couplings.append((tgt, src, gate, self._coup_spins[i].value(), mb))
        couplings.extend(self._extra_couplings)
        return emotions.Shaping(boosts=boosts, couplings=couplings)

    def _apply(self, *_):
        self._params.set_shaping(self._collect())

    def _reset(self):
        d = emotions.DEFAULT_SHAPING
        for (p, e), sp in self._cells.items():
            sp.blockSignals(True)
            sp.setValue(d.boosts.get(p, {}).get(e, 0.0))
            sp.blockSignals(False)
        for i, (_, _, _, k, _) in enumerate(self._base_couplings):
            for w in (self._coup_checks[i], self._coup_spins[i]):
                w.blockSignals(True)
            self._coup_checks[i].setChecked(True)
            self._coup_spins[i].setValue(k)
            for w in (self._coup_checks[i], self._coup_spins[i]):
                w.blockSignals(False)
        self._apply()

    def refresh_from(self, shaping):
        """预设加载等场景：把外部 Shaping 同步到控件（不触发 _apply）。"""
        for (p, e), sp in self._cells.items():
            sp.blockSignals(True)
            sp.setValue(shaping.boosts.get(p, {}).get(e, 0.0))
            sp.blockSignals(False)
        for i, (tgt, src, gate, k_def, _mb) in enumerate(self._base_couplings):
            cur_k = next((c[3] for c in shaping.couplings
                          if c[0] == tgt and c[1] == src and c[2] == gate), None)
            self._coup_checks[i].blockSignals(True)
            self._coup_checks[i].setChecked(cur_k is not None)
            self._coup_checks[i].blockSignals(False)
            if cur_k is not None:
                self._coup_spins[i].blockSignals(True)
                self._coup_spins[i].setValue(cur_k)
                self._coup_spins[i].blockSignals(False)


class CustomExprDialog(QDialog):
    """新建/编辑自定义复合表情：名字 + 5 基础情绪权重（-1..1，负=压该情绪）。

    例：「害羞」= happy 0.35 + surprised 0.30；「面无表情」= happy -0.5 + angry -0.5。
    """

    def __init__(self, parent=None, name="", weights=None):
        super().__init__(parent)
        self.setWindowTitle("自定义表情定义")
        self.setMinimumWidth(320)
        self._name_edit = QLineEdit(name)
        form = QFormLayout()
        form.addRow("名字", self._name_edit)
        self._spins = {}
        for e in emotions.EMOTIONS:
            sp = QDoubleSpinBox()
            sp.setRange(-1.0, 1.0)
            sp.setSingleStep(0.05)
            sp.setDecimals(2)
            sp.setValue(float((weights or {}).get(e, 0.0)))
            self._spins[e] = sp
            form.addRow(e, sp)
        h = QHBoxLayout()
        ok = QPushButton("确定")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        h.addStretch(1)
        h.addWidget(ok)
        h.addWidget(cancel)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(h)

    def result_value(self):
        """(消毒后的名字, {情绪: 权重})；名字空/全零权重 → 名字空串表示无效。"""
        name = _sanitize_preset_name(self._name_edit.text())
        weights = {e: sp.value() for e, sp in self._spins.items() if abs(sp.value()) > 1e-9}
        if not weights:
            return "", {}
        return name, weights


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceEQ")
        # 内容套 QScrollArea：小屏/内容增长时可滚动，而不是把组件压没
        self.setMinimumSize(420, 520)
        self.resize(470, 800)

        self.params = Params()
        self.thread = None
        self.worker = None
        self._calib_thread = None
        self._shape_dlg = None
        self._running = False
        self._had_error = False

        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(8)

        title = QLabel("FaceEQ")
        title.setObjectName("title")
        sub = QLabel("情绪 EQ 过滤器 · VTS 插件")
        sub.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(sub)

        # 摄像头选择
        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel("摄像头:"))
        self.cam_combo = QComboBox()
        for src in list_sources():
            self.cam_combo.addItem(f"Camera {src}", src)
        self.cam_combo.addItem("📱 手机 UDP (iFacialMocap/MeowFace)", "phone")
        self.cam_combo.currentIndexChanged.connect(
            lambda idx: setattr(self.params, "source", self.cam_combo.itemData(idx)))
        cam_row.addWidget(self.cam_combo, 1)
        root.addLayout(cam_row)

        # 增益
        g_gain = QGroupBox("增益 Gain")
        QVBoxLayout(g_gain)
        self.gain_slider = FloatSlider("全局 gain", 0.5, 3.0, 0.01, self.params.global_gain, "{:.2f}")
        g_gain.layout().addWidget(self.gain_slider)
        root.addWidget(g_gain)

        # 情绪（init 0）
        g_emo = QGroupBox("情绪 抑制/增强（-1..1，0=不塑造）")
        QVBoxLayout(g_emo)
        self.emo_sliders = {}
        for e in emotions.EMOTIONS:
            fs = FloatSlider(e, -1.0, 1.0, 0.01, 0.0, "{:+.2f}")
            g_emo.layout().addWidget(fs)
            self.emo_sliders[e] = fs
        root.addWidget(g_emo)

        # 平滑
        g_sm = QGroupBox("平滑 Smoothing")
        QVBoxLayout(g_sm)
        self.smooth_slider = FloatSlider("smooth", 0.0, 1.0, 0.01, self.params.smooth, "{:.2f}")
        g_sm.layout().addWidget(self.smooth_slider)
        root.addWidget(g_sm)

        # 按钮
        btns = QHBoxLayout()
        self.start_btn = QPushButton("▶  开始")
        self.stop_btn = QPushButton("⏹  停止")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.calib_btn = QPushButton("●  校准")
        self.shape_btn = QPushButton("🎛 高级塑造")
        btns.addWidget(self.start_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.calib_btn)
        btns.addWidget(self.shape_btn)
        root.addLayout(btns)

        # 预设
        g_pre = QGroupBox("预设 Preset（存/加载 EQ 快照）")
        QVBoxLayout(g_pre)
        pre_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.blockSignals(True)
        self.preset_combo.addItem("（选择预设加载）")
        for n in list_presets():
            self.preset_combo.addItem(n)
        self.preset_combo.blockSignals(False)
        pre_row.addWidget(QLabel("预设:"))
        pre_row.addWidget(self.preset_combo, 1)
        btn_save_pre = QPushButton("💾 存")
        btn_save_pre.clicked.connect(self._save_preset)
        btn_del_pre = QPushButton("🗑 删")
        btn_del_pre.clicked.connect(self._delete_preset)
        pre_row.addWidget(btn_save_pre)
        pre_row.addWidget(btn_del_pre)
        g_pre.layout().addLayout(pre_row)
        root.addWidget(g_pre)
        self.preset_combo.currentIndexChanged.connect(self._load_preset_by_index)

        # 自定义表情
        g_ce = QGroupBox("自定义表情（基础情绪加权组合，拖滑块激活 0..1）")
        QVBoxLayout(g_ce)
        self._ce_box = QVBoxLayout()
        g_ce.layout().addLayout(self._ce_box)
        ce_row = QHBoxLayout()
        btn_ce_new = QPushButton("＋ 新建")
        btn_ce_new.clicked.connect(self._ce_new)
        ce_row.addWidget(btn_ce_new)
        ce_row.addStretch(1)
        g_ce.layout().addLayout(ce_row)
        root.addWidget(g_ce)

        root.addStretch()

        # 状态栏
        self._profile_lbl = QLabel("profile: 未加载")
        self._fps_lbl = QLabel("FPS: -")
        self._dom_lbl = QLabel("[]")
        sb = self.statusBar()
        sb.addPermanentWidget(self._dom_lbl)
        sb.addPermanentWidget(self._fps_lbl)
        sb.addPermanentWidget(self._profile_lbl)
        sb.showMessage("就绪。点「开始」注入 VTS（会先提示关掉 VTS 摄像头）。")

        self._load_profile(DEFAULT_PROFILE)

        # 自定义表情：启动时载入定义文件并建行
        self._ce_rows = {}
        self.params.set_custom_exprs(load_custom_exprs())
        self._rebuild_ce_rows()

        # 滑块 → Params（实时）
        self.gain_slider.valueChanged.connect(lambda v: self.params.set_gain(v))
        for e, fs in self.emo_sliders.items():
            fs.valueChanged.connect(lambda v, ee=e: self.params.set_emotion(ee, v))
        self.smooth_slider.valueChanged.connect(lambda v: self.params.set_smooth(v))

        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.calib_btn.clicked.connect(self._on_calibrate)
        self.shape_btn.clicked.connect(self._open_shaping)

        # 滚动包装（放在内容构建完之后）：窗口不够高时滚动，不压扁组件
        scroll = QScrollArea()
        scroll.setWidget(central)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setCentralWidget(scroll)

    # —— 高级塑造 ——
    def _current_shaping(self):
        return self.params.snapshot()[4]

    def _open_shaping(self):
        """非模态打开塑造编辑器；重复点击 = 提到前台并同步当前值。"""
        if self._shape_dlg is None:
            self._shape_dlg = ShapingDialog(self.params, self)
        self._shape_dlg.refresh_from(self._current_shaping())
        self._shape_dlg.show()
        self._shape_dlg.raise_()
        self._shape_dlg.activateWindow()

    # —— 自定义复合表情 ——
    def _rebuild_ce_rows(self):
        """按当前定义重建自定义表情行（滑块 0..1 + 编辑/删除）。"""
        while self._ce_box.count():
            item = self._ce_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._ce_rows = {}
        defs, act = self.params.snapshot()[6], self.params.snapshot()[7]
        for name in sorted(defs):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            sl = FloatSlider(name, 0.0, 1.0, 0.01, act.get(name, 0.0))
            sl.valueChanged.connect(lambda v, nn=name: self.params.set_custom_act(nn, v))
            btn_edit = QPushButton("✎")
            btn_edit.setFixedWidth(32)
            btn_edit.clicked.connect(lambda _, nn=name: self._ce_edit(nn))
            btn_del = QPushButton("🗑")
            btn_del.setFixedWidth(32)
            btn_del.clicked.connect(lambda _, nn=name: self._ce_delete(nn))
            row.addWidget(sl, 1)
            row.addWidget(btn_edit)
            row.addWidget(btn_del)
            wrap = QWidget()
            wrap.setLayout(row)
            self._ce_box.addWidget(wrap)
            self._ce_rows[name] = wrap

    def _apply_ce_defs(self, defs):
        self.params.set_custom_exprs(defs)
        save_custom_exprs(defs)
        self._rebuild_ce_rows()

    def _ce_new(self):
        dlg = CustomExprDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        name, weights = dlg.result_value()
        if not name:
            self.statusBar().showMessage("自定义表情需要名字和至少一个非零权重。")
            return
        defs = self.params.snapshot()[6]
        if name in defs:
            QMessageBox.information(self, "已存在", f"「{name}」已存在，请直接编辑它。")
            return
        defs[name] = weights
        self._apply_ce_defs(defs)
        self.statusBar().showMessage(f"自定义表情「{name}」已创建。")

    def _ce_edit(self, name):
        defs = self.params.snapshot()[6]
        dlg = CustomExprDialog(self, name=name, weights=defs.get(name, {}))
        if dlg.exec() != QDialog.Accepted:
            return
        new_name, weights = dlg.result_value()
        if not new_name:
            self.statusBar().showMessage("修改无效：需要至少一个非零权重。")
            return
        defs.pop(name, None)
        defs[new_name] = weights
        self._apply_ce_defs(defs)
        self.statusBar().showMessage(f"自定义表情「{new_name}」已保存。")

    def _ce_delete(self, name):
        if QMessageBox.question(self, "删自定义表情", f"删除「{name}」？") != QMessageBox.StandardButton.Yes:
            return
        defs = self.params.snapshot()[6]
        defs.pop(name, None)
        self._apply_ce_defs(defs)
        self.statusBar().showMessage(f"自定义表情「{name}」已删除。")

    # —— profile ——
    def _load_profile(self, path):
        """加载 profile 到 Params。返回是否成功（供校准完成后的提示区分成败）。"""
        try:
            prof = profile_mod.load_profile(path)
            cfg = profile_mod.resolve(
                NS(gain=None, smooth=None, **{e: None for e in emotions.EMOTIONS}), prof)
            self.params.set_calib(cfg.calib)
            self._profile_lbl.setText(f"profile: {path}")
            return True
        except Exception:
            self._profile_lbl.setText("profile: 无/失败")
            self.params.set_calib(None)
            return False

    # —— 开始 / 停止 ——
    def _on_start(self):
        if self._running:
            return
        dlg = QMessageBox(self)
        dlg.setWindowTitle("启动前确认")
        if self.params.source == "phone":
            dlg.setText("手机面捕模式：手机 app（iFacialMocap / MeowFace）里填\n\n"
                        f"IP：{_best_local_ip()}\n端口：{PHONE_PORT}\n\n"
                        "手机与电脑同一 WiFi 后开始发送；首次可能弹 Windows 防火墙提示，请放行。\n"
                        "VTS 摄像头跟踪保持关闭（FaceEQ 注入会覆盖它）。\n\n准备好后点「开始」。")
        else:
            dlg.setText("请先在 VTube Studio 把【摄像头跟踪关掉】(Camera → None/Off)，让 FaceEQ 独占摄像头。\n\n关好后点「开始」。")
        dlg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        dlg.setDefaultButton(QMessageBox.Ok)
        if dlg.exec() != QMessageBox.Ok:
            return
        self._launch_worker()

    def _launch_worker(self):
        # 清理上一轮线程/worker（防累积）
        if self.worker:
            self.worker.deleteLater()
        if self.thread:
            self.thread.quit()
            self.thread.wait(2000)
        self.thread = QThread()
        self.worker = FaceEQWorker(self.params)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.dominant.connect(lambda d: self._dom_lbl.setText(f"[{d}]"))
        self.worker.fps.connect(lambda n: self._fps_lbl.setText(f"FPS: {n}"))
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self._on_finished)
        self._running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.statusBar().showMessage("启动中…")
        self.thread.start()

    def _on_stop(self):
        if self.worker:
            self.worker.stop()
        self.statusBar().showMessage("正在停止…")

    def _on_error(self, msg):
        self._had_error = True
        self.statusBar().showMessage(f"错误：{msg}")

    def _on_finished(self):
        self._running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if not self._had_error:
            self.statusBar().showMessage("已停止。")
        self._had_error = False

    def _on_calibrate(self):
        """启动校正向导（QThread 里 subprocess，不阻塞 GUI），完成后重载 profile。"""
        # 清理上一轮校准线程
        if hasattr(self, "_calib_runner") and self._calib_runner:
            self._calib_runner.deleteLater()
        if hasattr(self, "_calib_thread") and self._calib_thread:
            self._calib_thread.quit()
            self._calib_thread.wait(2000)
        if self._running:
            self._on_stop()
            if self.thread:
                self.thread.wait(3000)
        # 提示：校准即将打开摄像头画面
        cam_dlg = QMessageBox(self)
        cam_dlg.setWindowTitle("校准即将开始")
        cam_dlg.setText("校准将打开摄像头画面（约 2 分钟）。\n请对着摄像头做 11 个表情（中英文提示 + 实时值）。\n\n准备好后点「开始校准」。")
        cam_dlg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if cam_dlg.exec() != QMessageBox.Ok:
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.calib_btn.setEnabled(False)
        self.statusBar().showMessage("校准中…（照右侧中英文提示做 11 个表情，GUI 保持响应）")
        self._calib_thread = QThread()
        self._calib_runner = CalibrateRunner(self.params.source)
        self._calib_runner.moveToThread(self._calib_thread)
        self._calib_thread.started.connect(self._calib_runner.run)
        self._calib_runner.finished.connect(self._on_calibrate_done)
        self._calib_runner.finished.connect(self._calib_thread.quit)
        self._calib_thread.start()

    def _on_calibrate_done(self, ok):
        """校准子进程结束（QThread 信号回来）→ 重载 profile + 恢复按钮 + 按结果提示。"""
        loaded = self._load_profile(DEFAULT_PROFILE)
        self.start_btn.setEnabled(True)
        self.calib_btn.setEnabled(True)
        if not ok:
            self.statusBar().showMessage("校准程序异常退出（崩溃，详见其控制台输出）。")
        elif loaded:
            self.statusBar().showMessage("校准完成，profile 已重载。点「开始」继续。")
        else:
            self.statusBar().showMessage("校准结束，但没有生成有效 profile（未采样中性脸？）。")

    # —— 预设 ——
    def _refresh_presets(self):
        self.preset_combo.blockSignals(True)
        cur = self.preset_combo.currentText()
        self.preset_combo.clear()
        self.preset_combo.addItem("（选择预设加载）")
        for n in list_presets():
            self.preset_combo.addItem(n)
        # 尝试恢复选中
        idx = self.preset_combo.findText(cur)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.blockSignals(False)

    def _save_preset(self):
        idx = self.preset_combo.currentIndex()
        cur_name = self.preset_combo.itemText(idx) if idx > 0 else None
        if cur_name:
            # 有选中的预设 → 问覆盖还是新建
            reply = QMessageBox.question(
                self, "存预设",
                f"覆盖预设「{cur_name}」？\n（Yes=覆盖 | No=另存为新预设 | Cancel=不存）")
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                name = cur_name
            else:
                name, ok = QInputDialog.getText(self, "另存为新预设", "新预设名称：")
                if not ok or not name.strip():
                    return
                name = name.strip()
        else:
            # 没选中预设 → 直接问新名
            name, ok = QInputDialog.getText(self, "存预设", "预设名称：")
            if not ok or not name.strip():
                return
            name = name.strip()
        # 消毒在 _sanitize_preset_name（I/O 层）统一做
        name = _sanitize_preset_name(name.strip())
        if not name:
            self.statusBar().showMessage("预设名无效。")
            return
        save_preset(name, self.gain_slider.value(),
                    {e: fs.value() for e, fs in self.emo_sliders.items()},
                    self.smooth_slider.value(),
                    self._current_shaping(),
                    self.params.snapshot()[6])
        self._refresh_presets()
        self.preset_combo.setCurrentText(name)
        self.statusBar().showMessage(f"预设「{name}」已保存（含塑造与自定义表情）。")

    def _load_preset_by_index(self, idx):
        if idx <= 0:
            return
        name = self.preset_combo.itemText(idx)
        try:
            data = load_preset(name)
        except Exception as e:
            self.statusBar().showMessage(f"加载失败：{e}")
            return
        self.gain_slider.setValue(data.get("global_gain", 1.4))
        for e in emotions.EMOTIONS:
            if e in data.get("emotion_gains", {}):
                self.emo_sliders[e].setValue(data["emotion_gains"][e])
        self.smooth_slider.setValue(data.get("smooth", 0.4))
        # 预设 v2：含塑造配置则应用并同步对话框；旧预设（无 shaping）保持当前塑造
        sh = emotions.shaping_from_dict(data.get("shaping"))
        extras = []
        if sh is not None:
            self.params.set_shaping(sh)
            if self._shape_dlg is not None and self._shape_dlg.isVisible():
                self._shape_dlg.refresh_from(sh)
            extras.append("塑造")
        # 预设 v2：含自定义表情定义则替换并持久化
        ce = sanitize_custom_exprs(data.get("custom_expressions"))
        if ce:
            self.params.set_custom_exprs(ce)
            save_custom_exprs(ce)
            self._rebuild_ce_rows()
            extras.append("自定义表情")
        tail = f"（含{'/'.join(extras)}）" if extras else ""
        self.statusBar().showMessage(f"已加载预设「{name}」{tail}。")

    def _delete_preset(self):
        idx = self.preset_combo.currentIndex()
        if idx <= 0:
            self.statusBar().showMessage("先选中一个预设再删。")
            return
        name = self.preset_combo.itemText(idx)
        reply = QMessageBox.question(self, "删预设", f"删除预设「{name}」？")
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_preset(name)
        except Exception as e:
            self.statusBar().showMessage(f"删除失败：{e}")
            return
        self._refresh_presets()
        self.statusBar().showMessage(f"预设「{name}」已删除。")

    def closeEvent(self, e):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait(2000)
        # os._exit 绕过 cv2/mediapipe 释放偶发卡死（同 main.py）
        os._exit(0)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
