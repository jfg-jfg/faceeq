"""GUI 离屏冒烟：构造 MainWindow + 打开各对话框，抓异常/布局问题（不显示窗口）。
跑：QT_QPA_PLATFORM=offscreen PYTHONUTF8=1 .venv/Scripts/python.exe probes/gui_smoke.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

import gui
from faceeq import emotions

# 不碰真实硬件：离屏冒烟里摄像头枚举可能被占用进程卡死，打桩返回固定列表
gui.list_sources = lambda max_check=4: [0]

failures = []


def ck(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        failures.append(name)


app = QApplication(sys.argv)
win = gui.MainWindow()

# 1. 主窗口基础：情绪滑块在、有几何尺寸
ck("情绪滑块 5 个已建", len(win.emo_sliders) == 5)
geo = win.emo_sliders["happy"].geometry()
ck(f"happy 滑块几何非零 {geo.width()}x{geo.height()}", geo.width() > 0 and geo.height() > 0)

# 2. 输入源 + 输出目标组（多选）+ 信号监视器
ck("输入源下拉 2 项（phone/vmc）", win.input_combo.count() == 2)
win.input_combo.setCurrentIndex(1)   # vmc
ck(f"切 VMC 后端口默认 {win.input_port.value()}==39539", win.input_port.value() == 39539)
win.input_combo.setCurrentIndex(0)
ck("输入源写入 Params", win.params.snapshot().input_kind == "phone")
ck("输出目标勾选组 3 项", len(win.out_checks) == 3)
ck("默认勾选 vts", win.out_checks["vts"].isChecked()
   and win.params.snapshot().output_kinds == ["vts"])
win.out_checks["vmc"].setChecked(True)
ck(f"勾 vmc 后 Params 感知多输出（{win.params.snapshot().output_kinds}）",
   set(win.params.snapshot().output_kinds) == {"vts", "vmc"})
win.out_checks["vmc"].setChecked(False)
ck("输出目标提示文案非空", len(win.out_hint.text()) > 10)
ck("信号监视条 5 根", len(win._emo_bars) == 5)
win._on_emo_vals({"happy": 0.8, "sad": 0.25, "angry": 1.5})   # 越界值应被钳制
ck("监视条更新+钳制", win._emo_bars["happy"].value() == 80
   and win._emo_bars["sad"].value() == 25 and win._emo_bars["angry"].value() == 100)

# 3. 自定义表情行：示例文件 3 个定义 → 3 行滑块
snap = win.params.snapshot()
defs, act = snap.custom_exprs, snap.custom_act
ck(f"自定义表情定义 3 个（实际 {len(defs)}: {sorted(defs)}）", len(defs) == 3)
ck(f"自定义表情行已建 {len(win._ce_rows)}", len(win._ce_rows) == len(defs))

# 4. 打开高级塑造对话框（单 BlendShape 矩阵 + BS 耦合）
try:
    win._open_shaping()
    dlg = win._shape_dlg
    ck("高级塑造对话框打开", dlg is not None)
    ck(f"BlendShape 矩阵单元格 {len(dlg._bs_cells)}（{len(emotions.BS_CONFIG)} 形状×5）",
       len(dlg._bs_cells) == 5 * len(emotions.BS_CONFIG))
    ck(f"耦合行 {len(dlg._coup_checks)} 条（BS_COUPLING）",
       len(dlg._coup_checks) == len(emotions.BS_COUPLING))
    dlg._reset()
    dlg._apply()
    sh = win.params.snapshot().shaping
    # 语义：空 boost 键不进用户配置（bs_amplify 回退 BS_CONFIG 默认），有默认 boost 的键保留
    ck("塑造应用保留默认 boost 键（mouthSmileLeft happy=0.5）",
       sh.bs_boosts.get("mouthSmileLeft", {}).get("happy") == 0.5)
except Exception as e:
    import traceback
    traceback.print_exc()
    ck(f"高级塑造对话框（异常: {type(e).__name__}: {e}）", False)

# 5. 自定义表情：新建/删除路径（直接调处理器，绕过模态 exec）
try:
    defs = dict(win.params.snapshot().custom_exprs)
    defs["测试表情"] = {"happy": 0.3}
    win._apply_ce_defs(defs)
    ck("定义落盘+建行", win.params.snapshot().custom_exprs.get("测试表情") is not None
       and "测试表情" in win._ce_rows)
    win.params.set_custom_act("测试表情", 0.8)
    ck("激活度写入", win.params.snapshot().custom_act.get("测试表情") == 0.8)
    defs.pop("测试表情")
    win._apply_ce_defs(defs)
    ck("删除后行同步", "测试表情" not in win._ce_rows
       and win.params.snapshot().custom_act.get("测试表情") is None)
except Exception as e:
    import traceback
    traceback.print_exc()
    ck(f"自定义表情路径（异常: {type(e).__name__}: {e}）", False)

# 6. 语音情绪组 + 情绪触发对话框
ck("语音控件齐（开关/设备/灵敏度/强度）",
   win.voice_check is not None and win.voice_dev_combo.count() >= 1
   and win.voice_sens is not None and win.voice_strength is not None)
win.voice_check.setChecked(True)
ck("语音开关写入 Params", win.params.snapshot().voice_enabled is True)
try:
    win._open_triggers()
    dlg = win._trig_dlg
    ck("情绪触发对话框打开", dlg is not None)
    ck(f"触发行 5 情绪（{len(dlg._rows)}）", len(dlg._rows) == 5)
    dlg.set_hotkeys([{"name": "贴纸:大笑", "id": 3}, {"name": "切换表情", "id": 4}])
    dlg._rows["happy"][3].setCurrentIndex(1)      # 选中 id=3
    dlg._rows["happy"][0].setChecked(True)
    dlg._apply()
    tcfg = win.params.snapshot().hotkey_triggers
    ck(f"触发配置落盘+应用 (happy hotkey_id={tcfg.get('happy', {}).get('hotkey_id')})",
       tcfg.get("happy", {}).get("hotkey_id") == 3
       and tcfg.get("happy", {}).get("enabled") is True)
    import os as _os
    ck("hotkey_triggers.json 已写", _os.path.exists("hotkey_triggers.json"))
except Exception as e:
    import traceback
    traceback.print_exc()
    ck(f"情绪触发路径（异常: {type(e).__name__}: {e}）", False)

# 7. 内容不被压扁：主 central 是 QScrollArea（小屏滚动），central 高度接近布局需求
win.show()
app.processEvents()
from PySide6.QtWidgets import QScrollArea
scroll = win.centralWidget()
ck("central 是 QScrollArea（可滚动不压扁）", isinstance(scroll, QScrollArea))
central_h = scroll.widget().height()
lay = scroll.widget().layout()
need = lay.minimumSize().height() + lay.contentsMargins().top() + lay.contentsMargins().bottom()
print(f"[info] 窗口高 {win.height()}，central 高 {central_h}，布局最小需求 {need}（视口不足时出滚动条）")
ck(f"内容接近完整（central {central_h} >= 需求 {need}-24）", central_h >= need - 24)

# 清理测试产物，不污染工作区
try:
    os.remove("hotkey_triggers.json")
except OSError:
    pass

print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
