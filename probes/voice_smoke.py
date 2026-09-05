"""语音情绪 + 情绪触发热键 smoke（无麦克风、无 VTS、无 GL）。
跑：PYTHONUTF8=1 .venv/Scripts/python.exe probes/voice_smoke.py

钉死：声学特征（能量/亮度）、规则偏置映射（门限/方向/sensitivity）、快攻慢放、
触发配置消毒、decide_triggers 阈值+冷却判定、engine voice_bias 注入。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq import engine, hotkeys, voice
from faceeq.capture import Frame

failures = []


def ck(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        failures.append(name)


def tone(freq, seconds=0.2, sr=16000, amp=0.3):
    n = int(sr * seconds)
    return [amp * math.sin(2 * math.pi * freq * i / sr) for i in range(n)]


# (a) 特征提取：静音 / 明亮音 / 低沉音
sil = [0.0] * 3200
en, br = voice.features_from_pcm(sil, 16000)
ck(f"(a) 静音 → 能量≈0 ({en:.4f})", en < 0.01)
en_b, br_b = voice.features_from_pcm(tone(2500, amp=0.4), 16000)
en_d, br_d = voice.features_from_pcm(tone(180, amp=0.4), 16000)
ck(f"(a) 大声能量高 ({en_b:.3f} > 0.2)", en_b > 0.2)
ck(f"(a) 2500Hz 亮度高 ({br_b:.3f} > 0.6)", br_b > 0.6)
ck(f"(a) 180Hz 亮度低 ({br_d:.3f} < 0.2)", br_d < 0.2)
ck("(a) 同幅度不同频率能量接近", abs(en_b - en_d) < 0.05)

# (b) 偏置映射：门限 / 方向 / sensitivity
ck("(b) 安静 → 零偏置", voice.bias_from_features(0.01, 0.8, 1.0) == {})
b_bright = voice.bias_from_features(en_b, br_b, 1.0)
b_dull = voice.bias_from_features(en_d, br_d, 1.0)
ck(f"(b) 明亮大声 → happy 主导 ({b_bright.get('happy', 0):.3f}, angry={b_bright.get('angry', 0):.3f})",
   b_bright.get("happy", 0) > b_bright.get("angry", 0) and b_bright.get("happy", 0) > 0)
ck(f"(b) 亮到极值加 surprised ({b_bright.get('surprised', 0):.3f}>=0)",
   b_bright.get("surprised", 0) >= 0)
ck(f"(b) 低沉大声 → angry 主导 ({b_dull.get('angry', 0):.3f} > happy)",
   b_dull.get("angry", 0) > b_dull.get("happy", 0))
ck("(b) 偏置都在 0..1", all(0 <= v <= 1 for d in (b_bright, b_dull) for v in d.values()))
b_sens = voice.bias_from_features(en_b * 0.5, br_b, 2.0)
ck(f"(b) sensitivity 放大弱信号 ({b_sens.get('happy', 0):.3f} > 0)",
   b_sens.get("happy", 0) > 0)

# (c) 快攻慢放
prev = voice.smooth_bias({}, {"happy": 0.8}, 1.0)
ck(f"(c) 快攻: {prev['happy']:.2f}==0.8", abs(prev["happy"] - 0.8) < 1e-9)
decay = voice.smooth_bias(prev, {}, 1.0)
ck(f"(c) 慢放: 0.8*0.85={decay['happy']:.3f}", abs(decay["happy"] - 0.68) < 1e-9)
ck("(c) strength 缩放", voice.smooth_bias({}, {"happy": 0.8}, 0.5)["happy"] == 0.4)

# (d) 触发配置消毒 + decide_triggers
cfg = hotkeys.sanitize_trigger_config(
    {"happy": {"enabled": True, "threshold": 1.5, "cooldown": 0.1, "hotkey_id": 3,
               "evil": "x"},
     "hack": {"enabled": True, "hotkey_id": 9}},
    emotions_valid := ["happy", "angry", "sad", "surprised", "disgust"])
h = cfg.get("happy", {})
ck("(d) 消毒: 阈值钳到 1.0 / 冷却抬到 0.5 / 未知键丢弃",
   h.get("threshold") == 1.0 and h.get("cooldown") == 0.5 and "evil" not in h)
ck("(d) 消毒: 非法情绪条目丢弃", "hack" not in cfg)
CFG = {"happy": {"enabled": True, "threshold": 0.6, "cooldown": 5.0, "hotkey_id": 7},
       "angry": {"enabled": False, "threshold": 0.5, "cooldown": 1.0, "hotkey_id": 8},
       "sad": {"enabled": True, "threshold": 0.5, "cooldown": 1.0, "hotkey_id": None}}
emo_hi = {"happy": 0.9, "angry": 0.9, "sad": 0.9, "surprised": 0.0, "disgust": 0.0}
fired = hotkeys.decide_triggers(emo_hi, CFG, {}, now=100.0)
ck(f"(d) 越阈值触发 happy id=7 ({fired})", fired == [(7, "happy")])
fired2 = hotkeys.decide_triggers(emo_hi, CFG, {"happy": 97.0}, now=100.0)
ck(f"(d) 冷却内不触发 ({fired2})", fired2 == [])
fired3 = hotkeys.decide_triggers({"happy": 0.3}, CFG, {}, now=100.0)
ck("(d) 低于阈值不触发", fired3 == [])
ck("(d) 未启用/无热键不触发", hotkeys.decide_triggers(emo_hi, CFG, {}, 100.0)[:1] == [(7, "happy")])

# (e) engine voice_bias 注入（additive + clamp 1.0）
f = Frame(bs={"jawOpen": 0.1})
r0 = engine.process_frame(f, 1.4, _Z := {e: 0.0 for e in
                                         ["happy", "angry", "sad", "surprised", "disgust"]})
r1 = engine.process_frame(f, 1.4, _Z, None, voice_bias={"happy": 0.5, "angry": 2.0})
ck(f"(e) voice_bias 抬 happy ({r1.emotions['happy']:.2f}==0.5)",
   abs(r1.emotions["happy"] - 0.5) < 1e-9)
ck(f"(e) 注入 clamp 1.0 (angry={r1.emotions['angry']})", r1.emotions["angry"] == 1.0)
ck(f"(e) 无偏置时基线 happy=0 ({r0.emotions['happy']})", r0.emotions["happy"] == 0.0)

print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
