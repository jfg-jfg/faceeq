# 校准与 profile（FaceEQ）

FaceEQ 默认用一套通用增益。但**检测器对不同脸/设备/光照/人种读数差异很大**——同一
嘴角下垂，张三的面捕读 0.4，李四只读 0.1。校准就是**按你的脸测一遍**，让每个 AU（动作单元）
的增益匹配你，而不是用别人猜的值。

> v0.2.0 起 EQ 作用在 blendshape 空间，但 signals 永远吃**原始读数**——校准逻辑完全不变。
> 校准前把面捕设备**固定好**（支架）：手持时头和设备一起动，读数会失真。

## 跑校正向导

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe probes\calibrate.py
```

流程（11 步，约 2 分钟）——**单窗口**：左侧状态区（进度 / 收流状态 / `live xxx` 实时值 / 消息）
+ 右侧 **PIL 渲染的中英文文字提示面板**（大字动作指令，如「嘴角上扬（大笑）/ mouth corners UP」）。
1. 每个 AU：读右侧中英文指令 → 照着做并**保持** → 看左侧 `live xxx` 确认在爬 → 按
   **空格**采样 ~1 秒 → 自动下一个。
   - 按键：`SPACE` 采样当前 AU；`ESC` 跳过当前（该 AU 不判死，用默认增益 1.0）；`q` 退出。
2. 跑完写两个文件：
   - `profiles/calibration.json` —— 你的 profile（引擎读这个）；
   - `profiles/calibration_result.txt` —— 人读报告，与 profile 同目录（每 AU 的
     neutral/max/delta/gain + dead/skipped 列表 + 脏 neutral/负 delta 警告）。

`--out 路径`：改 profile 输出位置。
（UI 演进：早期用 Live2D Haru 当 AU 示范，精度不够——browIn/browUp 同参、press/sneer 无参；
第二版 cv2 自绘方向箭头仍不直观；然后 PIL 中英文文字面板；v0.2.0 起 tkinter 窗口、彻底去 cv2。）

## 跑 FaceEQ（profile 自动）

```bash
PYTHONUTF8=1 .venv\Scripts\python.exe main.py --input phone --output vts
```

**首跑自动校准**：没传 `--profile` 时，main.py 自动找 `profiles/calibration.json`——有就直接用；
**没有（首次使用）会自动启动校正向导**，校准完再继续跑。所以第一次 `main.py` = 校准 + 运行，一条命令。

- `--recalibrate`：重跑校正向导（覆盖现有 profile），适合换面捕源/换脸/重测。
- `--legacy`：强制用硬编码默认、不找 profile（调试/对比）。
- `--profile 路径`：指定别的 profile。
- `--gain`/`--smooth`/`--happy` 等 CLI 仍覆盖 profile（**CLI > profile > 代码默认**）。

启动会打印 `[profile] 已加载 ...：au_gains 激活（N 个非 1.0）`。

## profile 里有什么

```json
{
  "schema_version": 1,
  "au_gains": { "smile": 0.64, "frown": null, ... },   // 每 AU 归一化增益
  "neutral":  { "smile": 0.002, ... },                 // 你的 neutral 基线
  "captures": { "smile": {"neutral":..,"max":..,"delta":..,"gain":..}, ... },
  "global_gain": null, "smooth": null, "emotion_gains": null,  // 可手填（passthrough）
  "demographic": null
}
```

- **`au_gains`**：进情绪公式前，先把原始读数**减去 neutral 基线**再**乘增益**，把你的 max 归一到
  `target_delta`(0.5)（先扣中性，避免高压基线被放大）。`null` = 该 AU 在你脸上读不到（dead）。
- **死搭档重分配**：dead 的 AU 不只"按 1.0 忽略"——它会把情绪公式里的权重**让给活搭档**。如
  `press` 死 → `angry` 全归 `browDn`（不再被 0.5 稀释）；`eyeWide`+`browUp` 死 → `surprised` 全靠
  `jawOpen` 达满量程。所以即便多数 AU 死，活情绪仍能达正常强度。
- **passthrough 三个**（`global_gain`/`smooth`/`emotion_gains`）：校准不测这些（它们是品味/模型
  旋钮，非 per-face 量），向导写 `null`，你可以手填进 JSON，或继续用 CLI 覆盖。

## 判读：dead AU

报告里 `dead` 表示该 AU 在你脸上 delta≤0.05（检测器读不到）。**普通 RGB 追踪对细微 AU
（嘴角下垂 AU15、内眉抬 AU1、皱鼻 AU9）容易欠读**——这是检测器/硬件限制，不是你做不到位，
也不是增益能救的（增益只会放大噪声）。iPad TrueDepth 实测能读这些 AU（撇嘴 sad 0.82、
皱鼻 disgust 0.64，见 acceptance-sprint1.md）；VSeeFace 等 RGB 追踪器介于两者之间，
以你校准的实测为准。dead AU 存 `null`，引擎忽略，不会误放大噪声。

报告里的 `skipped` 是另一回事：校准时按 `ESC` 跳过的 pose——「没测」≠「测不到」，这些 AU
**不判死**、用默认增益 1.0；想要 per-face 增益就重跑校准补测。

## 原理

`signals_with_raw(bs, calib)`：raw 永远是**未增益**的真检测读数；`calib=None` 走 legacy
（硬编码默认，含 `SAD_FROWN_GAIN`/`SAD_BROWIN_GAIN`），给定（profile.Calib：gains+neutral+dead+
target_delta+emotion_scale）则：
1. `gained = (raw − neutral) · gain`（先扣中性基线，避免高压基线被放大）；
2. 死搭档重分配（dead AU 把情绪权重让给活搭档）；
3. **量程统一**：除以 `emotion_scale[e]`（该情绪在"你 max 脸"时的值），使各活情绪都落到 0..1、
   跨情绪可比——boost/dominant 不再偏向某个高量程情绪。

`emotion_scale` 由 `compute_emotion_scale(dead, target_delta)` 在加载 profile 时按 `_MAX_POSE`
（每情绪的 max 脸各 AU 取 target_delta/0、死 AU 置 0）预算。两个硬编码 `SAD_*_GAIN` 被 profile 取代。
无 profile（`--legacy` 或没校准）= 逐字等于硬编码默认，不回归。

## 报告里的警告

- `⚠ neutral 偏高`：某些 AU 在 neutral 时读数就偏高（你 neutral 没放松，或天生肌肉张力）→
  影响增益可靠性，**放松脸重测 neutral**。
- `⚠ 做表情时读数反而更低`：某 pose 读数 < neutral（做反了，或 neutral 脏）→ 重测该 pose / neutral。
