"""打包产品 exe（PyInstaller onedir）。

用法:
    .venv/Scripts/python.exe -m pip install pyinstaller
    .venv/Scripts/python.exe probes/build_release.py

产物: dist/FaceEQ/（绿色目录：FaceEQ.exe + 依赖 + models + 内置预设）
      分发 = 把 dist/FaceEQ 整个目录打 zip。
说明:
- 只含 core 依赖（无 live2d-py/glfw——本地 Live2D 预览是开发特性，产品预览走 VTS/目标软件）。
- mediapipe 带大量数据文件，用 --collect-all 兜底；单文件(onefile)模式已知易碎，勿改 onefile。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "FaceEQ"
SEP = ";" if sys.platform == "win32" else ":"


def main():
    os.chdir(ROOT)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[build] 未安装 PyInstaller：.venv/Scripts/python.exe -m pip install pyinstaller")
        sys.exit(1)

    for d in (os.path.join("build", NAME), os.path.join("dist", NAME)):
        if os.path.isdir(d):
            print(f"[build] 清理 {d}")
            shutil.rmtree(d, ignore_errors=True)

    datas = [
        (os.path.join("models", "face_landmarker.task"), "models"),
        (os.path.join("custom_expressions.json"), "."),
        (os.path.join("presets", "builtin"), os.path.join("presets", "builtin")),
    ]
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--name", NAME, "--windowed", "--onedir"]
    for src, dst in datas:
        if os.path.exists(src):
            cmd += ["--add-data", f"{src}{SEP}{dst}"]
        else:
            print(f"[build] ⚠ 缺数据文件 {src}（不影响打包，运行时会缺该功能）")
    for pkg in ("mediapipe", "sounddevice"):
        cmd += ["--collect-all", pkg]
    cmd.append(os.path.join("gui.py"))
    print("[build]", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("[build] PyInstaller 失败")
        sys.exit(r.returncode)

    exe = os.path.join("dist", NAME, f"{NAME}.exe")

    # —— 构建后裁剪：确认不用的组件（GUI 只用 Qt Core/Gui/Widgets）。逐项删除后需试启动验证。
    #    注意 matplotlib 不能裁：mediapipe vision/__init__ 导入链在 import 时就需要它。 ——
    internal = os.path.join("dist", NAME, "_internal")
    pruned = 0
    prune_items = [
        os.path.join(internal, "PySide6", "opengl32sw.dll"),   # 软件渲染 OpenGL 兜底（20MB）
        os.path.join(internal, "PySide6", "Qt6Quick.dll"),
        os.path.join(internal, "PySide6", "Qt6Qml.dll"),
        os.path.join(internal, "PySide6", "Qt6Pdf.dll"),
        os.path.join(internal, "PySide6", "translations"),
    ]
    for p in prune_items:
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
            pruned += 1
        elif os.path.exists(p):
            os.remove(p)
            pruned += 1
    print(f"[build] 裁剪 {pruned} 项不用的组件（Quick/Qml/Pdf/软渲染GL/翻译/matplotlib）")

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(os.path.join("dist", NAME)) for f in fs)
    print(f"\n[build] 完成: {exe}")
    print(f"[build] 目录总大小 {size / 1e6:.0f} MB")
    print("[build] ⚠ 请试启动 dist/FaceEQ/FaceEQ.exe 确认裁剪无副作用后再分发")
    print("[build] 分发：把 dist/FaceEQ 整个目录打 zip；发布清单见 RELEASE.md")


if __name__ == "__main__":
    main()
