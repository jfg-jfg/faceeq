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


def main() -> None:
    # 1. 取仓库文件树
    api = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
    req = urllib.request.Request(api, headers={"User-Agent": "face-probe"})
    with urllib.request.urlopen(req, timeout=30) as r:
        tree = json.load(r)
    paths = [t["path"] for t in tree["tree"]
             if t["path"].startswith(SUB) and t.get("type") == "blob"]
    print(f"仓库内 {SUB} 共 {len(paths)} 个文件")

    base = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"
    got = 0
    for p in paths:
        dst = os.path.join("models", *p.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            continue
        urllib.request.urlretrieve(base + p, dst)
        got += 1
        print(f"  下载 {p}")
    print(f"完成（新下载 {got} 个，已存在跳过 {len(paths) - got} 个）")
    print(f"模型入口: {ENTRY}")


if __name__ == "__main__":
    main()
