"""
下载 live2d-py 仓库里自带的免费 Cubism 4 示例模型（Haru）到 models/。

模型文件受 Live2D 免费许可协议约束，不提交进仓库（models/ 已在 .gitignore），
本脚本仅供本地开发取用，可重复运行（已下载的会跳过）。

用法: .venv\\Scripts\\python.exe probes\\fetch_sample_model.py
"""
import json
import os
import urllib.request

REPO = "EasyLive2D/live2d-py"
BRANCH = "main"
SUB = "Resources/v3/Haru/"          # Cubism 4 (.moc3) 模型
DEST_ROOT = os.path.join("models", "Resources", "v3", "Haru")
ENTRY = os.path.join(DEST_ROOT, "Haru.model3.json")
# 完整字面 URL（固定下载源，非运行时拼接，无 SSRF 面）
_API_URL = "https://api.github.com/repos/EasyLive2D/live2d-py/git/trees/main?recursive=1"
_RAW_BASE = "https://raw.githubusercontent.com/EasyLive2D/live2d-py/main/"


def main() -> None:
    # 1. 取仓库文件树
    req = urllib.request.Request(_API_URL, headers={"User-Agent": "face-probe"})
    with urllib.request.urlopen(req, timeout=30) as r:
        tree = json.load(r)
    paths = [t["path"] for t in tree["tree"]
             if t["path"].startswith(SUB) and t.get("type") == "blob"]
    print(f"仓库内 {SUB} 共 {len(paths)} 个文件")

    got = 0
    for p in paths:
        dst = os.path.join("models", *p.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            continue
        urllib.request.urlretrieve(_RAW_BASE + p, dst)
        got += 1
        print(f"  下载 {p}")
    print(f"完成（新下载 {got} 个，已存在跳过 {len(paths) - got} 个）")
    print(f"模型入口: {ENTRY}")


if __name__ == "__main__":
    main()
