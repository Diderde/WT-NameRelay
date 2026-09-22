# WT-Tool-Experimental Version

> **本仓库是 fork，不是原项目的官方版本。** 本仓库是 [Beiku（@beikuwawa）](https://github.com/beikuwawa) 的原项目 [WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay)（beta 0.2.0）的实验性 fork，由 Diderde（[@Diderde](https://github.com/Diderde)）制作与维护，仅供个人学习与实验使用，不构成正式发布版本。

- 原始项目：[WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay)（原始作者：Beiku，原始仓库：`beikuwawa/WT-NameRelay`）
- 基线版本：beta 0.2.0
- 修改与新增代码按 GPL-3.0-only 授权，原始代码仍按原始许可授权；来源与许可分层详见 [`MODIFICATION_NOTICE.md`](MODIFICATION_NOTICE.md)。

War Thunder语音包文件名称补全、复制与语音处理工具。车组、无线电与 Bank 模块支持手动导入和目录自动检索；语音处理模块提供波形时间轴、非破坏性裁切、试听和 FFmpeg 导出。

本项目是非官方第三方工具，不包含、不提供也不分发任何游戏官方资源或官方音频，与 Gaijin Entertainment、War Thunder及其关联主体不存在授权、赞助或合作关系。

> 原始代码按 WT-NameRelay Source-Available License 1.0（[`LICENSE`](LICENSE)）授权，不是 OSI 定义的开源软件：允许个人非商业使用与同许可源码分享，禁止未经许可的商业使用、二次售卖、付费分发和捆绑收费。使用注意事项见 [`PROJECT_USAGE_NOTICE.md`](PROJECT_USAGE_NOTICE.md)。

## 环境与启动

项目验证环境：Windows、Python 3.11.5、PySide6 6.7.3、Qt 6.7.3、PyQtGraph 0.13.7、NumPy 1.26.4。

```powershell
cd "<项目目录>"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

也可以直接运行 `start.bat`（自动创建虚拟环境并安装依赖）。`start.bat` 启动前会执行三段式检查：

1. **环境与文件检查**：git / curl 工具、Python 虚拟环境、`TTS model\` 下的 GPT-SoVITS 代码、CosyVoice3 GGUF 与 GPT-SoVITS 预训练权重；
2. **按需补齐**：虚拟环境缺失时自动创建；TTS 模型资源缺失时弹出 Y/N 询问，确认后调用同目录 `download_tts_verify.bat` 下载（GitHub 浅克隆 GPT-SoVITS 代码、hf-mirror 下载 CosyVoice3 GGUF 与 25 个 GPT-SoVITS 预训练权重，支持断点续传与已完成跳过，自动适配系统代理）；
3. **启动**：全部就绪后运行主程序。

TTS 模型统一存放在 `TTS model\` 下并按模型名分目录（`GPT-SoVITS\` 含代码与权重、`CosyVoice3\` 为 GGUF 权重），该目录已加入 `.gitignore` 不入库；权重清单见 `gpt_sovits_weights_list.txt`。

正式 Windows EXE 不放入源码提交，本修改版为实验版，不提供正式发布构建；如需原始项目正式发布，请前往[原仓库 Releases](https://github.com/beikuwawa/WT-NameRelay/releases) 下载标有 `beta 0.2.0` 的 Windows x64 ZIP，并使用同页提供的 SHA-256 文件校验下载内容。

## 可选组件：vtcore（Rust 扩展）

`.vt` 工程容器、Ed25519 签名与整包校验由 Rust 扩展 `vtcore` 提供（源码在 `vtcore/`，构建后以 abi3 扩展装入虚拟环境）。

**不构建它应用照样能跑**：规范字节（`spec_hash`）自动回退到 Python 参考实现，数值与扩展路径**逐字节一致**（两侧读同一份黄金向量做测试）；但签名、`.vt` 容器、TOFU 信任库与 `.vtmanifest` 整包校验会不可用，调用时报 `vtcore_missing`。当前生效的后端在应用内「关于与许可」页末尾标明。

```powershell
# 前置：Rust 工具链（https://rustup.rs；Windows 需 MSVC 生成工具）
.\.venv\Scripts\python.exe -m pip install maturin
cd vtcore
..\.venv\Scripts\python.exe -m maturin develop --release
```

产物为 CPython 3.12+ 通用的 abi3 扩展，因此在同一份源码上换 Python 小版本无需重编。接口清单与测试方式见 `vtcore/README.md`，字节级规范见 `docs/voice-batch-m2-spec.md`。

## 功能概览

- 修改版特性：中文/English 界面运行时切换、日间/夜间双主题（未显式选择时跟随系统深浅色）、配置/日志/临时文件收敛到项目目录（`config/`、`logs/`、`temp/`）、`start.bat` 一键启动。
- 首页分两组入口：「文件复制」汇总车组、无线电、Bank 三个复制模块；「语音处理」直达语音编辑器。
- 车组、无线电与 Bank 模块均支持手动导入与目录自动检索，支持 `.wav`、`.flac`、`.ogg`、`.mp3`、`.m4a`、`.aac`、`.opus` 音频，扩展名匹配不区分大小写。
- 名称与内置名称库区分大小写精确匹配，同组剩余目标自动随机且均衡分配；自动补全永不覆盖已有文件，手动复制的冲突统一询问跳过、覆盖或取消。
- Bank 模块将 `.assets.bank` 与普通 `.bank` 作为不同角色，只有同一目录、同一类别（`common` 或 `ground`）、同一国家的两个角色同时存在时才能成为复制来源。
- 名称库在构建期由一次性脚本从用户提供的合法参考目录生成并嵌入 Qt 资源，运行时不读取 Excel；当前包含车组 511 个有效名称/151 个名称组、无线电 56 个确认分组/480 个完整名称、Bank 52 个完整国家组（common 17 组、ground 35 组）。
- 生成的名称库 JSON 与公开审计报告只保存外部来源标识，不记录开发机绝对路径。

## 名称库再生成（维护者操作）

名称库由一次性脚本从用户自行提供的合法参考目录生成并嵌入 Qt 资源；应用日常运行不读取这些参考工程。重建依赖 `requirements-dev.txt`（openpyxl 供 Excel 提取）与 PySide6 自带的 `pyside6-rcc`：

```powershell
.\.venv\Scripts\python.exe tools\extract_crew_names.py --input "<名称库 Excel 路径>"
.\.venv\Scripts\python.exe tools\build_radio_name_groups.py `
  --voice1 "<无线电 voice1 参考目录>" `
  --additional-01 "<无线电 additional_01 参考目录>" `
  --english "<无线电 english 参考目录>"
.\.venv\Scripts\python.exe tools\build_bank_name_groups.py `
  --sound "<War Thunder sound 参考目录>"
.\.venv\Scripts\pyside6-rcc.exe app\resources\resources.qrc -o app\resources\resources_rc.py
```

脚本会生成正式 JSON 与审计报告写入 `reports/`，其中无线电脚本会拒绝把高度、单位、方位角或孤立名称作为可补齐变体。

## 语音处理

语音处理页围绕一条单轨时间轴进行非破坏性编辑：所有裁切范围以整数毫秒保存，试听与正式导出都从同一个不可变 `TimelineSnapshot` 生成，因此片段顺序、裁切范围、空白时长与试听效果完全一致。

- 左右手柄进行非破坏性裁切，中央区域用于选择与排序；`Ctrl + 鼠标滚轮` 缩放，`Shift + 鼠标滚轮` 水平滚动，缩放保持可视区左侧时间不变；时间尺按可视范围自动切换秒/毫秒，最大缩放 1000 px/s（1 px/ms）。
- 「检测静音」按阈值与最短时长扫描静音段，勾选后一键在静音中点批量切分，一次撤销即可整体回滚。
- 「片段分析」列出每个片段的 EBU R128 响度与真峰值，并可导出频谱图 PNG。
- 导出格式支持 WAV（16/24-bit、32-bit Float）、MP3、FLAC、Opus 与 M4A，质量档随格式联动。
- 「导出处理」提供：响度归一化（EBU R128 两遍模式，精确命中目标 LUFS）、峰值归一化、语音归一化；FFT / 非局部均值降噪、去咔哒声、去嘶音；低切 / 人声增强 / 广播链（压缩 + 限幅）预设；片段淡入淡出与去除首尾静音。
- 平均分配导出（矩阵项目组一次渲染写入三个目标）固定使用 WAV。
- 音频探测、波形解析、响度分析、试听缓存和正式导出均在后台执行，且随时可取消。
- 第三方组件及许可全文见 `THIRD_PARTY_LICENSES.md` 与 `licenses/`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py app tools tests
$tests = Get-ChildItem tests -Filter "test_*.py" | Sort-Object Name
foreach ($test in $tests) {
  .\.venv\Scripts\python.exe -m unittest ("tests." + $test.BaseName) -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

自动化测试仅在临时目录创建测试字节文件，不会操作用户的音频素材。按模块分别启动测试进程，可以避免 QtMultimedia 全局状态在同一进程中跨测试模块残留。

## 当前范围

- 已实现：车组、无线电、Bank 的手动导入与自动检索、精确识别、分组确认、均衡随机分配、后台复制、统一冲突处理、取消、进度与结果展示；语音处理的波形编辑、静音检测切分、录音、多格式导出与响度/降噪处理链。
- 复制任务暂不提供暂停；Windows 发布流程已提供调试 onedir、正式 onedir 和正式 onefile 构建。

## 构建与大文件

仓库通过 Git LFS 管理 `app/resources/ffmpeg/bin/` 中的 FFmpeg、ffprobe、ffplay 和共享 DLL。克隆源码前请先安装 Git LFS；克隆后运行 `git lfs pull` 获取这些二进制资源。

正式发布优先提供完整 onedir ZIP。`build/`、`dist/`、`release/`、虚拟环境、日志、用户音频和测试输出不会加入普通源码提交。

FFmpeg 构建版本、源码披露、许可和第三方声明见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md)、[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) 与 [`licenses/`](licenses/)。

## 已知限制

- 若构建 Windows 可执行包，当前仅面向 x64。
- 打包构建中 onefile 首次启动需要释放 Qt 与 FFmpeg 资源，通常比 onedir 慢，也更容易被安全软件进行额外扫描。
- 名称库生成需要用户自行提供合法的参考目录；仓库不包含游戏官方资源或原始音频。
- 不同游戏版本可能改变 Bank 或语音文件命名，使用前请备份目标文件。

## 免责声明、许可与反馈

使用前请阅读 [`PROJECT_USAGE_NOTICE.md`](PROJECT_USAGE_NOTICE.md)。原始代码适用 [`LICENSE`](LICENSE)，本修改版的修改与新增代码按 GPL-3.0-only 授权，第三方组件继续遵循各自许可证。

发现 Bug 时请在 GitHub Issues 中提供：软件版本、复现步骤、预期行为、实际行为和必要的本地日志片段。提交日志前请先移除个人目录、语音素材名称及其他隐私信息；不要上传游戏官方资源、用户音频、密码或 Token。

---

本工具 fork 自 [Beiku](https://github.com/beikuwawa) 的原项目 [WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay)（beta 0.2.0）

本版（WT-Tool-Experimental Version）维护者：Diderde（GitHub：[@Diderde](https://github.com/Diderde)）
