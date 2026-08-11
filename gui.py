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
import subprocess
import sys
import threading
import time
from types import SimpleNamespace as NS

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

from faceeq import emotions, engine, profile as profile_mod
from faceeq.capture import Capture, list_sources
from faceeq.mapping import base_map
from faceeq.smooth import Smoother
from faceeq.vts_bridge import VTSBridge

DEFAULT_PROFILE = os.path.join("profiles", "calibration.json")
PRESETS_DIR = "presets"


# —— 预设 I/O ——
def list_presets():
    if not os.path.isdir(PRESETS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(PRESETS_DIR) if f.endswith(".json"))


def save_preset(name, gain, emotion_gains, smooth):
    os.makedirs(PRESETS_DIR, exist_ok=True)
    data = {"name": name, "global_gain": gain,
            "emotion_gains": emotion_gains, "smooth": smooth}
    with open(os.path.join(PRESETS_DIR, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_preset(name):
    with open(os.path.join(PRESETS_DIR, name + ".json"), "r", encoding="utf-8") as f:
        return json.load(f)


def delete_preset(name):
    os.remove(os.path.join(PRESETS_DIR, name + ".json"))

# —— VTS 风格 QSS（深色 / 圆角 / 蓝高亮）——
QSS = """
* { font-family: 'Segoe UI','Microsoft YaHei',sans-serif; font-size: 13px; color: #e0e0e0; }
QMainWindow, QWidget#central { background: #252a35; }
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

    def snapshot(self):
        with self._lock:
            return self.global_gain, dict(self.emotion_gains), self.smooth, self.calib

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
            self.status.emit("正在打开摄像头…")
            cap = Capture(source=source)
            self.status.emit("正在连接 VTS…")
            bridge = VTSBridge()
            bridge.start()                       # connect + auth + discover + ensure_custom_params
            _, _, smooth, _ = self._params.snapshot()
            smoother = Smoother(smooth)
            self.status.emit("运行中（注入 VTS）")
            last_params = {}
            frames = 0
            timer = time.time()
            last_dom = ""
            self._running = True
            while self._running:
                f = cap.read()
                gain, eg, smooth, calib = self._params.snapshot()
                params, dom_now, ff = engine.process_frame(f, gain, eg, calib)
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
    """在 QThread 里跑校准子进程，不阻塞 GUI。完成后 emit finished。"""
    finished = Signal()

    def __init__(self, source):
        super().__init__()
        self._source = source

    @Slot()
    def run(self):
        calibrate_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "probes", "calibrate.py")
        subprocess.run([sys.executable, calibrate_path, "--source", str(self._source)],
                       check=False)
        self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceEQ")
        self.setMinimumSize(440, 600)

        self.params = Params()
        self.thread = None
        self.worker = None
        self._calib_thread = None
        self._running = False
        self._had_error = False

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
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
        btns.addWidget(self.start_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.calib_btn)
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

        # 滑块 → Params（实时）
        self.gain_slider.valueChanged.connect(lambda v: self.params.set_gain(v))
        for e, fs in self.emo_sliders.items():
            fs.valueChanged.connect(lambda v, ee=e: self.params.set_emotion(ee, v))
        self.smooth_slider.valueChanged.connect(lambda v: self.params.set_smooth(v))

        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.calib_btn.clicked.connect(self._on_calibrate)

    # —— profile ——
    def _load_profile(self, path):
        try:
            prof = profile_mod.load_profile(path)
            cfg = profile_mod.resolve(
                NS(gain=None, smooth=None, **{e: None for e in emotions.EMOTIONS}), prof)
            self.params.set_calib(cfg.calib)
            self._profile_lbl.setText(f"profile: {path}")
        except Exception as ex:
            self._profile_lbl.setText(f"profile: 无/失败")
            self.params.set_calib(None)

    # —— 开始 / 停止 ——
    def _on_start(self):
        if self._running:
            return
        dlg = QMessageBox(self)
        dlg.setWindowTitle("启动前确认")
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

    def _on_calibrate_done(self):
        """校准子进程完成（QThread 信号回来）→ 重载 profile + 恢复按钮。"""
        self._load_profile(DEFAULT_PROFILE)
        self.start_btn.setEnabled(True)
        self.calib_btn.setEnabled(True)
        self.statusBar().showMessage("校准完成，profile 已重载。点「开始」继续。")

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
        # 消毒预设名（过滤路径非法字符 + Windows 保留名 + 限长 64）
        name = re.sub(r'[\\/:*?"<>|]', '_', name).strip()[:64]
        if not name:
            self.statusBar().showMessage("预设名无效。")
            return
        if name.upper() in {"CON","PRN","AUX","NUL"} | {f"{p}{n}" for p in ("COM","LPT") for n in range(1,10)}:
            name = "_" + name
        save_preset(name, self.gain_slider.value(),
                    {e: fs.value() for e, fs in self.emo_sliders.items()},
                    self.smooth_slider.value())
        self._refresh_presets()
        self.preset_combo.setCurrentText(name)
        self.statusBar().showMessage(f"预设「{name}」已保存。")

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
        self.statusBar().showMessage(f"已加载预设「{name}」。")

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
