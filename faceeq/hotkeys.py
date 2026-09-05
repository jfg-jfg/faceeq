"""情绪 → VTS 热键触发：配置消毒 + 触发判定（纯函数，smoke 可测）。

在连续 EQ 之上补 on/off 事件层：检测情绪越过阈值且冷却结束 → 触发目标热键
（VTS Expression/贴纸/动作）。典型用途：大笑→贴纸特效、怒→切换表情。
触发决策在 worker 逐帧调用 decide_triggers；发射动作由 VTSOutput.trigger_hotkey 做。
"""
import json
import os

HOTKEY_TRIGGERS_FILE = "hotkey_triggers.json"

_VALID = {"enabled", "threshold", "cooldown", "hotkey_id", "hotkey_name"}


def sanitize_trigger_config(raw, valid_emotions):
    """{情绪: 配置} 消毒：情绪限定白名单、数值钳范围、未知键丢弃。"""
    out = {}
    for e, c in (raw or {}).items():
        if e not in valid_emotions or not isinstance(c, dict):
            continue
        clean = {k: v for k, v in c.items() if k in _VALID}
        try:
            clean["enabled"] = bool(clean.get("enabled", False))
            clean["threshold"] = max(0.05, min(1.0, float(clean.get("threshold", 0.8))))
            clean["cooldown"] = max(0.5, min(600.0, float(clean.get("cooldown", 5.0))))
        except (TypeError, ValueError):
            continue
        hid = clean.get("hotkey_id")
        clean["hotkey_id"] = int(hid) if hid is not None else None
        out[e] = clean
    return out


def load_trigger_config(path=HOTKEY_TRIGGERS_FILE, valid_emotions=()):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    return sanitize_trigger_config(raw, valid_emotions)


def save_trigger_config(cfg, path=HOTKEY_TRIGGERS_FILE):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def decide_triggers(emo: dict, cfgs: dict, last_fire: dict, now: float):
    """返回本次应触发的 (hotkey_id, 情绪) 列表。纯函数、无副作用。

    emo: 当前情绪向量；cfgs: sanitize 后的触发配置；last_fire: {情绪: 上次触发时刻}。
    条件：启用 + 情绪值 ≥ 阈值 + 距上次触发 ≥ 冷却 + 配置了热键 id。
    """
    fired = []
    for e, c in (cfgs or {}).items():
        if not c or not c.get("enabled") or c.get("hotkey_id") is None:
            continue
        v = (emo or {}).get(e, 0.0)
        if v < c.get("threshold", 0.8):
            continue
        if now - last_fire.get(e, float("-inf")) < c.get("cooldown", 5.0):
            continue
        fired.append((c["hotkey_id"], e))
    return fired
