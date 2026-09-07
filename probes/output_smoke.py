"""多输出支持（VMC/OSC）smoke：bs_amplify 塑形 + 三个输出适配器的真实 UDP 回环验证。
跑：PYTHONUTF8=1 .venv/Scripts/python.exe probes/output_smoke.py

钉死：BS 默认塑形（happy 嘴部增强、blink 1:1、persona 压制）、VMC bundle 封包
（python-osc 解析回读）、OSC prefix/映射两模式、序列化往返保 bs_boosts。
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq import emotions, core
from faceeq.frame import Frame
from faceeq.outputs import VmcOutput, OscRawOutput, VTSOutput, create_output

failures = []


def ck(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        failures.append(name)


_Z = {e: 0.0 for e in emotions.EMOTIONS}
_EH = {**_Z, "happy": 0.9}

# (a) bs_amplify 默认基线
BASE = {"mouthSmileLeft": 0.4, "eyeBlinkLeft": 0.3, "browDownLeft": 0.2,
        "eyeLookOutLeft": 0.5, "noseSneerLeft": 0.3}
emo_happy = dict(_Z, happy=0.8)
out = emotions.bs_amplify(BASE, emo_happy, 1.4, _Z)
ck(f"(a) happy 增益抬嘴笑 ({out['mouthSmileLeft']:.3f} > 0.4)",
   out["mouthSmileLeft"] > 0.4)
ck(f"(a) blink 1:1 不吃全局 ({out['eyeBlinkLeft']:.3f}==0.3)",
   abs(out["eyeBlinkLeft"] - 0.3) < 1e-9)
ck(f"(a) eyeLook 1:1 透传 ({out['eyeLookOutLeft']:.3f}==0.5)",
   abs(out["eyeLookOutLeft"] - 0.5) < 1e-9)
ck("(a) 无情绪键的形状只吃全局 (browDown 0.2*1.4)", abs(out["browDownLeft"] - 0.28) < 1e-9)

# (b) persona 负增益压制
out_neg = emotions.bs_amplify(BASE, emo_happy, 1.4, {**_Z, "happy": -1.0})
ck(f"(b) happy 负增益压嘴笑 ({out_neg['mouthSmileLeft']:.3f} < 0.4)",
   0.0 <= out_neg["mouthSmileLeft"] < 0.4)
ck(f"(b) 压制不越负 ({out_neg['mouthSmileLeft']:.3f}>=0)", out_neg["mouthSmileLeft"] >= 0)

# (c) Shaping 定制 + 序列化往返
sh = emotions.DEFAULT_SHAPING.copy()
sh.bs_boosts["browDownLeft"] = {"happy": 0.5}          # 自定义：happy 也抬压眉
EH1 = {**_Z, "happy": 1.0}
out_base = emotions.bs_amplify(BASE, emo_happy, 1.4, EH1)   # 默认塑形对照
out_c = emotions.bs_amplify(BASE, emo_happy, 1.4, EH1, sh)
ck(f"(c) 自定义 bs_boost 生效 ({out_c['browDownLeft']:.3f} > 默认 {out_base['browDownLeft']:.3f})",
   out_c["browDownLeft"] > out_base["browDownLeft"])
sh_rt = emotions.shaping_from_dict(emotions.shaping_to_dict(sh))
ck("(c) 序列化往返保 bs_boosts",
   sh_rt is not None
   and emotions.bs_amplify(BASE, emo_happy, 1.4, EH1, sh_rt)["browDownLeft"]
   == out_c["browDownLeft"])
sh_n = emotions.shaping_from_dict({"param_boosts": {}, "couplings": []})
ck("(c) 缺 bs_boosts 键 → 默认表（不被空表覆盖）",
   abs(emotions.bs_amplify(BASE, emo_happy, 1.4, _Z, sh_n)["mouthSmileLeft"]
       - out["mouthSmileLeft"]) < 1e-9)

# (d) VMC 输出：真实 UDP 回环 + python-osc 解析回读
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 0))
rx.settimeout(2.0)
vmc_port = rx.getsockname()[1]
vmc = VmcOutput("127.0.0.1", vmc_port)
BS = {"jawOpen": 0.5, "eyeWideLeft": 0.8, "mouthSmileLeft": 0.3}
vmc.inject({}, BS, True)
data, _ = rx.recvfrom(65536)
from pythonosc.osc_packet import OscPacket
msgs = [m.message for m in OscPacket(data).messages]
addrs = [m.address for m in msgs]
vals = {m.params[0]: m.params[1] for m in msgs if m.address.endswith("blend/val")}
ck(f"(d) VMC 帧消息数 {len(msgs)}=={len(BS)}+1(apply)", len(msgs) == len(BS) + 1)
ck("(d) blend/val 地址齐全", all("/VMC/ext/blend/val" in a for a in addrs[:-1]))
ck(f"(d) apply 收帧 ({addrs[-1]})", addrs[-1] == "/VMC/ext/blend/apply")
ck(f"(d) 值 round-trip jawOpen={vals.get('jawOpen')}",
   abs(float(vals.get("jawOpen", -1)) - 0.5) < 1e-6)
ck(f"(d) 字符串名 eyeWideLeft={vals.get('eyeWideLeft')}",
   abs(float(vals.get("eyeWideLeft", -1)) - 0.8) < 1e-6)
rx.close()

# (e) OSC 原始输出：prefix 模式与映射模式
rx2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx2.bind(("127.0.0.1", 0))
rx2.settimeout(2.0)
osc_port = rx2.getsockname()[1]
osc = OscRawOutput("127.0.0.1", osc_port)
osc.inject({}, BS, True)
addrs = []
for _ in range(len(BS)):                    # 原始 OSC：每参数一个数据报
    data, _ = rx2.recvfrom(65536)
    addrs += [m.message.address for m in OscPacket(data).messages]
addrs = sorted(addrs)
ck(f"(e) prefix 模式地址 {addrs[0]}",
   addrs[0] == "/faceeq/bs/eyeWideLeft" and len(addrs) == 3)
osc_m = OscRawOutput("127.0.0.1", osc_port,
                     mapping={"jawOpen": "/avatar/parameters/JawOpen"})
osc_m.inject({}, BS, True)
data, _ = rx2.recvfrom(65536)
msgs = [m.message for m in OscPacket(data).messages]
ck(f"(e) 映射模式只发映射项 ({msgs[0].address})",
   len(msgs) == 1 and msgs[0].address == "/avatar/parameters/JawOpen")
rx2.close()

# (f) 工厂 + StepResult 双输出空间（单趟管线）
ck("(f) create_output('vts') → VTSOutput", isinstance(create_output("vts"), VTSOutput))
try:
    create_output("xxx")
    ck("(f) 未知 kind raise", False)
except ValueError:
    ck("(f) 未知 kind raise ValueError", True)
f_phone = Frame(bs={"jawOpen": 0.1, "mouthSmileLeft": 0.2}, rot=(5.0, 0.0, 0.0))
pl = core.Pipeline(core.PipelineConfig(gain=1.4, emotion_gains=_Z))
res = pl.step(f_phone)
ck(f"(f) StepResult 双空间: params {len(res.params)} + bs {len(res.bs)}",
   len(res.params) > 0 and len(res.bs) > 0)
ck(f"(f) emotions 向量在结果里（{sorted(res.emotions)}）", len(res.emotions) == 5)
ck(f"(f) 头旋转直传 ParamAngleX=5.0 (={res.params.get('ParamAngleX')})",
   abs(res.params.get("ParamAngleX", 0) - 5.0) < 1e-9)

print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
