# 发布清单（Release Checklist）

每次发版照此走。产物形态：`dist/FaceEQ/` 绿色目录 → zip 分发。

## 1. 发布前

- [ ] 五个 smoke 全过：`probes/{profile_smoke,phone_smoke,output_smoke,gui_smoke,voice_smoke}.py`
- [ ] 真机手测：webcam 源 + VTS 输出完整跑一遍（校准→开始→拖滑块→预设）
- [ ] 待验收项确认：手机源方向符号（`_ROT_SIGN/_EYE_SIGN`）、Warudo/VMC 对接
- [ ] 版本号：`faceeq/__init__.py` 加 `__version__`（首次 v0.1.0）；CHANGELOG 记录变更

## 2. 打包

- [ ] `.venv/Scripts/python.exe -m pip install -r requirements.txt pyinstaller`
- [ ] `PYTHONUTF8=1 .venv/Scripts/python.exe probes/build_release.py`
- [ ] 产物自检：`dist/FaceEQ/FaceEQ.exe` 存在；目录含 `models/face_landmarker.task`、
      `presets/builtin/`、`custom_expressions.json`
- [ ] 干净环境语义冒烟：双击 exe → 主窗口出现 → 无 profile 时出首启动引导 →
      信号监视器动 → 退出无残留进程
- [ ] 杀软误报检查（Windows Defender + 一款第三方）；被误报时在 README「排错」加白名单指引，
      长期解法是代码签名证书（付费，暂缓）

## 3. GitHub Release

- [ ] `git tag v0.1.0 && git push --tags`
- [ ] Release notes：功能清单 + 已知限制（webcam sad/disgust 需手机源；rig 上限声明）+ 升级说明
- [ ] 上传 `FaceEQ-v0.1.0-win64.zip`（dist/FaceEQ 打 zip）
- [ ] README 徽章/下载链接指向最新 Release

## 4. 渠道分发

- [ ] **itch.io**：建项目页（截 3 图：主面板/塑造矩阵/信号监视器；30s 前后对比 GIF），
      下载指向 GitHub Release 或直接传 zip，标签 `vtuber` / `vtube-studio` / `live2d`
- [ ] **VTS 官方 Plugins Wiki**：按
      [Plugins 页](https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins) 的指引提交 PR
      申请收录（收录硬指标：user friendly + good manual——引 quickstart 与 outputs 文档）
- [ ] **Reddit**：r/vtubertech 发 "I made a free expression emotion EQ for VTS/Live2D" 帖
      （附对比 GIF + 诚实 rig 上限声明）
- [ ] **B站**：教程视频脚本要点——安装三步 / 校准 11 表情 / ★ 预设试效果 / 高级塑造矩阵 /
      手机面捕（可选章节）；简介放 GitHub 链接
- [ ] Emiliana 的 [Best VTuber Software gist](https://gist.github.com/emilianavt/cbf4d6de6f7fb01a42d4cce922795794)
      申请收录（有用户量后再做）

## 5. 发布后

- [ ] 盯 GitHub Issues / B站评论，高频问题回写 docs FAQ
- [ ] 记录下载量/Star 作为是否上 Steam 付费的决策依据（门槛自定，如 1k 下载 + 50 star）

## 已知发布风险

- mediapipe 打包体积大（~200-400MB onedir）——接受；单文件模式易碎不要改
- 杀软误报（Python GUI 常见）——文档指引 + 未来签名
- VTS 鉴权弹窗在 --windowed 无控制台下正常（VTS 侧弹窗，非控制台）
