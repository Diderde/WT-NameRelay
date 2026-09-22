# WT-Tool-Experimental Version 修改版声明（Modification Notice）

本文件是关于本修改版（派生作品）的许可与来源声明，随程序内"关于与许可"一并展示。

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

- `app/paths.py` —— 项目内存储路径定位
- `app/preferences.py` —— 用户偏好读写
- `app/i18n.py` —— 中英双语与运行时切换
- `start.bat` —— 一键启动脚本
- `app/pages/file_copy_page.py` —— 二级"文件复制"选择页（车组/无线电/Bank 的分组入口）
- `licenses/GPL-3.0.txt` —— GNU GPL-3.0 许可证原文（本修改版新增代码适用，仅第 3 版）
- `app/audio/silence_service.py` —— 静音检测后台服务（silencedetect 解析）
- `app/audio/analysis_service.py` —— 片段响度（EBU R128）与频谱图分析服务
- `download_tts_verify.bat` —— TTS 资源下载脚本（GPT-SoVITS 代码 / CosyVoice3 GGUF / 预训练权重，断点续传与跳过已完成）
- `gpt_sovits_weights_list.txt` —— GPT-SoVITS 权重清单（25 文件，供下载脚本逐文件校验）
- `app/services/tts_training.py` —— GPT-SoVITS 微调链路（prep 三阶段 + s1/s2 训练的编排与子进程托管）
- `app/widgets/tts_params_panel.py` —— 推理参数面板（参数随请求下发给后端）
- `app/widgets/tts_train_panel.py` —— 微调栏（数据集与超参表单、阶段状态、实时日志）
- `tools/download_progress.py` —— 下载进度监视器（只读统计已落盘字节，显示已下载/用时/速度/剩余）
- `tts_assets_manifest.txt` —— TTS 资源官方哈希清单（41 文件；sha256 / git blob sha1 + 大小 + 路径）
- `tools/collect_tts_asset_hashes.py` —— 从 HuggingFace 采集官方哈希并生成上述清单
- `tools/verify_tts_assets.py` —— TTS 资源完整性校验（存在性 / 大小 / 官方哈希，只读）
- `vtcore/wheels/vtcore-0.1.0-cp312-abi3-win_amd64.whl` —— 预编译 abi3 扩展（随源码附带，免 Rust 工具链）
- `tools/sanitize_wheel.py` —— 构建后中和 wheel（SBOM 绝对路径 + 重建 `RECORD`）
- `tools/check_wheel_leaks.py` —— 检查 wheel 是否残留构建机路径/用户名（入库/发布前必跑）
- `tools/view_gbk_bat.py` —— 把 GBK 的 bat 转写为 UTF-8 以便阅读（只读）

## 修改过的原有文件（修改部分按 GPL-3.0-only）

- `app/styles/theme.py` —— 日间/夜间双主题，颜色集中为调色板
- `app/main_window.py`、`app/pages/home_page.py`、`app/pages/base_tool_page.py`、
  `app/widgets/feature_card.py` —— 语言与主题切换、文案改造
- `app/widgets/disclaimer_dialog.py`、`app/widgets/about_dialog.py`、
  `app/widgets/license_dialog.py` —— 文案、修改版声明与许可多子页面
- `app/logging_setup.py` —— 日志位置收敛到项目内 `logs/`
- `app/audio/ffmpeg_service.py`、`app/pages/audio_processing_page.py` ——
  临时目录与设置存储本地化；导出格式扩展（MP3/FLAC/Opus/M4A）、
  两遍响度归一化、静音检测切分、降噪/修复与话筒预设链、
  录音与片段分析入口
- `app/audio/models.py`、`app/audio/__init__.py`、`app/i18n.py`、
  `THIRD_PARTY_LICENSES.md` ——
  导出设置字段、批量静音切分、服务导出与翻译键、许可清单、
  结构断言随上述功能调整
- `main.py`、`app/branding.py` —— 修改版标识与启动流程
- `windows_version_info.txt`、`build_release.py`、`*.spec` —— 打包元数据
- `.gitignore`、`.gitattributes`、`app/resources/resources.qrc`、
  `app/resources/resources_rc.py` —— 资源、忽略规则与 CRLF 行尾策略调整
  （`resources_rc.py` 由 `resources.qrc` 重新生成）
- `THIRD_PARTY_LICENSES.md` —— `licenses/` 目录文件清单补充 `GPL-3.0.txt`、
  移除随许可变更而不再需要的 `GPL-2.0.txt`，
  移除 Pillow 条目
- `requirements-dev.txt` —— 移除无引用的开发依赖 Pillow
  （`app`、`tools`、打包配置均不再使用；其许可证文本
  `licenses/Pillow-HPND.txt` 一并删除）
- `app/contracts.py` —— 新增随机源注入协议 `TaskRandomSource`；
  `app/services/copy_task_builder.py`、`app/services/bank_copy_task_builder.py`、
  `app/services/auto_completion_analyzer.py` —— `rng` 注解改用该协议
- `app/models/completion_group.py`、`app/services/bank_name_repository.py`、
  `app/services/crew_name_repository.py`、`app/services/auto_scan_service.py`、
  `app/services/average_distribution.py`、`app/services/directory_scanner.py`、
  `app/services/radio_staged_worker.py`、`app/widgets/audio_page_scroll_router.py`、
  `app/widgets/timeline_editor.py`、`app/pages/bank_page.py`、`app/pages/crew_page.py`、
  `tools/enrich_audio_categories.py` ——
  代码检查整改：补齐导入与注解、恢复带 `# noqa` 标注的资源注册副作用导入、
  清理未用导入
- **删除** `app/resources/icons/` 全部图标资源（主图标 `wt_name_relay.png`/`.ico`
  与 5 个功能小图标）：主程序改用系统默认图标、控件改纯文字呈现；
  图标未随本修改版再分发，原资源仍完整保存于上游仓库

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
