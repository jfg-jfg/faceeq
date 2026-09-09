"""受控录像分段扫描:头三轴 / 眼球四向 / 关键表情 的偏移段检测。

用法: python fbx_scan.py <file.fbx> [file2.fbx ...]
每条曲线找 |值-中位数| > 阈值 的连续段,按时序输出段的方向与幅度。
"""
import sys

sys.path.insert(0, r"C:\Users\jiafei\AppData\Local\Temp")
sys.path.insert(0, r"D:\program\face\probes")
import struct
from statistics import median

from fbx_peaks import Reader, read_node, Node, find

KTIME = 46186158000  # 每秒


def load(path):
    data = open(path, "rb").read()
    version = struct.unpack_from("<I", data, 23)[0]
    r = Reader(data, 27)
    root = Node("root")
    while r.p < len(data) - 13:
        n = read_node(r, version)
        if n is None:
            break
        root.children.append(n)

    objs = {}
    obj_nodes = []
    find(root, "Objects", obj_nodes)
    for o in obj_nodes[0].children:
        if len(o.props) >= 3 and isinstance(o.props[0], int):
            raw = o.props[1]
            name, _, label = raw.partition(b"\x00\x01")
            objs[o.props[0]] = (name.decode("utf-8", "replace"),
                                label.decode("utf-8", "replace"), o)

    conn = []
    find(root, "Connections", conn)
    child2parent = {}
    op_prop = {}
    for c in conn[0].children:
        if c.props and c.props[0] in (b"OO", b"OP"):
            child, parent = c.props[1], c.props[2]
            child2parent[child] = parent
            if c.props[0] == b"OP" and len(c.props) > 3:
                op_prop[(child, parent)] = c.props[3].decode("utf-8", "replace")

    def curve_data(oid):
        kv, kt = [], []
        arrays = []
        find(objs[oid][2], "KeyValueFloat", arrays)
        if arrays:
            kv = arrays[0].props[0]
        times = []
        find(objs[oid][2], "KeyTime", times)
        if times:
            kt = [t / KTIME for t in times[0].props[0]]
        return kt, kv

    # 分类曲线
    rot = {}    # 轴 -> (kt, vals)
    shapes = {}  # 形状 -> (kt, vals)
    for oid, (name, label, _n) in objs.items():
        if label != "AnimCurve":
            continue
        par = child2parent.get(oid)
        if par is None:
            continue
        prop = op_prop.get((oid, par))
        pname, plabel, _ = objs.get(par, ("?", "?", None))
        if prop in ("d|X", "d|Y", "d|Z") and plabel == "AnimCurveNode":
            gp = child2parent.get(par)
            if gp is not None and objs.get(gp, ("", "Model"))[1] == "Model":
                kt, kv = curve_data(oid)
                rot[prop[-1]] = (kt, kv)
        elif pname == "DeformPercent" and plabel == "AnimCurveNode":
            gp = child2parent.get(par)
            if gp is not None and objs.get(gp, ("", "?"))[1] == "SubDeformer":
                gname = objs[gp][0]
                kt, kv = curve_data(oid)
                shapes[gname.split(".", 1)[-1]] = (kt, kv)
    return rot, shapes


def runs(kt, vals, thresh, min_dur=0.4):
    if not kt:
        return []
    base = median(vals)
    out = []
    cur = None
    for t, v in zip(kt, vals):
        dev = v - base
        if abs(dev) > thresh:
            sign = 1 if dev > 0 else -1
            if cur and cur["sign"] == sign and t - cur["t1"] < 0.6:
                cur["devs"].append(dev)
                cur["t1"] = t
            else:
                if cur and cur["t1"] - cur["t0"] >= min_dur:
                    out.append(cur)
                cur = {"t0": t, "t1": t, "sign": sign, "devs": [dev]}
        else:
            if cur and t - cur["t1"] > 0.6:
                if cur["t1"] - cur["t0"] >= min_dur:
                    out.append(cur)
                cur = None
    if cur and cur["t1"] - cur["t0"] >= min_dur:
        out.append(cur)
    return [{"t": f"{c['t0']:.1f}-{c['t1']:.1f}", "sign": c["sign"],
             "dev": median(c["devs"])} for c in out]


def report(path):
    rot, shapes = load(path)
    print(f"\n━━━ {path.split(chr(92))[-1]} ━━━━━━━━━━")
    if rot:
        dur = max((kt[-1] for kt, _ in rot.values() if kt), default=0)
        print(f"时长 {dur:.1f}s | 头部三轴偏移段(阈 8°):")
        for axis in "XYZ":
            if axis in rot:
                for s in runs(rot[axis][0], rot[axis][1], 8.0):
                    print(f"  R{axis} t={s['t']}s 方向{'+' if s['sign']>0 else '−'}"
                          f" 幅度{abs(s['dev']):6.1f}°")
    else:
        print("(无头旋转曲线)")
    eye_names = ["eyeLookInLeft", "eyeLookOutLeft", "eyeLookInRight",
                 "eyeLookOutRight", "eyeLookUpLeft", "eyeLookDownLeft",
                 "eyeLookUpRight", "eyeLookDownRight"]
    print("眼球偏移段(阈 15):")
    for n in eye_names:
        if n in shapes:
            for s in runs(shapes[n][0], shapes[n][1], 15.0):
                print(f"  {n:<18} t={s['t']}s {'+' if s['sign']>0 else '−'}{abs(s['dev']):.0f}")
    c_names = ["mouthFrownLeft", "mouthFrownRight", "browInnerUp",
               "browDownLeft", "browDownRight", "noseSneerLeft",
               "noseSneerRight", "mouthSmileLeft", "mouthSmileRight"]
    print("表情偏移段(阈 12):")
    for n in c_names:
        if n in shapes:
            for s in runs(shapes[n][0], shapes[n][1], 12.0):
                print(f"  {n:<18} t={s['t']}s {'+' if s['sign']>0 else '−'}{abs(s['dev']):.0f}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        report(p)
