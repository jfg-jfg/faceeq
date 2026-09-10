"""生成 eq-demo-long.mp4 的配音版（B站解说）→ assets/eq-demo-long-narrated.mp4。

背景: 用户反馈原版「看不出来区别而且太快了」→ 0.5× 慢放 + 按表情段配音解说。
台本取自 docs/marketing-kit.md B站脚本(钩子 + 逐情绪要点), 对齐慢放后分段(秒):
  中性 0-3.2 | 大笑 3.2-8.0 | 撇嘴 8.0-12.8 | 皱鼻 12.8-17.2 | 皱眉 17.2-22.0 | 眨眼 22.0-25.2

TTS: 优先 edge-tts(zh-CN-XiaoxiaoNeural, 需网络); 失败回退 Windows SAPI(Microsoft Huihui, 离线)。
视频编码用 mpeg4(本机 ffmpeg 的 libx264/h264_mf 已知损坏, 见 probes/make_compare_gif.py)。

用法:
    .venv/Scripts/python.exe probes/make_narrated_demo.py
产物:
    assets/eq-demo-long-narrated.mp4      成片(25.2s, 含解说音轨)
    assets/vo/line_N.<ext>                每条解说的中间音频(可单独复用/重录)
"""
import asyncio
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "eq-demo-long.mp4")
OUT = os.path.join(ROOT, "assets", "eq-demo-long-narrated.mp4")
VO_DIR = os.path.join(ROOT, "assets", "vo")
SLOW = 2.0                      # 0.5× 慢放
DUR = round(12.6 * SLOW, 1)     # 25.2s

# (起点秒, 段末秒, 台词) —— 段末用于校验台词不越过下一段
LINES = [
    (0.4, 7.9, "同样的面捕数据，右边多了一层表情均衡器，它叫 Face EQ。"),
    (8.3, 12.7, "撇嘴的悲伤，被独立放大。"),
    (13.0, 17.1, "厌恶也一样，单独增强。"),
    (17.4, 21.9, "怒气单独调，情绪之间不打架。"),
    (22.2, 25.1, "眨眼保持一比一透传。"),
]

VOICE = "zh-CN-XiaoxiaoNeural"
SAPI_VOICE = "Microsoft Huihui Desktop"


def tts_edge(text: str, path: str) -> None:
    import edge_tts

    async def run():
        com = edge_tts.Communicate(text, VOICE, rate="-4%")
        await com.save(path)

    asyncio.run(run())


def tts_sapi(text: str, path_mp3: str) -> str:
    """SAPI 只能写 wav; 返回实际生成的 wav 路径。"""
    wav = path_mp3[:-4] + ".wav"
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SelectVoice('{SAPI_VOICE}');$s.Rate = -1;"
        f"$s.SetOutputToWaveFile('{wav}');"
        f"$s.Speak('{text}');$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return wav


def ffprobe_dur(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main():
    os.makedirs(VO_DIR, exist_ok=True)
    files = []
    use_edge = True
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        use_edge = False
        print("[vo] edge-tts 未安装 → 回退 Windows SAPI (Huihui)。"
              "要更自然的音色: .venv/Scripts/python.exe -m pip install edge-tts")

    for i, (t0, t1, text) in enumerate(LINES):
        ext = "mp3" if use_edge else "wav"
        path = os.path.join(VO_DIR, f"line_{i}.{ext}")
        if use_edge:
            tts_edge(text, path)
        else:
            path = tts_sapi(text, path)
        d = ffprobe_dur(path)
        end = t0 + d
        flag = "OK" if end <= t1 else f"⚠ 超段 {end - t1:.1f}s"
        print(f"[vo] line_{i} @{t0:>5.1f}s  {d:4.1f}s  ({flag})  {text}")
        files.append((t0, path))

    # —— 合成: 0.5× 慢放 + 各条 adelay + amix(不归一化) + 补齐到全片长 ——
    inputs = ["-i", SRC]
    for _, p in files:
        inputs += ["-i", p]
    ms = [str(int(t0 * 1000)) for t0, _ in files]
    fc = "[0:v]setpts=%.1f*PTS[v];" % SLOW
    fc += "".join(f"[{i + 1}:a]adelay={m}:all=1[d{i}];"
                  for i, m in enumerate(ms))
    fc += "".join(f"[d{i}]" for i in range(len(files)))
    fc += (f"amix=inputs={len(files)}:normalize=0,"
           f"apad=whole_dur={DUR}[a]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", fc,
           "-map", "[v]", "-map", "[a]",
           "-c:v", "mpeg4", "-q:v", "3", "-c:a", "aac", "-b:a", "128k", OUT]
    print("[mux]", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"[done] {OUT}  ({ffprobe_dur(OUT):.1f}s)")


if __name__ == "__main__":
    main()
