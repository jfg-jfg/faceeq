"""营销截图：离屏渲染主面板 / 信号监视 / 高级塑造 → assets/。

zh、en 各出一张主面板；监视条/塑造矩阵填入演示数据让画面「活」。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QGroupBox

import gui
from gui import QSS
from faceeq import emotions
from faceeq import i18n

OUT = os.path.join("assets", "shots")
os.makedirs(OUT, exist_ok=True)

app = QApplication(sys.argv)
app.setStyleSheet(QSS)   # 深色主题与真实运行一致


def dress(win):
    """填入演示状态：元气预设 + 监视条情绪值 + 运行中状态栏。"""
    win.gain_slider.setValue(1.9)         # 元气预设档位
    win.emo_sliders["happy"].setValue(1.0)
    win.emo_sliders["sad"].setValue(-0.4)
    win.emo_sliders["surprised"].setValue(0.8)
    win.emo_sliders["angry"].setValue(0.3)
    win.emo_sliders["disgust"].setValue(-0.4)
    win._on_emo_vals({"happy": 0.85, "angry": 0.12, "sad": 0.32,
                      "surprised": 0.12, "disgust": 0.05})
    win._dom_lbl.setText("[happy]")
    win._fps_lbl.setText("FPS: 60")
    win.statusBar().showMessage(
        "运行中（输出：vts+vmc，手机源）" if i18n.current_lang() == "zh"
        else "Running (outputs: vts+vmc, phone source)")


def group_shot(win, title_contains, path):
    for gb in win.findChildren(QGroupBox):
        if title_contains in gb.title():
            gb.grab().save(path)
            return True
    return False


def main():
    lang0 = i18n.current_lang()

    # —— 中文 ——
    i18n.set_lang("zh")
    win = gui.MainWindow()
    win.resize(1120, 900)
    win.show()
    from PySide6.QtCore import Qt
    scroll = win.centralWidget()
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    for _ in range(8):
        app.processEvents()
        time.sleep(0.05)
    dress(win)
    for _ in range(4):
        app.processEvents()
        time.sleep(0.05)
    win.grab().save(os.path.join(OUT, "main-zh.png"))
    ok1 = group_shot(win, "信号监视", os.path.join(OUT, "monitor-zh.png"))
    print("zh main/monitor:", ok1)

    # —— English（set_lang + 重新扫描）——
    i18n.set_lang("en")
    gui.translate_tree(win)
    app.processEvents()
    dress(win)
    win.grab().save(os.path.join(OUT, "main-en.png"))

    # —— 高级塑造对话框（zh）——
    i18n.set_lang("zh")
    win._open_shaping()
    win._shape_dlg.show()
    for _ in range(6):
        app.processEvents()
        time.sleep(0.05)
    win._shape_dlg.grab().save(os.path.join(OUT, "shaping-zh.png"))
    win._shape_dlg.close()

    win.close()
    i18n.set_lang(lang0)
    print("screens saved →", OUT)


if __name__ == "__main__":
    main()
