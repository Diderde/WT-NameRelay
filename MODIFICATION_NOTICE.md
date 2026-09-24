# WT-Tool-Experimental Version 修改版声明（Modification Notice）

本文件是关于本修改版（派生作品）的许可与来源声明，随程序内"关于与许可"一并展示。
开发过程的逐轮变更登记见 `docs/modification-history.md`（同属本修改版文档，不内嵌展示）。

## 基本信息

| 项目 | 内容 |
| --- | --- |
| 本修改版名称 | WT-Tool-Experimental Version |
| 原始项目 | WT-NameRelay |
| 原始仓库 | [beikuwawa/WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay) |
| 原始作者 | Beiku（GitHub: [@beikuwawa](https://github.com/beikuwawa)） |
| 基线版本 | beta 0.2.0（commit `aed3c94`，"Initial release: WT-NameRelay beta 0.2.0"） |
| 原始许可 | WT-NameRelay Source-Available License 1.0（见随附 `LICENSE` 文件） |
| 修改者 | Diderde（GitHub: [@Diderde](https://github.com/Diderde)） |
| 修改起始日期 | 2026-09 |
| 修改与新增代码许可 | **GNU General Public License v3.0 only（GPL-3.0-only）** |

## 许可分层

本修改版包含两部分代码，各自适用不同的许可，边界如下：

1. **原始代码**：即基线 beta 0.2.0 中已有的文件与代码，仍按
   **WT-NameRelay Source-Available License 1.0** 授权。本修改版的使用不改变、
   不替代该许可的任何条款。
2. **修改与新增代码**：即下文清单所列由 Diderde 新增的文件，以及对原有文件的
   修改部分，按 **GPL-3.0-only** 授权。

两部分代码以独立边界共存；如需分发本修改版，应同时遵守原始许可的全部条款
（包括非商业限制与同许可分享要求）并保留本声明。

## 新增文件（GPL-3.0-only，Copyright (C) 2026 Diderde）

> 以下三段清单由 `git diff --name-status -M aed3c94` 对本修改版工作树做机器比对生成，
> 上游基线为 `aed3c94`（WT-NameRelay beta 0.2.0）。可重跑该命令复核完整性。

本修改版新增 **95 个代码/文档/资源文件**（逐条列于下）；此外
`licenses/ffmpeg/`（10 个文件）为随包 FFmpeg 第三方组件的**逐组件许可原文**与索引
（`manifest.json` / `measured-versions.json` / `MANIFEST.md`），属**第三方材料**，
不作为本修改版的 GPL-3.0-only 新增代码；其许可归属见 `THIRD_PARTY_LICENSES.md`。

- `.zcodeignore` —— ZCode 编辑器的忽略规则（上半部同步自 `.gitignore`）
- `MODIFICATION_NOTICE.md` —— 本文件：修改版声明、许可分层与完整文件清单（会内嵌进程序展示）
- `app/audio/analysis_service.py` —— Per-clip loudness analysis (EBU R128) and spectrum image rendering.
- `app/audio/silence_service.py` —— Silence detection for the audio timeline (background worker over ffmpeg).
- `app/i18n.py` —— Lightweight Chinese/English translation for usage-layer UI strings.
- `app/models/voice_table.py` —— Voice batch table model (M1)。
- `app/pages/file_copy_page.py` —— Second-level selector that groups the three name-copy tool pages.
- `app/pages/tts_model_page.py` —— 二级页：TTS 模型选择（GPT-SoVITS / CosyVoice 3 GGUF）。
- `app/pages/voice_batch_page.py` —— 三级页：TTS 批量生成工作台（W3）。
- `app/paths.py` —— Project-local storage locations anchored at the repository root.
- `app/preferences.py` —— Shared access to the user preference file (config/settings.ini).
- `app/resources/ffmpeg/bin/libgcc_s_seh-1.dll`
- `app/resources/ffmpeg/bin/libmp3lame-0.dll`
- `app/resources/ffmpeg/bin/libopus-0.dll`
- `app/resources/ffmpeg/bin/libwinpthread-1.dll`
- `app/services/save_coordinator.py` —— 工程持久化与自动保存（M2 起）。
- `app/services/tts_runner.py` —— TTS 运行时（M1）：串行队列 + 后端抽象 + 产物校验。
- `app/services/tts_training.py` —— GPT-SoVITS 微调链路：数据准备（prep 三阶段）与 s1/s2 两段训练。
- `app/services/voice_filename_validator.py` —— 语音产物文件名校验（ValidatorProfile 架构；产品只发布 WT_DEFAULT）。
- `app/services/voice_service_launcher.py` —— CosyVoice3 推理服务装配（B 方案：独立子进程 + HTTP 契约）。
- `app/services/vt_key_store.py` —— 项目密钥存储（M2-W4，规范见 `docs/voice-batch-m2-spec.md` §7）。
- `app/services/vt_manifest.py` —— `.vtmanifest` 整包验证（M2-W5，规范见 `docs/voice-batch-m2-spec.md` §9）。
- `app/services/vt_project.py` —— `.vt` 工程文件的读写、只读锁（M2，规范 §8）。
- `app/services/vt_trust_store.py` —— TOFU 信任库（M2-W4，规范见 `docs/voice-batch-m2-spec.md` §6）。
- `app/widgets/cosyvoice_info_panel.py` —— CosyVoice 3（GGUF）信息面板：模型位置、就绪状态与用途说明。
- `app/widgets/flow_layout.py` —— 自动换行的水平流式布局（Qt 官方 FlowLayout 示例的 PySide6 实现）。
- `app/widgets/tts_params_panel.py` —— 推理参数面板：把后端支持的合成参数暴露到界面。
- `app/widgets/tts_train_panel.py` —— 微调栏：GPT-SoVITS 数据集配置 + 五阶段执行 + 实时日志。
- `app/widgets/voice_table_model.py` —— 语音批量表格模型与行委托（W3）。
- `app/widgets/vt_key_dialog.py` —— 签名密钥对话框（M2 界面接线）：展示项目密钥的**公开部分**，并可生成新密钥。
- `app/widgets/water_backdrop.py` —— 全窗口水纹流动背板（玻璃卡片视觉的全局底衬）。
- `docs/development-notes.md` —— 开发注意事项汇编（硬规则、收尾流程、门禁、环境与工具链陷阱）
- `docs/modification-history.md` —— 逐轮变更登记（开发过程记录；与声明分离以免撑大内嵌文档）
- `docs/test-drive-plan.md` —— The Test Drive — A Standalone Voice-Pack Simulator for War Thunder
- `docs/tts-spike-report.md` —— TTS 运行时 Spike 报告（后端选型与契约探针结论）
- `docs/tts-workflow-guide.md` —— 面向使用者的语音包作业流程指南
- `docs/voice-batch-m2-spec.md` —— 语音批量 M2 规范（vtcore 与 `.vt` 容器，字节格式冻结）
- `docs/voice-batch-spec.md` —— 语音批量生成 M1 规范（字节格式冻结）
- `download_tts_verify.bat` —— TTS 资源下载脚本（GPT-SoVITS 代码 / CosyVoice3 GGUF / 预训练权重，断点续传与跳过已完成）
- `gpt_sovits_weights_list.txt` —— GPT-SoVITS 权重清单（25 文件，供下载脚本逐文件校验）
- `start.bat` —— 一键启动脚本（含依赖补齐、资源校验、vtcore 扩展获取）
- `tests/deterministic_rng.py` —— Deterministic test double for the service-layer random-source injection point.
- `tests/fixtures/voice_table_golden.json` —— vtcore 黄金向量固定装置（字节级冻结，跨语言一致性基准）
- `tests/test_asset_verify.py` —— TTS 资源完整性校验测试（`tools/verify_tts_assets.py`）。
- `tests/test_audio_features.py` —— Tests for the audio processing feature additions (P1-P7).
- `tests/test_cosyvoice_shim.py` —— B 方案测试：CosyVoice3 本地服务（shim）与应用侧装配。
- `tests/test_ffmpeg_license.py` —— 随包 FFmpeg 许可审计测试（含换件绊线与检测器自检）
- `tests/test_tts_interface.py` —— 接口层契约测试：用本地 stub HTTP 服务验证客户端行为（**不启动任何真实模型**）。
- `tests/test_tts_runner.py` —— W2 TTS 运行时测试：串行队列 / 失败隔离 / 取消 / 超时 / HTTP 契约。
- `tests/test_voice_batch.py` —— W3 语音批量工作台测试：表格模型 / 委托几何 / 页面生成闭环 / i18n 表头。
- `tests/test_voice_filename_validator.py` —— W3 文件名校验测试：WT_DEFAULT 规则与冲突建议（不使用 random）。
- `tests/test_voice_output_dir.py` —— 输出目录偏好（中等方案）：回退默认、偏好覆盖、选择器接线、取消不动现状。
- `tests/test_voice_save.py` —— 持久化与自动保存测试：`.vt` 工作文件 / 旁车状态命名与往返 / 修订号防旧覆盖。
- `tests/test_voice_table.py` —— W1 语音表模型测试：规范字节黄金向量 / 身份语义 / 双轴状态合成。
- `tests/test_vt_key_store.py` —— 项目密钥存储测试（M2-W4，`docs/voice-batch-m2-spec.md` §7）。
- `tests/test_vt_manifest.py` —— `.vtmanifest` 整包验证测试（M2-W5，规范 §9）。
- `tests/test_vt_project.py` —— `.vt` 工程读写 / 只读锁 / 工作文件往返测试（M2，规范 §8）。
- `tests/test_vt_trust.py` —— TOFU 信任库测试（M2-W4，`docs/voice-batch-m2-spec.md` §6）。
- `tests/test_vtcore.py` —— vtcore（Rust/PyO3）契约测试：规范字节兼容 + Ed25519 签名层。
- `tools/audit_ffmpeg_license.py` —— 二进制许可审计器：核对 configure 开关、屏蔽后扫 GPL 特征、与界面标签对拍
- `tools/check_tts_services.py` —— from __future__ import annotations
- `tools/check_wheel_leaks.py` —— 本机身份字样改为运行时推导，不再把真实用户名写进公开源码
- `tools/collect_rust_licenses.py` —— 汇总 Rust 依赖的许可证（读 `vtcore/Cargo.lock` + 本地 cargo registry 元数据）。
- `tools/collect_tts_asset_hashes.py` —— 采集 TTS 资源的**官方哈希**，生成 `tts_assets_manifest.txt`。
- `tools/cosyvoice3_shim.py` —— CosyVoice3 本地推理服务（CrispASR 绑定的 HTTP 包装）。
- `tools/download_progress.py` —— 下载进度监视器：实时显示已下载大小、用时、速度与预计剩余时间。
- `tools/ffmpeg-build/01-toolchain.sh` —— 装 MSYS2 工具链与三个外部库
- `tools/ffmpeg-build/02-build.sh` —— 取源码并编译最小 LGPL 构建（无 chromaprint）
- `tools/ffmpeg-build/03-version-relink.sh` —— 把版本串写实为 N-125829-gfe953596e9 并增量重链
- `tools/ffmpeg-build/04-collect.sh` —— 收集运行时文件换进仓库并跑许可审计
- `tools/ffmpeg-build/README.md` —— 随包 FFmpeg 的可复现构建说明（合规义务的一部分）
- `tools/gen_voice_table_golden.py` —— M1 规范字节黄金向量的生成 / 校验（供 Python 与 Rust vtcore 共用）。
- `tools/run_gate.ps1` —— 门禁模块清单加入 `ffmpeg_license`（26 个模块）
- `tools/sanitize_wheel.py` —— 同上
- `tools/verify_ffmpeg_licenses.py` —— 核验 licenses/ffmpeg/ 的许可文本是否与清单一致（存在性 + sha256）。
- `tools/verify_tts_assets.py` —— TTS 资源完整性校验：存在性 + 大小 + 官方哈希比对。
- `tools/view_gbk_bat.py` —— 把 GBK 的 bat 转写为 UTF-8 便于阅读（只读，不改原文件）。
- `tts_assets_manifest.txt` —— TTS 资源官方哈希清单（41 文件；sha256 / git blob sha1 + 大小 + 路径）
- `vtcore/Cargo.lock` —— Rust 依赖锁定（行尾 LF 例外，见 `.gitattributes`）
- `vtcore/Cargo.toml` —— vtcore crate 清单与依赖声明
- `vtcore/README.md` —— vtcore 构建方式、接口清单与测试方式
- `vtcore/pyproject.toml` —— maturin 构建配置（abi3 wheel）
- `vtcore/src/canonical.rs` —— M1 规范字节的权威实现（`docs/voice-batch-spec.md` §4）。
- `vtcore/src/container.rs` —— `.vt` 二进制容器（`docs/voice-batch-m2-spec.md` §2–§3）。
- `vtcore/src/hex.rs` —— 十六进制编解码（文本层统一小写，`m2-spec` §1）。
- `vtcore/src/keystore.rs` —— 项目私钥的 AEAD 封装（`docs/voice-batch-m2-spec.md` §7）。
- `vtcore/src/lib.rs` —— vtcore：语音批量规范字节的权威实现（PyO3 绑定）。
- `vtcore/src/manifest.rs` —— `.vtmanifest` 的规范字节（`docs/voice-batch-m2-spec.md` §9）。
- `vtcore/src/sign.rs` —— 签名层（`docs/voice-batch-m2-spec.md` §5）：算法编号表、签名消息规范字节、Ed25519 sign/verify。
- `vtcore/tests/container.rs` —— `.vt` 容器测试：往返一致性、双层完整性、未知 chunk 策略、自洽校验、签名绑定。
- `vtcore/tests/golden.rs` —— 黄金向量字节兼容测试：读 `tests/fixtures/voice_table_golden.json`（与 Python 侧同一份基准）。
- `vtcore/tests/keystore.rs` —— 密钥封装测试（`m2-spec` §7）：往返、随机 nonce、AAD 绑定、篡改与格式校验。
- `vtcore/tests/manifest.rs` —— `.vtmanifest` 规范字节测试（`m2-spec` §9）：布局、排序、路径与哈希校验、签名绑定。
- `vtcore/tests/sign.rs` —— 签名层测试：**RFC 8032 §7.1 官方 Ed25519 测试向量** + 签名消息布局 + 拒绝路径。
- `vtcore/wheels/vtcore-0.1.0-cp312-abi3-win_amd64.whl` —— 预编译 abi3 扩展（随源码附带，免 Rust 工具链）

## 修改过的原有文件（修改部分按 GPL-3.0-only）

> 机器比对结果：上游基线中有 **93 个文件**在本修改版被修改。
> 仅**修改部分**按 GPL-3.0-only 授权，未改动的部分仍遵循原 Source-Available 许可。

- `.gitattributes` —— 新增 `vtcore/Cargo.lock text eol=lf`；确立整体 CRLF 行尾策略
- `.gitignore` —— 补模型/音频通配符（含 `*.gguf`）与仓库根临时目录规则
- `FFMPEG_BUILD_INFO.md` —— 随包 FFmpeg 的来源、许可实测结论、可复现构建与验收闸门
- `README.md` —— fork 名称、可选组件 vtcore 一节、来源与许可声明
- `THIRD_PARTY_LICENSES.md` —— 第三方组件与许可证清单（FFmpeg 自建构建、Rust crate、Python 依赖）
- `WT-NameRelay-debug.spec` —— PyInstaller 打包配置（debug）
- `WT-NameRelay-onedir.spec` —— PyInstaller 打包配置（onedir）
- `WT-NameRelay.spec` —— PyInstaller 打包配置（release）
- `app/__init__.py` —— WT-Tool application package.
- `app/audio/__init__.py` —— Audio-processing domain models and background services.
- `app/audio/ffmpeg_service.py` —— 按导出格式返回编码器与质量参数（质量为空时使用各格式默认档）。
- `app/audio/models.py` —— Immutable multi-resolution min/max envelope.
- `app/audio/project_service.py` —— Read-only exact lookup over the two existing embedded name libraries.
- `app/audio/waveform_service.py` —— Process-local cache keyed by path metadata; zoom never invokes FFmpeg.
- `app/branding.py` —— 本修改版（fork）的正式名称：用户可见品牌，固定原文呈现，不随界面语言切换。
- `app/contracts.py` —— 随机源注入点要求的最小接口。
- `app/logging_setup.py` —— 日志位置收敛到项目内 `logs/`
- `app/main_window.py` —— Application shell responsible only for page routing.
- `app/models/__init__.py` —— Immutable domain models used by the crew manual-copy workflow.
- `app/models/completion_group.py` —— One directory-scoped automatic completion group.
- `app/models/radio_copy.py` —— Radio manual-copy assignment mode.
- `app/pages/__init__.py` —— Application pages.
- `app/pages/audio_processing_page.py` —— Project-scoped, non-destructive single-track voice processing page.
- `app/pages/bank_page.py` —— Country-paired Bank completion using the shared copy worker.
- `app/pages/base_tool_page.py` —— Shared presentation-only framework for secondary pages.
- `app/pages/crew_page.py` —— Configurable manual and automatic completion workflow for a name module.
- `app/pages/home_page.py` —— Landing page with one entry per tool group.
- `app/pages/radio_page.py` —— Radio workflow with an isolated deterministic average manual-copy mode.
- `app/resources/ffmpeg/bin/avcodec-63.dll`
- `app/resources/ffmpeg/bin/avdevice-63.dll`
- `app/resources/ffmpeg/bin/avfilter-12.dll`
- `app/resources/ffmpeg/bin/avformat-63.dll`
- `app/resources/ffmpeg/bin/avutil-61.dll`
- `app/resources/ffmpeg/bin/ffmpeg.exe`
- `app/resources/ffmpeg/bin/ffprobe.exe`
- `app/resources/ffmpeg/bin/swresample-7.dll`
- `app/resources/ffmpeg/bin/swscale-10.dll`
- `app/resources/resources.qrc` —— 资源清单（图标资源删除后同步）
- `app/resources/resources_rc.py` —— Resource object code (Python 3)
- `app/services/__init__.py` —— Future file-processing service boundaries.
- `app/services/auto_completion_analyzer.py` —— Build directory-isolated completion views from one disk scan snapshot.
- `app/services/auto_scan_service.py` —— Own a cancellable background scan without blocking the Qt UI thread.
- `app/services/average_distribution.py` —— Normalize paths in JSON order and fold only equal complete triples.
- `app/services/bank_copy_task_builder.py` —— Create country-level assignments, then flatten them for the shared worker.
- `app/services/bank_filename_parser.py` —— Strictly parse Bank names, prioritising the longer assets suffix.
- `app/services/bank_name_repository.py` —— Read-only access to the embedded Bank category/country library.
- `app/services/copy_task_builder.py` —— Sort versioned names by numeric version components, then by text.
- `app/services/crew_name_parser.py` —— Turn an actual source-file path into an exact recognition record.
- `app/services/crew_name_repository.py` —— Read-only, exact-match access to an embedded module name library.
- `app/services/crew_service.py` —— Own the worker thread used by one crew manual-copy batch at a time.
- `app/services/directory_scanner.py` —— Raised internally when a directory scan receives a cancellation request.
- `app/services/file_copy_worker.py` —— Background-only worker for one frozen manual-copy plan.
- `app/services/radio_staged_service.py` —— Compatibility name; all application pages use the generic service.
- `app/services/radio_staged_worker.py` —— Snapshot every source before an average-distribution target is touched.
- `app/styles/theme.py` —— 注册主题模式变化监听（QSS 之外的自绘控件用）。
- `app/widgets/__init__.py` —— Reusable UI widgets.
- `app/widgets/about_dialog.py` —— 署名与许可信息属于法律内容，固定中文原文，不随界面语言切换。
- `app/widgets/animated_stack.py` —— Animate disposable page snapshots so live widgets never leave paint trails.
- `app/widgets/audio_page_scroll_router.py` —— Route wheel input between the timeline and the page scroll area.
- `app/widgets/auto_scan_result_panel.py` —— Filterable, scrollable automatic-completion confirmation surface.
- `app/widgets/completion_group_widget.py` —— Collapsible automatic-completion group with existing and missing rows.
- `app/widgets/confirmation_group.py` —— One independently selectable group of pending manual-copy targets.
- `app/widgets/copy_mode_switch.py` —— Compact animated two-state switch for radio manual copy mode.
- `app/widgets/directory_selector.py` —— Directory input, background-scan controls, and scan statistics.
- `app/widgets/disclaimer_dialog.py` —— Mandatory, non-bypassable acknowledgement displayed before MainWindow exists.
- `app/widgets/feature_card.py` —— Keyboard-accessible feature card with restrained hover feedback.
- `app/widgets/file_drop_area.py` —— Small drag-and-drop surface that forwards local filesystem paths.
- `app/widgets/license_dialog.py` —— License documents presented as one sub-page per document.
- `app/widgets/pyqtgraph_timeline.py` —— A seconds/milliseconds ruler whose labelled ticks remain readable.
- `app/widgets/radio_confirmation_group.py`
- `app/widgets/source_file_list.py` —— Scrollable imported-file list with per-item removal controls.
- `app/widgets/task_status_panel.py` —— Progress bar with smooth value changes and a restrained running sheen.
- `app/widgets/timeline_editor.py` —— Superseded canvas prototype kept only for source-history comparison.
- `build_release.py` —— 发布闸门升级：打包前同时跑二进制许可审计，不通过即拒发
- `main.py` —— Show the mandatory notice before constructing the main window.
- `packaging/hooks/hook-pyqtgraph.py` —— Package only the PyQtGraph data used by WT-NameRelay.
- `requirements-dev.txt` —— 移除无引用的开发依赖 Pillow；新增 `maturin`
- `tests/test_audio_page_matrix.py` —— flush 定时器为 16ms；跨模块同进程运行时事件循环可能繁忙，
- `tests/test_audio_processing.py`
- `tests/test_auto_completion.py` —— Regression lock: AutoCompletionAnalysis 注解必须可解析（防未导入前向引用回归）。
- `tests/test_average_distribution_contract.py`
- `tests/test_bank_module.py`
- `tests/test_crew_workflow.py`
- `tests/test_pyqtgraph_timeline.py` —— A stale terminal callback from the preceding session must not finalize
- `tests/test_radio_average_manual.py`
- `tests/test_radio_module.py`
- `tests/test_release_features.py` —— 修改版声明断言随 FFmpeg 版本串更新
- `tests/test_ui_smoke.py`
- `tools/build_radio_name_groups.py` —— Build the embedded radio name library from three read-only source directories.
- `tools/enrich_audio_categories.py` —— Attach reference-project category metadata without changing name groups.
- `tools/extract_crew_names.py`
- `tools/visual_check_audio_page.py` —— Visible Windows-only harness for manually checking the audio page.
- `windows_version_info.txt` —— 可执行文件版本元数据（随本版名称）

## 删除的原有文件（不再随本修改版分发）

> 机器比对结果：上游基线中有 **9 个文件**不再随本修改版分发；
> 原始文件仍完整保存于上游仓库，可自 `aed3c94` 取得。

- `app/resources/ffmpeg/bin/ffplay.exe` —— 自建最小构建不再编译 ffplay；应用未使用它，发布包本就不包含
- `app/resources/icons/audio_processing.svg` —— 主图标与 5 个功能小图标；主程序改用系统默认图标、控件改纯文字呈现
- `app/resources/icons/back.svg` —— 主图标与 5 个功能小图标；主程序改用系统默认图标、控件改纯文字呈现
- `app/resources/icons/bank.svg` —— 主图标与 5 个功能小图标；主程序改用系统默认图标、控件改纯文字呈现
- `app/resources/icons/crew.svg` —— 主图标与 5 个功能小图标；主程序改用系统默认图标、控件改纯文字呈现
- `app/resources/icons/radio.svg` —— 主图标与 5 个功能小图标；主程序改用系统默认图标、控件改纯文字呈现
- `app/resources/icons/wt_name_relay.ico` —— 主图标与 5 个功能小图标；主程序改用系统默认图标、控件改纯文字呈现
- `app/resources/icons/wt_name_relay.png` —— 主图标与 5 个功能小图标；主程序改用系统默认图标、控件改纯文字呈现
- `licenses/Pillow-HPND.txt` —— 开发依赖 Pillow 已移除，其许可证文本一并删除

## 运行行为差异（相对基线）

- 配置存储：注册表 → `config/settings.ini`（普通文件）
- 日志目录：`%LOCALAPPDATA%` → 项目内 `logs/`
- 临时渲染目录：系统 `%TEMP%` → 项目内 `temp/`
- 新增：中/英界面切换、日间/夜间主题（默认跟随系统）
- 新增：`start.bat` 一键启动
- 界面品牌标识：主标识为本 fork 正式名称 `WT-Tool-Experimental Version`（单一名称，
  不再拆分为副标题），不再沿用原项目名；"关于与许可"页底部标注 fork 来源（Beiku 的
  WT-NameRelay 及其仓库地址）与本版维护者（Diderde）；启动"使用声明"首段即声明 fork 来源

## 其他声明

本项目为非官方第三方工具，与 Gaijin Entertainment、War Thunder及其关联主体
不存在隶属、授权、赞助或合作关系；不包含、不提供也不分发任何游戏官方资源或
官方音频。

---

## Modification Notice (English Summary)

- **This is a fork**: WT-Tool-Experimental Version is an unofficial experimental
  fork of WT-NameRelay, not an official release of the original project.
- **Base project**: WT-NameRelay beta 0.2.0 by Beiku
  ([beikuwawa/WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay)), licensed under the
  WT-NameRelay Source-Available License 1.0.
- **Modifier**: Diderde (GitHub: [@Diderde](https://github.com/Diderde)), since 2026-09.
- **Licensing layering**: the original code remains under its original
  Source-Available license; the additions and modifications listed above by
  Diderde are licensed under **GNU GPL-3.0-only**.
- This is an unofficial third-party tool, not affiliated with Gaijin
  Entertainment or War Thunder, and contains no official game assets.
- Any redistribution must comply with the original license terms in full and
  keep this notice attached.

## 逐轮变更登记

开发过程中的逐轮改动登记（含每轮的文件增删与设计说明）已移至
`docs/modification-history.md`，与本源代码分发一并提供。
本文件只保留**面向使用者与合规审查**的内容：许可分层、完整文件清单、
运行行为差异与其他声明。

---

