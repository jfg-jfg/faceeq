"""手机 UDP 面捕（iFacialMocap/MeowFace 兼容）的解析与管线 smoke（无网络、无 GL）。
跑：PYTHONUTF8=1 .venv/Scripts/python.exe probes/phone_smoke.py

钉死：官方样例封包解析（名称映射/百分比值/欧拉轴）、v2 `&` 分隔容忍、坏包返回 None；
base_map 手机路径（rot/eye 直取、无 lms 也出参数）；engine 端到端出情绪。
样例封包取自 iFacialMocap 官方开发者页（for-developer），改了几个数值让断言可读。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq import engine
from faceeq.capture import Frame, parse_phone_packet
from faceeq.mapping import base_map

failures = []


def ck(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        failures.append(name)


# 官方文档样例封包（数值微调；名称/结构逐字保留）
SAMPLE = ("mouthSmile_R-0|eyeLookOut_L-0|eyeLookIn_L-0|eyeLookOut_R-0|eyeLookIn_R-0|"
          "eyeWide_L-15|browDown_L-1|browDown_R-2|browOuterUp_L-1|browOuterUp_R-3|"
          "browInnerUp-20|noseSneer_L-0|noseSneer_R-0|jawOpen-10|jawRight-0|jawLeft-0|"
          "jawForward-0|mouthFunnel-0|mouthPucker-0|mouthClose-8|mouthRollLower-0|"
          "mouthRollUpper-0|mouthShrugLower-0|mouthShrugUpper-0|mouthPress_L-0|"
          "mouthPress_R-0|mouthStretch_L-0|mouthStretch_R-0|mouthFrown_L-11|"
          "mouthFrown_R-13|mouthUpperUp_L-1|mouthUpperUp_R-2|mouthLowerDown_L-3|"
          "mouthLowerDown_R-4|mouthSmile_L-5|mouthDimple_L-0|mouthDimple_R-0|"
          "cheekPuff-0|cheekSquint_L-0|cheekSquint_R-11|mouthLeft-1"
          "|=head#-21.488958,-6.038993,-6.6019735,-0.030653415,-0.10287084,-0.6584072"
          "|rightEye#6.0297494,2.4403017,0.25649446|leftEye#6.034903,-1.6660284,-0.17520553|")

# (a) 解析：_L/_R → Left/Right；0~100 → 0..1
p = parse_phone_packet(SAMPLE.encode("utf-8"))
ck("(a) 封包可解析", p is not None)
bs = p["bs"]
ck(f"(a) mouthSmile_R→Right=0.0 (={bs.get('mouthSmileRight')})",
   abs(bs.get("mouthSmileRight", -1) - 0.0) < 1e-9)
ck(f"(a) mouthSmile_L→Left=0.05 (={bs.get('mouthSmileLeft')})",
   abs(bs.get("mouthSmileLeft", -1) - 0.05) < 1e-9)
ck(f"(a) 百分比换算 browInnerUp=0.20 (={bs.get('browInnerUp')})",
   abs(bs.get("browInnerUp", -1) - 0.20) < 1e-9)
ck("(a) mouthFrownLeft=0.11 存在", abs(bs.get("mouthFrownLeft", -1) - 0.11) < 1e-9)
ck("(a) eyeWideLeft 存在（手机源有该通道，surprised 关键输入）",
   abs(bs.get("eyeWideLeft", -1) - 0.15) < 1e-9)

# (b) 头部旋转：欧拉 (X=.pitch, Y=yaw, Z=roll)
yaw, pitch, roll = p["rot"]
ck(f"(b) rot yaw=eY={yaw:.3f}", abs(yaw - (-6.038993)) < 1e-4)
ck(f"(b) rot pitch=eX={pitch:.3f}", abs(pitch - (-21.488958)) < 1e-4)
ck(f"(b) rot roll=eZ={roll:.3f}", abs(roll - (-6.6019735)) < 1e-4)

# (c) 眼球：欧拉→归一 -1..1（X=垂直、Y=水平，÷40°）
lx, ly, rx, ry = p["eye"]
ck(f"(c) eye lx≈-0.042 (={lx:.4f})", abs(lx - (-1.6660284 / 40)) < 1e-3)
ck(f"(c) eye ly≈-0.151 (={ly:.4f})", abs(ly - (-6.034903 / 40)) < 1e-3)
ck(f"(c) eye rx≈0.061 (={rx:.4f})", abs(rx - (2.4403017 / 40)) < 1e-3)

# (d) v2 `&` 分隔 + 负值容忍；坏包 → None
p2 = parse_phone_packet(b"eyeBlink_L&50|jawOpen&25|=head#1,2,3,0,0,0|")
ck(f"(d) v2 & 分隔: eyeBlinkLeft=0.5 (={p2['bs'].get('eyeBlinkLeft') if p2 else None})",
   p2 is not None and abs(p2["bs"].get("eyeBlinkLeft", -1) - 0.5) < 1e-9)
ck("(d) 垃圾封包→None", parse_phone_packet(b"\x00\x01not-a-packet") is None)
ck("(d) 空封包→None", parse_phone_packet(b"") is None)

# (e) base_map 手机路径：无 lms 也出全部参数；rot/eye 直取
f_phone = Frame(bs=bs, rot=(10.0, -5.0, 3.0), eye=(0.2, -0.1, 0.2, -0.1))
params = base_map(f_phone)
for k in ["ParamEyeLOpen", "ParamMouthForm", "ParamBrowLY", "ParamMouthOpenY",
          "ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamEyeBallX", "ParamEyeBallY"]:
    ck(f"(e) 手机帧出 {k}", k in params)
ck(f"(e) Angle 直取=10.0 (={params.get('ParamAngleX')})",
   abs(params.get("ParamAngleX", 0) - 10.0) < 1e-9)
ck(f"(e) EyeBallX=0.2 (={params.get('ParamEyeBallX')})",
   abs(params.get("ParamEyeBallX", 0) - 0.2) < 1e-9)
ck(f"(e) EyeBallY=-0.1 (={params.get('ParamEyeBallY')})",
   abs(params.get("ParamEyeBallY", 0) + 0.1) < 1e-9)
ck("(e) 空帧→空参数（webcam 无脸/手机断流一致）", base_map(Frame()) == {})

# (f) engine 端到端：悲伤脸 blendshape（手机能读 AU15/AU1）→ sad 主导、有参数出
emo = {"happy": 0.0, "angry": 0.0, "sad": 0.0, "surprised": 0.0, "disgust": 0.0}
res = engine.process_frame(f_phone, 1.4, emo, None)
ck(f"(f) 端到端有参数（{len(res.params)} 个）", len(res.params) > 0)
ck(f"(f) sad 主导（dominant={res.dominant}）", res.dominant == "sad")
ck(f"(f) bs_params 同步产出（{len(res.bs_params)} 形状，VMC 输出空间）", len(res.bs_params) >= 20)

print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
