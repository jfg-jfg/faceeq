"""验证 VTS 桥。

两种用法：
  1) 列参数（订正翻译表用）：
       PYTHONUTF8=1 .venv/Scripts/python.exe probes/vts_probe.py list
     只打印 VTS 里跟 眉/眼/嘴 相关的输入参数名 + 量程，把输出贴回来即可订正
     FaceEQ/vts_bridge.py 的 LIVE2D_TO_VTS。

  2) 正弦扫描（验证注入是否真的驱动小人）：
       PYTHONUTF8=1 .venv/Scripts/python.exe probes/vts_probe.py
     让所有可控参数做满量程正弦；Ctrl-C 停，参数回退给 VTS 自带跟踪。

前置：
  - VTube Studio 运行中 → 设置勾 “Allow Plugin API access” → 装个模型
  - pip install websocket-client
首次会弹 VTS 授权窗，点 Allow。
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq.mapping import RANGES
from faceeq.vts_bridge import LIVE2D_TO_VTS, VTSBridge


def main():
    list_only = len(sys.argv) > 1 and sys.argv[1].lower() in ("list", "--list", "-l")

    br = VTSBridge()
    print("[probe] 连接 VTS ...（首次会弹授权窗，点 Allow）")
    br.connect()
    br.authenticate()
    ranges = br.discover()

    if list_only:
        kw = ("eye", "brow", "pupil", "mouth", "smile", "ball", "cheek",
              "nose", "tongue", "lid")
        names = sorted(ranges.keys())
        rel = [n for n in names if any(k in n.lower() for k in kw)]
        print(f"\n[probe] VTS 共 {len(names)} 个可注入参数。眉/眼/嘴相关 ({len(rel)}):")
        for n in rel:
            print(f"   {n:24s} range={ranges[n]}")
        print("\n[probe] 把上面这些贴回来，我据此订正 LIVE2D_TO_VTS（名字+量程）。")
        br.close()
        return

    names = list(LIVE2D_TO_VTS.keys())
    print(f"[probe] 开始正弦扫描（{len(names)} 个参数满量程）→ 看 VTS 里小人是否被接管。"
          "Ctrl-C 退出。")
    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            params = {}
            for i, n in enumerate(names):
                lo, hi = RANGES.get(n, (0.0, 1.0))
                mid = (lo + hi) / 2
                amp = (hi - lo) / 2
                params[n] = mid + amp * math.sin(t * 1.5 + i)
            br.inject(params, face_found=True)
            print(f"\r[probe] t={t:5.1f}s  keepalive_ok={br.keepalive_ok()}   ",
                  end="", flush=True)
            time.sleep(1 / 30)
    except KeyboardInterrupt:
        print("\n[probe] 已停喂。VTS 参数应回退给它自己的跟踪。")
    finally:
        br.close()


if __name__ == "__main__":
    main()
