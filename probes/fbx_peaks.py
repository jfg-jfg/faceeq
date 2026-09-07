"""提取二进制 FBX 里 BlendShape 动画曲线的峰值(一次性分析工具)。

用法: python fbx_peaks.py <file.fbx>
输出: 每个 BlendShapeChannel(ARKit 形状)的 KeyValueFloat 峰值/均值/时长。
"""
import struct
import sys
import zlib


class Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name):
        self.name = name
        self.props = []
        self.children = []


class Reader:
    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.d, self.p)[0]
        self.p += 8
        return v

    def i64(self):
        v = struct.unpack_from("<q", self.d, self.p)[0]
        self.p += 8
        return v

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def f64(self):
        v = struct.unpack_from("<d", self.d, self.p)[0]
        self.p += 8
        return v

    def raw(self, n):
        v = self.d[self.p:self.p + n]
        self.p += n
        return v


def read_property(r):
    t = chr(r.u8())
    if t == "Y":
        return struct.unpack_from("<h", r.d, r.p)[0]
    if t == "C":
        return bool(r.u8())
    if t == "I":
        v = struct.unpack_from("<i", r.d, r.p)[0]
        r.p += 4
        return v
    if t == "F":
        v = struct.unpack_from("<f", r.d, r.p)[0]
        r.p += 4
        return v
    if t == "D":
        v = struct.unpack_from("<d", r.d, r.p)[0]
        r.p += 8
        return v
    if t == "L":
        return r.i64()
    if t in "fdlib":
        n = r.u32()
        enc = r.u32()
        clen = r.u32()
        raw = r.raw(clen)
        if enc == 1:
            raw = zlib.decompress(raw)
        fmt = {"f": "<%df", "d": "<%dd", "l": "<%dq", "i": "<%di", "b": "<%dB"}[t]
        return list(struct.unpack(fmt % n, raw))
    if t in "SR":
        n = r.u32()
        return r.raw(n)
    raise ValueError("unknown prop type: " + t)


def read_node(r, version):
    start = r.p
    if version >= 7500:
        end, nprops, plen = r.u64(), r.u64(), r.u64()
    else:
        end, nprops, plen = r.u32(), r.u32(), r.u32()
    nlen = r.u8()
    name = r.raw(nlen).decode("utf-8", "replace")
    if end == 0:
        return None
    node = Node(name)
    for _ in range(nprops):
        node.props.append(read_property(r))
    while r.p < end:
        child = read_node(r, version)
        if child is None:
            break
        node.children.append(child)
    r.p = end
    return node


def find(node, name, out):
    for c in node.children:
        if c.name == name:
            out.append(c)
        find(c, name, out)


def main(path):
    data = open(path, "rb").read()
    assert data[:20] == b"Kaydara FBX Binary  ", "not binary fbx"
    version = struct.unpack_from("<I", data, 23)[0]
    r = Reader(data, 27)
    root = Node("root")
    while r.p < len(data) - 13:
        n = read_node(r, version)
        if n is None:
            break
        root.children.append(n)

    # Objects: id -> (name, label)  (该 app 的 FBX 把两者合成一个字符串 name\x00\x01Label)
    objs = {}
    obj_nodes = []
    find(root, "Objects", obj_nodes)
    for o in obj_nodes[0].children:
        if len(o.props) >= 3 and isinstance(o.props[0], int):
            raw = o.props[1]
            if isinstance(raw, bytes):
                name, _, label = raw.partition(b"\x00\x01")
                name = name.decode("utf-8", "replace")
                label = label.decode("utf-8", "replace")
            else:
                name, label = str(raw), str(raw)
            objs[o.props[0]] = (name, label, o)

    # Connections: child -> parent
    conn_nodes = []
    find(root, "Connections", conn_nodes)
    child2parent = {}
    for c in conn_nodes[0].children:
        if c.props and c.props[0] in (b"OO", b"OP"):
            child2parent[c.props[1]] = c.props[2]

    # AnimationCurve: id -> peak/mean/frames/duration
    curves = {}
    for oid, (name, label, node) in objs.items():
        if label != "AnimCurve":
            continue
        kv, kt = [], []
        arrays = []
        find(node, "KeyValueFloat", arrays)
        if arrays:
            kv = arrays[0].props[0]
        times = []
        find(node, "KeyTime", times)
        if times:
            kt = times[0].props[0]
        if kv:
            curves[oid] = (max(kv), sum(kv) / len(kv), len(kv),
                           (kt[-1] - kt[0]) / 46186158000 if len(kt) > 1 else 0)

    # curve -> AnimCurveNode(DeformPercent) -> SubDeformer(blendShape1.<shape>)
    print(f"{'shape':<28}{'peak':>7}{'mean':>7}{'frames':>7}{'dur(s)':>8}")
    rows = []
    transform = {}
    for cid, par in child2parent.items():
        if cid not in curves or par not in objs:
            continue
        node_name, node_label, _ = objs[par]
        if node_label == "AnimCurveNode" and node_name == "DeformPercent":
            gp = child2parent.get(par)
            if gp in objs:
                gname, glabel, _ = objs[gp]
                shape = gname.split(".", 1)[-1] if glabel == "SubDeformer" else gname
                rows.append((shape, *curves[cid]))
        elif node_label == "AnimCurveNode":
            transform.setdefault(node_name, []).append(curves[cid])
    for name, peak, mean, n, dur in sorted(rows, key=lambda x: -x[1]):
        print(f"{name:<28}{peak:>7.3f}{mean:>7.3f}{n:>7}{dur:>8.1f}")
    for node_name, plist in sorted(transform.items()):
        print(f"[transform {node_name}] peaks={','.join(f'{p[0]:.1f}' for p in plist)} "
              f"dur={max((p[3] for p in plist), default=0):.1f}s")


if __name__ == "__main__":
    main(sys.argv[1])
