"""校正向导 CLI shim（实现已入 faceeq/calibrate.py；frozen exe 内嵌同一份代码）。

用法：
    PYTHONUTF8=1 .venv\Scripts\python.exe probes\calibrate.py --source phone
"""
import sys

from faceeq.calibrate import main

if __name__ == "__main__":
    sys.exit(main())
