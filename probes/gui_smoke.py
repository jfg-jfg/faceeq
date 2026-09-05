"""GUI 离屏冒烟：构造 MainWindow + 打开各对话框，抓异常/布局问题（不显示窗口）。
跑：QT_QPA_PLATFORM=offscreen PYTHONUTF8=1 .venv/Scripts/python.exe probes/gui_smoke.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

import gui

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
grp = win.emo_sliders["happy"].parentWidget()
ck(f"情绪组尺寸 {grp.width()}x{grp.height()}", grp.height() > 50)

# 2. 自定义表情行：示例文件 3 个定义 → 3 行滑块
defs, act = win.params.snapshot()[6], win.params.snapshot()[7]
ck(f"自定义表情定义 3 个（实际 {len(defs)}: {sorted(defs)}）", len(defs) == 3)
ck(f"自定义表情行已建 {len(win._ce_rows)}", len(win._ce_rows) == len(defs))

# 3. 打开高级塑造对话框（2b 曾因 snapshot 解包位数崩）
try:
    win._open_shaping()
    dlg = win._shape_dlg
    ck("高级塑造对话框打开", dlg is not None and dlg.isVisible() or dlg is not None)
    ck(f"塑造矩阵单元格 {len(dlg._cells)}（14 参数×5 情绪=70）", len(dlg._cells) == 70)
    ck("耦合行 4 条", len(dlg._coup_checks) == 4)
    dlg._reset()
    dlg._apply()
except Exception as e:
    import traceback
    traceback.print_exc()
    ck(f"高级塑造对话框打开（异常: {type(e).__name__}: {e}）", False)

# 4. 自定义表情：新建/编辑/删除路径（直接调处理器，绕过模态 exec）
try:
    defs = dict(win.params.snapshot()[6])
    defs["测试表情"] = {"happy": 0.3}
    win._apply_ce_defs(defs)
    ck("定义落盘+建行", win.params.snapshot()[6].get("测试表情") is not None
       and "测试表情" in win._ce_rows)
    win.params.set_custom_act("测试表情", 0.8)
    ck("激活度写入", win.params.snapshot()[7].get("测试表情") == 0.8)
    defs.pop("测试表情")
    win._apply_ce_defs(defs)
    ck("删除后行同步", "测试表情" not in win._ce_rows
       and win.params.snapshot()[7].get("测试表情") is None)
except Exception as e:
    import traceback
    traceback.print_exc()
    ck(f"自定义表情路径（异常: {type(e).__name__}: {e}）", False)

# 5. 内容不被压扁：QScrollArea 包装下 central 高度应≥布局最小需求（不够则出滚动条）
win.show()
app.processEvents()
central_h = win.centralWidget().widget().height()
lay = win.centralWidget().widget().layout()
need = lay.minimumSize().height() + lay.contentsMargins().top() + lay.contentsMargins().bottom()
print(f"[info] 窗口高 {win.height()}，central 高 {central_h}，布局最小需求 {need}")
ck(f"内容完整不被压（central {central_h} >= 需求 {need}）", central_h >= need)

print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
