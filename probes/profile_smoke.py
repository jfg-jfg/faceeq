"""profile + emotions.calib 的回归 / 重分配 smoke（无摄像头、无 GL）。
跑：PYTHONUTF8=1 .venv/Scripts/python.exe probes/profile_smoke.py

钉死：calib=None 逐字==今天；calib 激活时中性扣除、死搭档重分配、load/resolve 优先级；
负增益（persona 抑制）压参数向中性 + 耦合停摆 + eg 入口钳制。
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faceeq import emotions, engine, profile
from faceeq.capture import Frame

_BSNAMES = [
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight",
    "eyeSquintLeft", "eyeSquintRight", "browDownLeft", "browDownRight",
    "mouthPressLeft", "mouthPressRight", "browInnerUp", "browOuterUpLeft",
    "browOuterUpRight", "eyeWideLeft", "eyeWideRight", "noseSneerLeft",
    "noseSneerRight", "jawOpen"]


def bs(**kw):
    d = {n: 0.0 for n in _BSNAMES}
    d.update(kw)
    return d


def calib(gains, neutral=None, dead=()):
    """快捷 Calib：gains 缺失键→1.0；neutral 默认全 0。"""
    full = {k: gains.get(k, 1.0) for k in profile.RAW_KEYS}
    return profile.Calib(gains=full, neutral=neutral or {}, dead=set(dead))


failures = []


def ck(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        failures.append(name)


SAD_BS = bs(mouthFrownLeft=0.1, mouthFrownRight=0.1, browInnerUp=0.05)   # frown=0.1 browIn=0.05
BROW_BS = bs(browDownLeft=0.3, browDownRight=0.3)                        # browDn=0.3 press=0
JAW_BS = bs(jawOpen=0.5)                                                 # jaw=0.5

# (a)+(c) 无 profile = legacy；sad 逐字等于今天公式
emo_none, raw = emotions.signals_with_raw(SAD_BS)
indep_sad = max(0.0, min(1.0,
    0.6 * min(1.0, 0.1 * emotions.SAD_FROWN_GAIN)
    + 0.4 * min(1.0, 0.05 * emotions.SAD_BROWIN_GAIN) - 0.0))
ck(f"(a) 无 profile==legacy, sad={emo_none['sad']:.3f}", abs(emo_none["sad"] - indep_sad) < 1e-12)
ck("(c) raw 永不增益 (frown=0.1)", abs(raw["frown"] - 0.1) < 1e-12)

# (b1) calib 增益（neutral=0）：sad 上升
emo_g, _ = emotions.signals_with_raw(SAD_BS, calib({"frown": 8, "browIn": 6}))
ck(f"(b1) calib gains 抬 sad ({emo_g['sad']:.3f} > {emo_none['sad']:.3f})",
   emo_g["sad"] > emo_none["sad"])

# (b2) 中性扣除：neutral frown=0.05 → gained frown=(0.1-0.05)*8=0.4，sad 比 不扣(0.8) 低
emo_n, _ = emotions.signals_with_raw(SAD_BS, calib({"frown": 8, "browIn": 6}, neutral={"frown": 0.05}))
ck(f"(b2) 中性扣除让 sad 更低 ({emo_n['sad']:.3f} < {emo_g['sad']:.3f})",
   emo_n["sad"] < emo_g["sad"])

# (b3) 死搭档重分配：angry。press 死 → angry=browDn_g（满 0.30）；press 活 → 0.15
emo_bd, _ = emotions.signals_with_raw(BROW_BS, calib({"browDn": 1.0}, dead={"press"}))
emo_bd2, _ = emotions.signals_with_raw(BROW_BS, calib({"browDn": 1.0}))
ck(f"(b3) press 死→angry 重分配 ({emo_bd['angry']:.3f} > press 活 {emo_bd2['angry']:.3f})",
   emo_bd["angry"] > emo_bd2["angry"] + 0.1)

# (b4) surprised：eyeWide+browUp 死 → jaw 独撑达满量程（jaw=0.5→(0.5-0.3)/0.2=1.0）
emo_jaw, _ = emotions.signals_with_raw(JAW_BS, calib({"jawOpen": 1.0}, dead={"eyeWide", "browUp"}))
ck(f"(b4) eye/brow 死→surprised 靠 jaw 达 1.0 (={emo_jaw['surprised']:.3f})",
   abs(emo_jaw["surprised"] - 1.0) < 1e-9)

# (b5) 同步守卫：恒等 calib（gains 全 1.0、neutral 0、dead 空）下，两引擎共享部分逐字相等
#      → 守 _happy/_disgust/_sad 及常量在 _emo_legacy/_emo_gained 不漂移；sad 允许差（gained 无 SAD_*_GAIN）
TEST_BS = bs(mouthSmileLeft=0.5, mouthSmileRight=0.5, eyeSquintLeft=0.3, eyeSquintRight=0.3,
             browDownLeft=0.4, browDownRight=0.4, mouthPressLeft=0.2, mouthPressRight=0.2,
             eyeWideLeft=0.3, eyeWideRight=0.3, jawOpen=0.5, noseSneerLeft=0.2, noseSneerRight=0.2,
             mouthFrownLeft=0.1, mouthFrownRight=0.1, browInnerUp=0.2)
e_id, _ = emotions.signals_with_raw(TEST_BS, calib({}, {}, ()))   # 恒等 calib
e_lg, _ = emotions.signals_with_raw(TEST_BS)                      # legacy
for _emo in ["happy", "angry", "surprised", "disgust"]:
    ck(f"(b5) 同步守卫 {_emo}: identity==legacy ({e_id[_emo]:.4f} vs {e_lg[_emo]:.4f})",
       abs(e_id[_emo] - e_lg[_emo]) < 1e-12)
ck(f"(b5) sad 允许差（gained 无 SAD_*_GAIN）: identity={e_id['sad']:.4f} vs legacy={e_lg['sad']:.4f}",
   abs(e_id["sad"] - e_lg["sad"]) > 1e-9)

# (b6) 量程统一：emotion_scale 让各活情绪在"活 AU 都达 target_delta"时 ≈1.0（跨情绪可比）
DEAD7 = {"frown", "squint", "press", "browIn", "browUp", "eyeWide", "sneer"}  # 7 死，像真 webcam profile
TD = 0.5
es = emotions.compute_emotion_scale(DEAD7, TD)
live7 = {k: (k not in DEAD7) for k in profile.RAW_KEYS}
gmax = {k: (TD if k not in DEAD7 else 0.0) for k in profile.RAW_KEYS}   # 活 AU 都在 max
emo_sc = emotions._emo_gained(gmax, live7, TD, es)
for _e in ["happy", "angry", "surprised"]:   # 活情绪（smile/browDn/jawOpen 活）
    ck(f"(b6) 量程 {_e} @活max≈1.0 (={emo_sc[_e]:.3f})", abs(emo_sc[_e] - 1.0) < 0.02)
ck(f"(b6) sad 死情绪≈0 (={emo_sc['sad']:.3f})", emo_sc["sad"] < 0.05)

# (b7) _MAX_POSE 守卫：键集 == EMOTIONS，值里的 AU 都在 RAW_KEYS（防公式改了忘改 _MAX_POSE）
ck("(b7) _MAX_POSE 键集 == EMOTIONS", set(emotions._MAX_POSE.keys()) == set(emotions.EMOTIONS))
ck("(b7) _MAX_POSE 值里的 AU 都在 RAW_KEYS",
   all(k in profile.RAW_KEYS for e in emotions._MAX_POSE.values() for k in e))

# (f) 负增益 = persona 抑制（扑克脸）：相关参数往中性压、只抬不压的耦合停摆、eg 入口钳 [-1,1]
_Z = {e: 0.0 for e in emotions.EMOTIONS}
SMILE_BASE = {"ParamMouthForm": 0.6, "ParamEyeLSmile": 0.3, "ParamEyeRSmile": 0.3,
              "ParamMouthOpenY": 0.2}
EMO_HAPPY = {"happy": 0.8, "angry": 0.0, "sad": 0.0, "surprised": 0.0, "disgust": 0.0}
a_zero = emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, _Z)                      # 不塑造基线
a_pos = emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, {**_Z, "happy": 1.0})     # 全量夸张
a_neg = emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, {**_Z, "happy": -1.0})    # 抑制
ck(f"(f) happy 负增益压嘴笑向中性 ({a_neg['ParamMouthForm']:.3f} < 不塑造 {a_zero['ParamMouthForm']:.3f})",
   0.0 <= a_neg["ParamMouthForm"] < a_zero["ParamMouthForm"])
ck(f"(f) happy 正增益耦合抬眼笑 ({a_pos['ParamEyeLSmile']:.3f} > 基础 0.3)",
   a_pos["ParamEyeLSmile"] > 0.3)
ck(f"(f) happy 负增益停耦合（眼笑不再抬, ={a_neg['ParamEyeLSmile']:.3f}）",
   abs(a_neg["ParamEyeLSmile"] - 0.3) < 1e-9)
EMO_SMALL = {"happy": 0.2, "angry": 0.0, "sad": 0.0, "surprised": 0.0, "disgust": 0.0}
a_big = emotions.amplify(SMILE_BASE, EMO_SMALL, 1.4, {**_Z, "happy": 5.0})
a_one = emotions.amplify(SMILE_BASE, EMO_SMALL, 1.4, {**_Z, "happy": 1.0})
ck("(f) eg 入口钳制 [-1,1] (5.0 == 1.0)",
   abs(a_big["ParamMouthForm"] - a_one["ParamMouthForm"]) < 1e-12)

# (g) 塑造配置（Phase 2a）：默认==硬编码基线（no-regression 钉死）、自定义生效、序列化往返、试表情
sh_d = emotions.Shaping()
ck("(g) 默认 Shaping 输出 == amplify 无参路径",
   emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, _Z, sh_d)
   == emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, _Z))
d = emotions.shaping_to_dict(sh_d)
sh_rt = emotions.shaping_from_dict(d)
ck("(g) shaping 序列化往返输出一致（含 4 条默认耦合）",
   sh_rt is not None
   and emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, _Z, sh_rt)
   == emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, _Z, sh_d))
EG_H = {**_Z, "happy": 1.0}
out_def = emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, EG_H)          # 默认塑造
sh_cus = emotions.Shaping()                                            # 关 happy 嘴部 boost + 全部耦合
sh_cus.boosts["ParamMouthForm"] = {e: 0.0 for e in emotions.EMOTIONS}
sh_cus.couplings = []
out_cus = emotions.amplify(SMILE_BASE, EMO_HAPPY, 1.4, EG_H, sh_cus)
ck(f"(g) 自定义: 关 happy boost 后嘴笑回落 ({out_cus['ParamMouthForm']:.3f} < 默认 {out_def['ParamMouthForm']:.3f})",
   out_cus["ParamMouthForm"] < out_def["ParamMouthForm"])
ck(f"(g) 自定义: 关耦合后眼笑保持基值 (={out_cus['ParamEyeLSmile']:.3f})",
   abs(out_cus["ParamEyeLSmile"] - 0.3) < 1e-9)
sh_from_none = emotions.shaping_from_dict(None)
ck("(g) shaping_from_dict(None/空)=None→引擎用默认", sh_from_none is None)
tp, t_dom, t_ff = engine.process_frame(Frame(), 1.4, _Z, None, None, ("happy", 0.8))
ck(f"(g) 试表情: dom={t_dom} 有参数={len(tp)>0} face_found={t_ff}",
   t_dom == "happy" and len(tp) > 0 and t_ff)

# (h) 自定义复合表情（Phase 2b）：加权注入 additive+clamp、负权重压情绪、主导判定、端到端
emo0 = {"happy": 0.2, "angry": 0.0, "sad": 0.0, "surprised": 0.0, "disgust": 0.0}
EXPRS = {"害羞": {"happy": 0.3, "surprised": 0.4}}
emo1, ce_dom = emotions.apply_custom(emo0, EXPRS, {"害羞": 1.0})
ck(f"(h) additive: happy {emo1['happy']:.2f}==0.5, surprised {emo1['surprised']:.2f}==0.4",
   abs(emo1["happy"] - 0.5) < 1e-9 and abs(emo1["surprised"] - 0.4) < 1e-9)
ck(f"(h) 注入主导: dom={ce_dom}", ce_dom == "害羞")
emo2, ce_dom2 = emotions.apply_custom(emo0, EXPRS, {"害羞": 0.1})   # 弱注入不抢主导
ck(f"(h) 弱注入不主导: dom={ce_dom2}", ce_dom2 is None)
emo3, _ = emotions.apply_custom({"happy": 0.5, "angry": 0.0, "sad": 0.0,
                                 "surprised": 0.0, "disgust": 0.0},
                                {" shy": {"happy": 0.9}}, {" shy": 1.0})
ck(f"(h) clamp01: happy {emo3['happy']:.2f}<=1.0", 0.0 <= emo3["happy"] <= 1.0)
emo4, _ = emotions.apply_custom(emo0, {"冷": {"happy": -0.5}}, {"冷": 1.0})
ck(f"(h) 负权重压情绪: happy {emo4['happy']:.2f}==0 (不越到负)", emo4["happy"] == 0.0)
f_ce = Frame(bs={"jawOpen": 0.1})
p_ce, d_ce, ff_ce = engine.process_frame(f_ce, 1.4, _Z, None, None, None,
                                         EXPRS, {"害羞": 1.0})
ck(f"(h) 端到端: dom={d_ce} 参数={len(p_ce)>0} face={ff_ce}",
   d_ce == "害羞" and len(p_ce) > 0 and ff_ce)

# (d) load_profile
ck("(d) load_profile(None)=None", profile.load_profile(None) is None)
try:
    profile.load_profile("nonexistent_xyz_profile.json")
    ck("(d) 缺文件 raise", False)
except FileNotFoundError:
    ck("(d) 缺文件 raise FileNotFoundError", True)

fd, tmppath = tempfile.mkstemp(suffix=".json")
os.close(fd)
with open(tmppath, "w", encoding="utf-8") as fh:
    # frown null(→dead), squint 缺失(→1.0), browDn=60(越界→50), smile=1.43
    json.dump({"schema_version": 1,
               "au_gains": {"frown": None, "browDn": 60, "smile": 1.43},
               "neutral": {"frown": 0.01}}, fh)
p = profile.load_profile(tmppath)
ck("(d) 缺失键→1.0 (squint)", abs(p.au_gains["squint"] - 1.0) < 1e-9)
ck("(d) null→1.0 + 入 dead 集 (frown)", abs(p.au_gains["frown"] - 1.0) < 1e-9 and "frown" in p.dead)
ck("(d) 越界钳制 browDn=60→50", abs(p.au_gains["browDn"] - 50.0) < 1e-9)
ck("(d) 正常值保留 smile=1.43", abs(p.au_gains["smile"] - 1.43) < 1e-9)
ck("(d) dead 集 = null 键 {frown}", p.dead == {"frown"})
ck("(d) neutral 透传", p.neutral.get("frown") == 0.01)
os.remove(tmppath)

# (e) resolve 优先级 CLI > profile > 默认；calib 透传
args_none = NS(gain=None, smooth=None, happy=None, angry=None, sad=None,
               surprised=None, disgust=None)
r = profile.resolve(args_none, None)
ck("(e) 全 None→默认 (gain1.4/smooth0.4/happy1.0/calib None)",
   r.global_gain == 1.4 and r.smooth == 0.4 and r.emotion_gains["happy"] == 1.0
   and r.calib is None)

prof = profile.Profile(schema_version=1, au_gains={k: 1.0 for k in profile.RAW_KEYS},
                       neutral={"smile": 0.01}, captures={}, global_gain=1.8, smooth=0.6,
                       emotion_gains={"happy": 0.5}, dead={"press", "sneer"})
r2 = profile.resolve(args_none, prof)
ck("(e) profile 提供且 CLI None→用 profile (gain1.8/smooth0.6/happy0.5)",
   r2.global_gain == 1.8 and r2.smooth == 0.6 and r2.emotion_gains["happy"] == 0.5)
ck("(e) calib 透传 (gains/neutral/dead 都在)",
   r2.calib is not None and r2.calib.neutral.get("smile") == 0.01
   and r2.calib.dead == {"press", "sneer"})

args_cli = NS(gain=2.5, smooth=None, happy=-0.5, angry=None, sad=None,
              surprised=None, disgust=None)
r3 = profile.resolve(args_cli, prof)
ck("(e) CLI 胜 profile (gain 2.5>1.8, happy -0.5>0.5)",
   r3.global_gain == 2.5 and r3.emotion_gains["happy"] == -0.5)

print("\n" + ("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
