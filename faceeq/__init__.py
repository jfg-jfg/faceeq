"""FaceEQ: VTuber 表情情绪 EQ —— 面捕 blendshape → 按情绪放大/抑制 → 驱动 Live2D/3D 模型。

资源路径：源码运行取 CWD；PyInstaller 打包后取 _internal（sys._MEIPASS）里的只读资源。
"""
__version__ = "0.1.0"

import os
import sys


def resource_path(*parts) -> str:
    """定位随包分发的只读资源（模型/内置预设/示例配置）。

    冻结环境先查 _MEIPASS（onedir 的 _internal），再回退 CWD；源码运行即 CWD。
    未找到时返回 CWD 拼接路径（调用方按"不存在"自行处理）。
    """
    bases = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bases.append(meipass)
    bases.append(os.getcwd())
    for base in bases:
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return os.path.join(bases[-1], *parts)
