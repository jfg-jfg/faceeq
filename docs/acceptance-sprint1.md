# 冲刺①验收卡:手机/平板面捕方向符号 + TrueDepth 实测

> 目的:钉死 `faceeq/capture.py` 里 `_ROT_SIGN/_EYE_SIGN` 两组猜测符号(现在的值全是 +1,
> 从未拿真机验过),并实测 TrueDepth 下 sad/disgust 的真实读数——这决定 v0.2.0 的宣传口径。
> 预计 10 分钟。

## 准备(2 分钟)

1. **iPad**(Face ID 款)装 **iFacialMocap**(App Store,免费);
2. iPad 和电脑连**同一个 WiFi**;
3. 电脑查本机 IP:`Win+R` → `cmd` → `ipconfig` → 找「IPv4 地址」(如 192.168.1.23);
4. 电脑上启动探针(仓库根目录):

   ```
   PYTHONUTF8=1 .venv\Scripts\python.exe -u probes\phone_sign_probe.py
   ```

   看到「监听 UDP 49983,等 app 数据…」即就绪。(探针运行期间别开 FaceEQ GUI,会抢端口)
5. iPad 打开 iFacialMocap → 设置里填电脑 IP + 端口 **49983** → 开始发送。

探针打印行长这样(数字随你的脸变):

```
yaw  +20.0 pitch  -12.5 roll   +4.0 | eyeX-0.04/+0.06 eyeY-0.15/-0.15 | browIn0.30 … sad0.03 disg0.22
```

## A. 头部符号(动作要干脆,回到中间再做下一个)

| # | 动作 | 看哪个值 | 记录(+ 还是 −,大概数值) |
|---|---|---|---|
| A1 | 水平**左**转(自己向左) | yaw | ______ |
| A2 | 水平**右**转 | yaw | ______ |
| A3 | **低头** | pitch | ______ |
| A4 | **抬头** | pitch | ______ |
| A5 | 头向**左**肩歪 | roll | ______ |
| A6 | 头向**右**肩歪 | roll | ______ |

## B. 眼球符号(头别动,只动眼睛)

| # | 动作 | 看哪个值 | 记录 |
|---|---|---|---|
| B1 | 双眼看**左** | eyeX(两个数) | ______ |
| B2 | 双眼看**右** | eyeX | ______ |
| B3 | 双眼看**上** | eyeY | ______ |
| B4 | 双眼看**下** | eyeY | ______ |

## C. TrueDepth 表情实测(核心!)

每个表情保持 2 秒,记探针行尾的**峰值**:

| # | 表情 | 预期谁动 | 记录峰值 |
|---|---|---|---|
| C1 | **撇嘴**(嘴角向下,不皱眉) | frown↑,sad↑? | frown ____ sad ____ |
| C2 | **皱眉 + 内眉抬**(难过眉) | browIn/browDn↑,sad↑? | browIn ____ sad ____ |
| C3 | **皱鼻 + 抬上唇**(厌恶脸) | sneer↑,disg↑? | sneer ____ disg ____ |
| C4 | 微笑(对照) | smile↑,happy↑ | smile ____ happy ____ |

## D.(可选,强烈建议)VTS 端到端

关掉探针 → 开 FaceEQ GUI(`gui.py`,输入源选「📱 手机 UDP」)→ 连 VTS:
看模型**头的转向、眼球方向**跟你是否一致(镜像不镜像),**sad/disgust 表情**在模型上出不出得来。

## 回填

把 A1–B4 的符号、C1–C4 的峰值抄给我(拍照/打字都行)。我来判定:
- 哪几个符号要翻 → 改 `_ROT_SIGN/_EYE_SIGN`,smoke 补对应断言;
- C1–C3 峰值 ≥0.3 → 宣传语保留「TrueDepth 读到 sad/disgust」;<0.1 → 口径改保守,并考虑调 signals 权重。
