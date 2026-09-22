# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""Lightweight Chinese/English translation for usage-layer UI strings.

Only interface chrome participates in language switching. Legal content
(disclaimer body, license texts, the modification notice) is deliberately
excluded and stays in its original language.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QWidget

from app.preferences import get_preference, set_preference

LANGUAGE_KEY = "ui/language"

_LANGUAGES: dict[str, str] = {"zh": "中文", "en": "English"}

_STRINGS: dict[str, dict[str, str]] = {
    "common.back": {"zh": "返回主界面", "en": "Back to Home"},
    "home.eyebrow": {"zh": "War Thunder语音工具", "en": "War Thunder Voice Tools"},
    "home.subtitle": {
        "zh": "War Thunder语音包文件名称补全与复制工具",
        "en": "Voice pack file-name completion and copying for War Thunder",
    },
    "home.about": {"zh": "关于与许可", "en": "About & License"},
    "home.toggle.language": {"zh": "English", "en": "中文"},
    "home.toggle.theme.dark": {"zh": "夜间模式", "en": "Dark mode"},
    "home.toggle.theme.light": {"zh": "日间模式", "en": "Light mode"},
    "home.toggle.motion.on": {"zh": "动效：开", "en": "Motion: On"},
    "home.toggle.motion.off": {"zh": "动效：关", "en": "Motion: Off"},
    "home.card.crew.title": {"zh": "车组文件复制", "en": "Crew File Copy"},
    "home.card.crew.desc": {
        "zh": "用于处理车组语音相关文件名称",
        "en": "Complete and copy crew voice file names",
    },
    "home.card.radio.title": {"zh": "无线电文件复制", "en": "Radio File Copy"},
    "home.card.radio.desc": {
        "zh": "用于处理无线电语音相关文件名称",
        "en": "Complete and copy radio voice file names",
    },
    "home.card.bank.title": {"zh": "Bank 文件复制", "en": "Bank File Copy"},
    "home.card.bank.desc": {
        "zh": "用于处理 Bank 相关文件名称",
        "en": "Complete and copy bank file names",
    },
    "home.card.audio.title": {"zh": "语音处理", "en": "Audio Processing"},
    "home.card.audio.desc": {
        "zh": "用于编辑、导出与补齐语音项目文件",
        "en": "Edit, export and complete voice project files",
    },
    "home.card.copy.title": {"zh": "文件复制", "en": "File Copy"},
    "home.card.copy.desc": {
        "zh": "用于处理文件复制",
        "en": "File copy tools",
    },
    "card.action": {"zh": "进入功能", "en": "Open"},
    "card.tooltip": {"zh": "进入{title}", "en": "Open {title}"},
    "page.eyebrow": {"zh": "功能工作区", "en": "Workspace"},
    "page.copy.title": {"zh": "文件复制", "en": "File Copy"},
    "page.crew.title": {"zh": "车组文件复制", "en": "Crew File Copy"},
    "page.radio.title": {"zh": "无线电文件复制", "en": "Radio File Copy"},
    "page.bank.title": {"zh": "Bank 文件复制", "en": "Bank File Copy"},
    "page.audio.title": {"zh": "语音处理", "en": "Audio Processing"},
    "page.placeholder.title": {"zh": "功能区域", "en": "Workspace Area"},
    "page.placeholder.text": {
        "zh": "功能框架已建立，具体处理逻辑将在后续阶段接入。",
        "en": "The framework is ready; processing logic will be integrated in later stages.",
    },
    "dialog.disclaimer.window_title": {"zh": "WT-Tool-Experimental Version 使用声明", "en": "WT-Tool-Experimental Version Disclaimer"},
    "dialog.disclaimer.continue": {"zh": "我已阅读并继续", "en": "I have read and continue"},
    "dialog.disclaimer.countdown": {"zh": "我已阅读（{seconds}秒）", "en": "I have read ({seconds}s)"},
    "audio.export.format": {"zh": "导出格式", "en": "Export format"},
    "audio.export.quality": {"zh": "质量", "en": "Quality"},
    "audio.export.loudness_target": {"zh": "响度目标", "en": "Target loudness"},
    "audio.export.gain": {"zh": "音量增益", "en": "Gain"},
    "audio.export.flac_level": {"zh": "压缩级", "en": "Level"},
    "audio.export.matrix_wav_notice": {
        "zh": "平均分配导出固定使用 WAV 格式。",
        "en": "Average-distribution export always writes WAV.",
    },
    "audio.button.silence": {"zh": "检测静音", "en": "Detect silence"},
    "audio.button.analyze": {"zh": "片段分析", "en": "Clip analysis"},
    "dialog.processing.loudness_group": {"zh": "响度", "en": "Loudness"},
    "dialog.processing.off": {"zh": "关闭", "en": "Off"},
    "dialog.processing.peak": {"zh": "峰值归一化", "en": "Peak normalization"},
    "dialog.processing.loudness": {"zh": "响度归一化（EBU R128，两遍）", "en": "Loudness (EBU R128, two-pass)"},
    "dialog.processing.speech": {"zh": "语音归一化", "en": "Speech normalization"},
    "dialog.processing.repair_group": {"zh": "降噪与修复", "en": "Denoise & repair"},
    "dialog.processing.denoise_fft": {"zh": "FFT 降噪", "en": "FFT denoise"},
    "dialog.processing.denoise_nl": {"zh": "非局部均值降噪", "en": "Non-local means denoise"},
    "dialog.processing.strength": {"zh": "降噪强度", "en": "Denoise strength"},
    "dialog.processing.declick": {"zh": "去咔哒声", "en": "Declick"},
    "dialog.processing.deesser": {"zh": "去嘶音", "en": "De-ess"},
    "dialog.processing.preset_group": {"zh": "预设与修饰", "en": "Preset & polish"},
    "dialog.processing.preset_off": {"zh": "无预设", "en": "No preset"},
    "dialog.processing.preset_lowcut": {"zh": "低切（80 Hz）", "en": "Low cut (80 Hz)"},
    "dialog.processing.preset_voice": {"zh": "人声增强", "en": "Voice enhance"},
    "dialog.processing.preset_broadcast": {"zh": "广播链（压缩 + 限幅）", "en": "Broadcast (compress + limit)"},
    "dialog.processing.fade": {"zh": "片段淡入淡出", "en": "Clip fade in/out"},
    "dialog.processing.trim_edges": {"zh": "去除首尾静音", "en": "Trim leading/trailing silence"},
    "dialog.silence.threshold": {"zh": "静音阈值", "en": "Silence threshold"},
    "dialog.silence.min_duration": {"zh": "最短静音时长", "en": "Minimum silence"},
    "dialog.silence.scanning": {"zh": "正在检测静音……", "en": "Detecting silence…"},
    "dialog.silence.results": {"zh": "勾选需要切分的静音位置：", "en": "Tick the silences to split at:"},
    "dialog.silence.none": {"zh": "未检测到静音段。", "en": "No silence detected."},
    "dialog.silence.apply": {"zh": "在勾选处切分", "en": "Split at ticks"},
    "dialog.analyze.title": {"zh": "片段响度分析", "en": "Clip loudness"},
    "dialog.analyze.column_clip": {"zh": "片段", "en": "Clip"},
    "dialog.analyze.column_duration": {"zh": "时长", "en": "Duration"},
    "dialog.analyze.column_lufs": {"zh": "响度 (LUFS)", "en": "Loudness (LUFS)"},
    "dialog.analyze.column_peak": {"zh": "真峰值 (dBFS)", "en": "True peak (dBFS)"},
    "dialog.analyze.spectrum": {"zh": "频谱图", "en": "Spectrum"},
    "dialog.analyze.scanning": {"zh": "正在分析片段……", "en": "Analyzing clips…"},
    "dialog.about.window_title": {"zh": "关于与许可", "en": "About & License"},
    "dialog.about.view_license": {"zh": "查看完整许可证", "en": "View Full License"},
    "dialog.license.window_title": {"zh": "完整许可证文本", "en": "Full License Texts"},

    # 功能页存量文案（bank / radio / crew / audio 四页 i18n 覆盖）
    "ui.001": {"zh": "目标目录不存在或不可访问。", "en": "The target folder does not exist or is not accessible."},
    "ui.002": {"zh": "Bank 文件复制", "en": "Bank File Copy"},
    "ui.003": {"zh": "扫描已取消", "en": "Scan cancelled"},
    "ui.004": {"zh": "扫描失败：{0}", "en": "Scan failed: {0}"},
    "ui.005": {"zh": "任务正在运行", "en": "Task in progress"},
    "ui.006": {"zh": "Bank 任务仍在运行，是否安全取消后关闭？", "en": "A bank task is still running. Cancel it safely and close?"},
    "ui.007": {"zh": "手动复制", "en": "Manual copy"},
    "ui.008": {"zh": "导入同目录、同类别、同国家的 assets 与主 Bank 后才能作为来源。", "en": "Import the assets and main bank files that share a folder, category and country before they can be used as sources."},
    "ui.009": {"zh": "手动复制进度", "en": "Manual copy progress"},
    "ui.010": {"zh": "开始复制", "en": "Start copy"},
    "ui.011": {"zh": "自动检索", "en": "Auto scan"},
    "ui.012": {"zh": "扫描目录中的 Bank 配对；完整组为来源，残缺组仅补齐缺失角色。", "en": "Scan the folder for bank pairs; complete groups become sources, incomplete groups only have their missing roles filled in."},
    "ui.013": {"zh": "复制前 Bank 文件：0", "en": "Bank files before copy: 0"},
    "ui.014": {"zh": "已有完整国家组：0", "en": "Complete country groups: 0"},
    "ui.015": {"zh": "已有残缺国家组：0", "en": "Incomplete country groups: 0"},
    "ui.016": {"zh": "自动复制进度", "en": "Auto copy progress"},
    "ui.017": {"zh": "开始自动复制", "en": "Start auto copy"},
    "ui.018": {"zh": "选择复制文件", "en": "Files to copy"},
    "ui.019": {"zh": "仅接受 common / ground 的 .assets.bank 或 .bank；不符合规则的文件会保留并提示。", "en": "Only common / ground .assets.bank or .bank files are accepted; files that do not match stay in the list with a notice."},
    "ui.020": {"zh": "状态", "en": "Status"},
    "ui.021": {"zh": "完整路径", "en": "Full path"},
    "ui.022": {"zh": "移除选中", "en": "Remove selected"},
    "ui.023": {"zh": "清空", "en": "Clear"},
    "ui.024": {"zh": "识别待确认区", "en": "Recognized pending confirmation"},
    "ui.025": {"zh": "尚未导入可识别的 Bank 文件。", "en": "No recognizable bank files imported yet."},
    "ui.026": {"zh": "自动检索结果", "en": "Auto scan results"},
    "ui.027": {"zh": "请选择目录并开始识别。", "en": "Choose a folder and start scanning."},
    "ui.028": {"zh": "全选", "en": "Select all"},
    "ui.029": {"zh": "全部取消", "en": "Deselect all"},
    "ui.030": {"zh": "重新分配来源", "en": "Reassign sources"},
    "ui.031": {"zh": "取消任务", "en": "Cancel task"},
    "ui.032": {"zh": "目标", "en": "Target"},
    "ui.033": {"zh": "说明", "en": "Details"},
    "ui.034": {"zh": "选择 Bank 文件", "en": "Choose bank files"},
    "ui.035": {"zh": "Bank 文件 (*.bank);;所有文件 (*)", "en": "Bank files (*.bank);;All files (*)"},
    "ui.036": {"zh": "配对不完整，缺少：{0}", "en": "Incomplete pair, missing: {0}"},
    "ui.037": {"zh": "配对完整（可作为来源）", "en": "Pair complete (usable as a source)"},
    "ui.038": {"zh": "配对歧义", "en": "Ambiguous pair"},
    "ui.039": {"zh": "{0}（来源：{1}）", "en": "{0} (source: {1})"},
    "ui.040": {"zh": "\n输出：{0}", "en": "\nOutput: {0}"},
    "ui.041": {"zh": "尚未识别到可配对的 Bank 文件。", "en": "No bank files that can be paired yet."},
    "ui.042": {"zh": "未发现可识别的 Bank 配对。", "en": "No recognizable bank pairs found."},
    "ui.043": {"zh": "发现已有目标文件", "en": "Existing target files found"},
    "ui.044": {"zh": "请选择对本批 Bank 文件统一应用的处理方式。", "en": "Choose how to handle existing files for this bank batch."},
    "ui.045": {"zh": "跳过", "en": "Skip"},
    "ui.046": {"zh": "覆盖", "en": "Overwrite"},
    "ui.047": {"zh": "取消", "en": "Cancel"},
    "ui.048": {"zh": "选择 Bank 目录", "en": "Choose bank folder"},
    "ui.049": {"zh": "等待识别", "en": "Waiting for scan"},
    "ui.050": {"zh": "未选择目录", "en": "No folder selected"},
    "ui.051": {"zh": "目标目录不存在或不可访问", "en": "Target folder does not exist or is not accessible"},
    "ui.052": {"zh": "正在扫描", "en": "Scanning"},
    "ui.053": {"zh": "复制前 Bank 文件：{0}", "en": "Bank files before copy: {0}"},
    "ui.054": {"zh": "已有完整国家组：{0}", "en": "Complete country groups: {0}"},
    "ui.055": {"zh": "已有残缺国家组：{0}　计划新增：{1} 文件", "en": "Incomplete country groups: {0}　Planned additions: {1} files"},
    "ui.056": {"zh": "发现可补齐国家", "en": "Fillable countries found"},
    "ui.057": {"zh": "未发现可补齐国家", "en": "No fillable countries found"},
    "ui.058": {"zh": "来源国家组：{0}　待生成国家组：{1}　待生成文件数：{2}　预计生成后文件数：{3}", "en": "Source country groups: {0}　Country groups to create: {1}　Files to create: {2}　Files after generation: {3}"},
    "ui.059": {"zh": "复制前 Bank 文件：{0}　计划新增国家组：{1}　计划新增文件数：{2}　预计复制后 Bank 文件数：{3}", "en": "Bank files before copy: {0}　Country groups to add: {1}　Files to add: {2}　Bank files after copy: {3}"},
    "ui.060": {"zh": "复制结束，正在刷新结果", "en": "Copy finished, refreshing results"},
    "ui.061": {"zh": "成功", "en": "Success"},
    "ui.062": {"zh": "已取消", "en": "Cancelled"},
    "ui.063": {"zh": "国家组部分失败", "en": "Some country groups failed"},
    "ui.064": {"zh": "国家组失败", "en": "Country group failed"},
    "ui.065": {"zh": "国家组完成", "en": "Country group finished"},
    "ui.066": {"zh": "结果：{0}", "en": "Result: {0}"},
    "ui.067": {"zh": "无线电平均分配任务仍在运行。是否安全取消并在当前文件完成后关闭？", "en": "An average-distribution task for radio is still running. Cancel it safely and close after the current file?"},
    "ui.068": {"zh": "已导入 {0} 个文件", "en": "Imported {0} files"},
    "ui.069": {"zh": "已忽略 {0} 个文件夹", "en": "Ignored {0} folders"},
    "ui.070": {"zh": "已忽略 {0} 个重复路径", "en": "Ignored {0} duplicate paths"},
    "ui.071": {"zh": "已忽略 {0} 个无效路径", "en": "Ignored {0} invalid paths"},
    "ui.072": {"zh": "已拒绝 {0} 个超过平均分配上限的文件", "en": "Rejected {0} files that exceed the average-distribution limit"},
    "ui.073": {"zh": "尚未识别到可补全的无线电文件。", "en": "No radio files that can be completed yet."},
    "ui.074": {"zh": "没有可复制的文件", "en": "No files to copy"},
    "ui.075": {"zh": "请先导入已识别的文件，并至少选择一个待生成名称。", "en": "Import recognized files first and tick at least one name to create."},
    "ui.076": {"zh": "发现外部目标文件冲突", "en": "External target-file conflicts found"},
    "ui.077": {"zh": "本批任务中有 {0} 个外部目标文件已存在。", "en": "{0} external target files already exist in this batch."},
    "ui.078": {"zh": "本次导入源文件所对应的目标会在安全暂存后按平均分配计划重写；以下选项仅应用于其他已存在文件。", "en": "Targets that match the imported sources are rewritten from a safe staging copy by the average-distribution plan; the option below applies only to other existing files."},
    "ui.079": {"zh": "跳过外部冲突文件", "en": "Skip conflicting external files"},
    "ui.080": {"zh": "覆盖外部冲突文件", "en": "Overwrite conflicting external files"},
    "ui.081": {"zh": "取消本次任务", "en": "Cancel this task"},
    "ui.082": {"zh": "新建 {0}，覆盖 {1}，跳过 {2}，失败 {3}，取消 {4}。", "en": "Created {0}, overwritten {1}, skipped {2}, failed {3}, cancelled {4}."},
    "ui.083": {"zh": "部分无线电文件复制失败", "en": "Some radio files failed to copy"},
    "ui.084": {"zh": "本批任务有 {0} 个文件失败。", "en": "{0} files failed in this batch."},
    "ui.085": {"zh": "请选择对本批所有外部冲突文件统一应用的处理方式。", "en": "Choose how to handle every conflicting external file in this batch."},
    "ui.086": {"zh": "部分组别已回退顺序复制", "en": "Some groups fell back to sequential copy"},
    "ui.087": {"zh": "当前组别无法使用平均分配模式，已自动顺序分配", "en": "The current group cannot use average distribution; sequential copy was applied automatically"},
    "ui.088": {"zh": "无法切换到平均分配", "en": "Cannot switch to average distribution"},
    "ui.089": {"zh": "超过平均分配导入上限", "en": "Over the average-distribution import limit"},
    "ui.090": {"zh": "当前文件数超过平均分配上限，已保持顺序复制。", "en": "The current file count exceeds the average-distribution limit; sequential copy is kept."},
    "ui.091": {"zh": "部分文件超过平均分配上限，未加入列表。", "en": "Some files exceed the average-distribution limit and were not added to the list."},
    "ui.092": {"zh": "项目组：{0}\n源目录：{1}\n成员数：{2}\n最多允许：{3}\n实际导入：{4}", "en": "Project group: {0}\nSource folder: {1}\nMembers: {2}\nAllowed at most: {3}\nImported: {4}"},
    "ui.093": {"zh": "项目组：{0}\n成员数：{1}\n最多允许：{2}\n实际尝试：{3}\n拒绝文件：\n", "en": "Project group: {0}\nMembers: {1}\nAllowed at most: {2}\nAttempted: {3}\nRejected files:\n"},
    "ui.094": {"zh": "已保留此前成功导入的文件，超出上限的文件未加入列表。", "en": "Previously imported files were kept; files over the limit were not added to the list."},
    "ui.095": {"zh": "无线电平均分配构建器尚未初始化。", "en": "The radio average-distribution builder is not initialized yet."},
    "ui.096": {"zh": "{0}文件复制任务仍在运行。是否安全取消并在当前文件完成后关闭？", "en": "A {0} file-copy task is still running. Cancel it safely and close after the current file?"},
    "ui.097": {"zh": "自动检索与补全", "en": "Auto scan & completion"},
    "ui.098": {"zh": "扫描目标目录后，仅补全已出现但尚不完整的{0}名称组。", "en": "After scanning the target folder, only {0} name groups that appeared but are still incomplete are filled in."},
    "ui.099": {"zh": "自动补全进度", "en": "Auto-completion progress"},
    "ui.100": {"zh": "可导入多个实际文件；未识别文件会保留在列表中。", "en": "You can import several real files; unrecognized files stay in the list."},
    "ui.101": {"zh": "仅显示从内置名称库精确识别出的分组；每个目标可单独取消。", "en": "Only groups recognized exactly from the built-in name library are shown; every target can be deselected."},
    "ui.102": {"zh": "同组多个来源会在导入或移除时自动随机且均衡地分配，无需手动选择。", "en": "Multiple sources in a group are distributed randomly and evenly on import or removal; no manual choice is needed."},
    "ui.103": {"zh": "显示本次结果", "en": "Show these results"},
    "ui.104": {"zh": "来源路径", "en": "Source path"},
    "ui.105": {"zh": "目标路径", "en": "Target path"},
    "ui.106": {"zh": "所有文件 (*)", "en": "All files (*)"},
    "ui.107": {"zh": "已移除文件，并自动更新受影响名称组的来源分配。", "en": "Files removed; source assignment of the affected name groups was updated automatically."},
    "ui.108": {"zh": "列表已清空。", "en": "The list is now empty."},
    "ui.109": {"zh": "尚未识别到可补全的{0}文件。", "en": "No {0} files that can be completed yet."},
    "ui.110": {"zh": "发现已存在的目标文件", "en": "Existing target files found"},
    "ui.111": {"zh": "本批任务中有 {0} 个目标文件已存在。", "en": "{0} target files already exist in this batch."},
    "ui.112": {"zh": "请选择对本批冲突文件统一应用的处理方式。", "en": "Choose how to handle every conflicting file in this batch."},
    "ui.113": {"zh": "跳过已存在文件", "en": "Skip existing files"},
    "ui.114": {"zh": "覆盖已存在文件", "en": "Overwrite existing files"},
    "ui.115": {"zh": "请选择对本批所有冲突文件统一应用的处理方式。", "en": "Choose how to handle every conflicting file in this batch."},
    "ui.116": {"zh": "成功 {0}，跳过 {1}，失败 {2}。", "en": "Succeeded {0}, skipped {1}, failed {2}."},
    "ui.117": {"zh": "选择目标目录", "en": "Choose target folder"},
    "ui.118": {"zh": "未发现可识别的{0}文件", "en": "No recognizable {0} files found"},
    "ui.119": {"zh": "所有已出现的触发组均已完整", "en": "Every triggered group that appeared is already complete"},
    "ui.120": {"zh": "发现缺失文件", "en": "Missing files found"},
    "ui.121": {"zh": "目标目录已不存在，请重新识别", "en": "The target folder no longer exists; scan again"},
    "ui.122": {"zh": "没有可补全的文件", "en": "No files to complete"},
    "ui.123": {"zh": "请先完成识别，并至少选择一个待补全文件。", "en": "Finish scanning first and tick at least one file to complete."},
    "ui.124": {"zh": "正在补全", "en": "Completing"},
    "ui.125": {"zh": "补全未完成。", "en": "Completion did not finish."},
    "ui.126": {"zh": "补全完成，正在刷新结果", "en": "Completion finished, refreshing results"},
    "ui.127": {"zh": "部分文件补全失败，正在刷新结果", "en": "Some files failed to complete, refreshing results"},
    "ui.128": {"zh": "任务已取消，正在刷新结果", "en": "Task cancelled, refreshing results"},
    "ui.129": {"zh": "补全结束，正在刷新结果", "en": "Completion finished, refreshing results"},
    "ui.130": {"zh": "语音处理", "en": "Audio Processing"},
    "ui.131": {"zh": "选择语音制作项目根目录", "en": "Choose the voice project root folder"},
    "ui.132": {"zh": "选择", "en": "Choose"},
    "ui.133": {"zh": "重新扫描", "en": "Rescan"},
    "ui.134": {"zh": "车组", "en": "Crew"},
    "ui.135": {"zh": "无线电", "en": "Radio"},
    "ui.136": {"zh": "目标文件名", "en": "Target file name"},
    "ui.137": {"zh": "粘贴名称、带扩展名的名称或完整路径", "en": "Paste a name, a name with extension, or a full path"},
    "ui.138": {"zh": "请输入需要制作的目标文件名。", "en": "Enter the target file name to create."},
    "ui.139": {"zh": "同组待制作项目", "en": "Pending items in this group"},
    "ui.140": {"zh": "添加音频", "en": "Add audio"},
    "ui.141": {"zh": "插入2秒空白", "en": "Insert 2 s silence"},
    "ui.142": {"zh": "删除选中", "en": "Delete selected"},
    "ui.143": {"zh": "音频裁剪", "en": "Trim audio"},
    "ui.144": {"zh": "撤销", "en": "Undo"},
    "ui.145": {"zh": "试听音轨", "en": "Preview track"},
    "ui.146": {"zh": "停止", "en": "Stop"},
    "ui.147": {"zh": "循环选中", "en": "Loop selection"},
    "ui.148": {"zh": "时间轴缩放", "en": "Timeline zoom"},
    "ui.149": {"zh": "导出设置", "en": "Export settings"},
    "ui.150": {"zh": "单声道", "en": "Mono"},
    "ui.151": {"zh": "立体声", "en": "Stereo"},
    "ui.152": {"zh": "导出后保留音轨", "en": "Keep the track after export"},
    "ui.153": {"zh": "输出：—", "en": "Output: —"},
    "ui.154": {"zh": "开始导出", "en": "Start export"},
    "ui.155": {"zh": "工作线程数", "en": "Worker threads"},
    "ui.156": {"zh": "当前项目组进度", "en": "Current group progress"},
    "ui.157": {"zh": "请输入目标文件名。", "en": "Enter a target file name."},
    "ui.158": {"zh": "一键复制补齐", "en": "One-click copy & complete"},
    "ui.159": {"zh": "任务进度详情", "en": "Task progress details"},
    "ui.160": {"zh": "选择制作项目根目录", "en": "Choose the project root folder"},
    "ui.161": {"zh": "项目目录已就绪。", "en": "Project folder is ready."},
    "ui.162": {"zh": "创建项目目录失败：{0}", "en": "Failed to create the project folder: {0}"},
    "ui.163": {"zh": "目标名称含有 Windows 不允许的字符。", "en": "The target name contains characters that Windows does not allow."},
    "ui.164": {"zh": "已识别：{0} / {1} / {2}", "en": "Recognized: {0} / {1} / {2}"},
    "ui.165": {"zh": "该名称已收录，但未分类；将按当前分类导出。", "en": "The name is known but has no category; it is exported with the current category."},
    "ui.166": {"zh": "该名称未收录；将按当前分类导出。", "en": "The name is unknown; it is exported with the current category."},
    "ui.167": {"zh": "第 {0} 组：{1} ～ {2}（{3}/3）", "en": "Group {0}: {1} – {2} ({3}/3)"},
    "ui.168": {"zh": "请输入已收录的目标文件名。", "en": "Enter a target file name from the built-in library."},
    "ui.169": {"zh": "完成度：{0} / {1}", "en": "Completion: {0} / {1}"},
    "ui.170": {"zh": "已制作：{0}", "en": "Created: {0}"},
    "ui.171": {"zh": "待制作：{0}", "en": "Pending: {0}"},
    "ui.172": {"zh": "完整小组：{0} / {1}", "en": "Complete subgroups: {0} / {1}"},
    "ui.173": {"zh": "同名多格式：", "en": "Same name, multiple formats:"},
    "ui.174": {"zh": "输出：{0}", "en": "Output: {0}"},
    "ui.175": {"zh": "平均分配目标：\n", "en": "Average-distribution targets:\n"},
    "ui.176": {"zh": "当前项目组已完整。", "en": "The current group is already complete."},
    "ui.177": {"zh": "未知错误", "en": "Unknown error"},
    "ui.178": {"zh": "平均分配补齐有 {0} 个文件失败。", "en": "{0} files failed during average-distribution completion."},
    "ui.179": {"zh": "平均分配补齐未全部完成", "en": "Average-distribution completion did not finish"},
    "ui.180": {"zh": "有 {0} 个目标文件复制失败：\n{1}", "en": "{0} target files failed to copy:\n{1}"},
    "ui.181": {"zh": "选择音频", "en": "Choose audio"},
    "ui.182": {"zh": "音频文件 (*.wav *.flac *.mp3 *.ogg *.m4a *.aac *.opus)", "en": "Audio files (*.wav *.flac *.mp3 *.ogg *.m4a *.aac *.opus)"},
    "ui.183": {"zh": "无法导入 {0}：文件不存在", "en": "Cannot import {0}: file not found"},
    "ui.184": {"zh": "正在解析音频时长与波形……", "en": "Reading audio duration and waveform…"},
    "ui.185": {"zh": "已导入：{0}", "en": "Imported: {0}"},
    "ui.186": {"zh": "无法导入 {0}：{1}", "en": "Cannot import {0}: {1}"},
    "ui.187": {"zh": "裁切：{0} - {1}，{2}", "en": "Trim: {0} - {1}, {2}"},
    "ui.188": {"zh": "请先点击音频片段中的裁剪位置。", "en": "Click the trim position inside an audio clip first."},
    "ui.189": {"zh": "当前有后台任务运行，请稍后再执行音频裁剪。", "en": "A background task is running; trim audio later."},
    "ui.190": {"zh": "已在 {0} s 处将音频切分为两段。", "en": "Audio split into two clips at {0} s."},
    "ui.191": {"zh": "请先设置项目目录、合法目标名称和至少一个音轨。", "en": "Set a project folder, a valid target name and at least one audio track first."},
    "ui.192": {"zh": "目标已存在", "en": "Target already exists"},
    "ui.193": {"zh": "是否覆盖现有 WAV 文件？", "en": "Overwrite the existing WAV file?"},
    "ui.194": {"zh": "当前项目组不符合平均分配条件，已保持顺序复制。", "en": "The current group does not qualify for average distribution; sequential copy is kept."},
    "ui.195": {"zh": "目标名称不属于当前矩阵项目组。", "en": "The target name does not belong to the current matrix group."},
    "ui.196": {"zh": "该三成员小组已经完成，请从待制作下拉列表选择其他小组。", "en": "This three-member subgroup is already complete; choose another subgroup from the pending list."},
    "ui.197": {"zh": "存在其他音频格式", "en": "Other audio formats exist"},
    "ui.198": {"zh": "平均分配不会删除或改写非 WAV 文件。请先处理以下同名文件：\n", "en": "Average distribution never deletes or rewrites non-WAV files. Handle these same-name files first:\n"},
    "ui.199": {"zh": "重新生成未完整小组", "en": "Regenerate incomplete subgroups"},
    "ui.200": {"zh": "平均分配将覆盖以下已有成员：\n", "en": "Average distribution will overwrite these existing members:\n"},
    "ui.202": {"zh": "请先向音轨中导入音频。", "en": "Import audio into the track first."},
    "ui.203": {"zh": "请先选择需要循环的片段。", "en": "Select the clip to loop first."},
    "ui.204": {"zh": "正在准备试听：{0}", "en": "Preparing preview: {0}"},
    "ui.205": {"zh": "试听失败：{0}", "en": "Preview failed: {0}"},
    "ui.206": {"zh": "全部音频片段：(clip_id, 时间轴起点, 显示名, 路径, trim_start, trim_end)。", "en": "Every audio clip: (clip_id, timeline start, display name, path, trim_start, trim_end)."},
    "ui.207": {"zh": "已在 {0} 处静音处切分。", "en": "Split at the silence at {0}."},
    "ui.208": {"zh": "正在生成频谱图，请稍候。", "en": "Generating the spectrum image, please wait."},
    "ui.209": {"zh": "峰值归一化：{0} dBFS", "en": "Peak normalization: {0} dBFS"},
    "ui.210": {"zh": "响度归一化：{0} LUFS", "en": "Loudness normalization: {0} LUFS"},
    "ui.201": {"zh": "\n\n是否继续？", "en": "\n\nContinue?"},
    "ui.211": {"zh": "响度处理：关闭", "en": "Loudness: off"},
    "ui.212": {"zh": "面板响度目标：与导出处理对话框共用同一目标值并立即持久化。", "en": "Panel loudness target: shared with the export processing dialog and saved immediately."},
    "ui.213": {"zh": "任何影响 pre-loudnorm 链的处理变化都使既有响度测量失效。", "en": "Any processing change that affects the pre-loudnorm chain invalidates existing loudness measurements."},
    "ui.214": {"zh": "格式切换：联动质量档与 Opus 的采样率约束，并持久化选择。", "en": "format switching: pairs the quality level with Opus sample-rate limits and saves the choice."},
    "ui.215": {"zh": "平均分配导出固定 WAV：矩阵模式下锁定格式选择并显示提示。", "en": "Average-distribution export always writes WAV: in matrix mode the format choice is locked with a notice."},
    "ui.216": {"zh": "正在准备补齐", "en": "Preparing completion"},
    "ui.217": {"zh": "无法平均补齐", "en": "Cannot complete by average distribution"},
    "ui.218": {"zh": "存在不同格式的同名文件", "en": "Same-name files in different formats exist"},
    "ui.219": {"zh": "平均补齐不会删除或制造同名多格式。请先处理：\n", "en": "Average completion never deletes or creates same-name files in several formats. Handle these first:\n"},
    "ui.220": {"zh": "{0} → 第{1}组", "en": "{0} → group {1}"},
    "ui.221": {"zh": "来源到目标映射：\n", "en": "Source-to-target mapping:\n"},
    "ui.222": {"zh": "\n\n将重写 {0} 个来源目标", "en": "\n\n{0} source targets will be rewritten"},
    "ui.223": {"zh": "\n将新建 {0} 个目标", "en": "\n{0} targets will be created"},
    "ui.224": {"zh": "\n外部冲突 {0} 个", "en": "\n{0} external conflicts"},
    "ui.225": {"zh": "\n最终分配：{0}", "en": "\nFinal distribution: {0}"},
    "ui.226": {"zh": "\n\n提示：\n", "en": "\n\nNotes:\n"},
    "ui.227": {"zh": "确认平均分配补齐", "en": "Confirm average-distribution completion"},
    "ui.228": {"zh": "\n\n是否开始？", "en": "\n\nStart now?"},
    "ui.229": {"zh": "目标文件状态已变化", "en": "Target file status changed"},
    "ui.230": {"zh": "确认期间出现了新的目标文件，请检查后重新确认：\n", "en": "New target files appeared during confirmation; review them and confirm again:\n"},
    "ui.231": {"zh": "平均分配补齐未能启动：{0}", "en": "Average-distribution completion could not start: {0}"},
    "ui.232": {"zh": "平均分配补齐未能启动：\n{0}", "en": "Average-distribution completion could not start:\n{0}"},
    "ui.233": {"zh": "无法启动复制任务", "en": "Cannot start the copy task"},
    "ui.234": {"zh": "正在暂存平均分配来源", "en": "Staging average-distribution sources"},
    "ui.235": {"zh": "平均分配补齐未启动：复制服务正忙，请稍后重试。", "en": "Average-distribution completion did not start: the copy service is busy, try again later."},
    "ui.236": {"zh": "复制任务未启动", "en": "Copy task did not start"},
    "ui.237": {"zh": "复制服务正忙，请稍后重试。", "en": "The copy service is busy, try again later."},
    "home.card.tts.title": {"zh": "TTS生成", "en": "TTS Generation"},
    "home.card.tts.desc": {"zh": "用于自定义音频制作", "en": "Create custom voice audio"},
    "page.tts_model.title": {"zh": "TTS生成", "en": "TTS Generation"},
    "page.voice_batch.title": {"zh": "语音批量生成", "en": "Batch Voice Generation"},
    "tts.card.gpt.title": {"zh": "GPT-SoVITS", "en": "GPT-SoVITS"},
    "tts.card.gpt.desc": {"zh": "用于算力充足情况下进行制作", "en": "For machines with plenty of compute"},
    "tts.card.cosy.title": {"zh": "CosyVoice 3 GGUF", "en": "CosyVoice 3 GGUF"},
    "tts.card.cosy.desc": {"zh": "用于算力不足情况下（如仅CPU）制作", "en": "For limited compute (for example CPU-only)"},
    "tts.badge.ready": {"zh": "模型已就绪", "en": "Model ready"},
    "tts.badge.missing": {"zh": "模型未就绪", "en": "Model not ready"},
    "voice.table.title": {"zh": "语音生成列表", "en": "Voice generation list"},
    "voice.table.hint": {"zh": "双击单元格编辑名称/文本/音色；名称须符合 WT_DEFAULT 规则（ASCII、.wav）。`.vt` 只读工程与 `.json` 可经「更多 → 打开工程…」导入。", "en": "Double-click a cell to edit name, text or voice; names must satisfy the WT_DEFAULT rule (ASCII, .wav). Import a read-only .vt project or a .json via More → Open project."},
    "voice.weights.gpt_hint": {"zh": "GPT 权重路径（.ckpt）", "en": "GPT weights path (.ckpt)"},
    "voice.weights.sovits_hint": {"zh": "SoVITS 权重路径（.pth）", "en": "SoVITS weights path (.pth)"},
    "voice.weights.apply": {"zh": "应用权重", "en": "Apply weights"},
    "voice.weights.applying": {"zh": "正在应用权重…", "en": "Applying weights…"},
    "voice.weights.applied": {"zh": "权重已切换，后续生成将使用新音色。", "en": "Weights applied; new generations will use them."},
    "voice.weights.failed": {"zh": "权重切换失败：{message}", "en": "Failed to apply weights: {message}"},
    "voice.weights.unsupported": {"zh": "当前后端不支持切换权重。", "en": "The current backend does not support switching weights."},
    "voice.col.status": {"zh": "状态", "en": "Status"},
    "voice.col.name": {"zh": "名称", "en": "Name"},
    "voice.col.text": {"zh": "文本", "en": "Text"},
    "voice.col.voice": {"zh": "音色", "en": "Voice"},
    "voice.col.duration": {"zh": "时长", "en": "Duration"},
    "voice.col.actions": {"zh": "操作", "en": "Actions"},
    "voice.status.pending": {"zh": "未完成", "en": "Pending"},
    "voice.status.running": {"zh": "正在生成", "en": "Generating"},
    "voice.status.done": {"zh": "已完成", "en": "Done"},
    "voice.status.regenerate": {"zh": "需要重新生成", "en": "Needs regeneration"},
    "voice.status.failed": {"zh": "生成失败", "en": "Generation failed"},
    "voice.tip.stale": {"zh": "创作内容已变更，需重新生成", "en": "Source content changed; regenerate required"},
    "voice.action.add": {"zh": "添加行", "en": "Add row"},
    "voice.action.duplicate": {"zh": "复制行", "en": "Duplicate row"},
    "voice.action.remove": {"zh": "删除行", "en": "Remove row"},
    "voice.action.generate_selected": {"zh": "生成选中行", "en": "Generate selected"},
    "voice.action.generate_stale": {"zh": "生成未完成项", "en": "Generate pending"},
    "voice.action.stop": {"zh": "停止", "en": "Stop"},
    "voice.action.more": {"zh": "更多", "en": "More"},
    "voice.action.preview": {"zh": "试听", "en": "Preview"},
    "voice.action.regenerate": {"zh": "重新生成", "en": "Regenerate"},
    "voice.preview.missing": {"zh": "该行尚无音频产物，请先生成。", "en": "This row has no audio yet; generate it first."},
    "voice.preview.playing": {"zh": "正在试听：{name}", "en": "Previewing: {name}"},
    "voice.action.export_vt": {"zh": "导出 .vt", "en": "Export .vt"},
    "voice.export.title": {"zh": "导出 .vt 工程", "en": "Export .vt project"},
    "voice.export.done": {"zh": "已导出：{name}", "en": "Exported: {name}"},
    "voice.export.done_signed": {"zh": "已签名并导出：{name}", "en": "Signed and exported: {name}"},
    "voice.export.unavailable": {"zh": "未构建 Rust 扩展 vtcore，无法导出 .vt（见 README「可选组件：vtcore」）", "en": "The Rust extension vtcore is not built; .vt export is unavailable (see README, \"Optional component: vtcore\")"},
    "voice.export.locked": {"zh": "目标文件已签名且处于只读锁，请另存为新文件", "en": "The target file is signed and read-only locked; save as a new file"},
    "voice.export.failed": {"zh": "导出失败：{code}", "en": "Export failed: {code}"},
    "voice.action.export_vt_signed": {"zh": "签名并导出 .vt", "en": "Sign and export .vt"},
    "voice.action.keys": {"zh": "密钥…", "en": "Keys…"},
    "voice.keys.title": {"zh": "签名密钥", "en": "Signing keys"},
    "voice.keys.none": {"zh": "尚未创建签名密钥。", "en": "No signing key has been created yet."},
    "voice.keys.hint": {"zh": "私钥受系统凭据库保护后存放于 config/，不会进入工程文件或导出产物。", "en": "Private keys are protected by the OS credential store under config/ and never enter project files or exports."},
    "voice.keys.created": {"zh": "已创建密钥：{key_id}", "en": "Created key: {key_id}"},
    "voice.keys.current": {"zh": "当前密钥：{key_id}", "en": "Current key: {key_id}"},
    "voice.keys.public": {"zh": "公钥", "en": "Public key"},
    "voice.keys.generate": {"zh": "生成新密钥", "en": "Generate new key"},
    "voice.keys.copy_public": {"zh": "复制公钥", "en": "Copy public key"},
    "voice.keys.copied": {"zh": "公钥已复制到剪贴板", "en": "Public key copied to clipboard"},
    "voice.keys.unreadable": {"zh": "密钥不可读：{code}", "en": "Key unreadable: {code}"},
    "voice.sign.confirm": {"zh": "尚未创建签名密钥，是否现在生成一个？\n（私钥存放于 config/，受系统凭据库保护）", "en": "No signing key yet. Create one now?\n(The private key lives under config/, protected by the OS credential store.)"},
    "voice.action.open_project": {"zh": "打开工程…", "en": "Open project…"},
    "voice.action.unlock_project": {"zh": "解锁以编辑", "en": "Unlock to edit"},
    "voice.open.title": {"zh": "打开语音工程", "en": "Open voice project"},
    "voice.open.vt_editable": {"zh": "已打开工程（可编辑）：{name}（{count} 行）", "en": "Opened project (editable): {name} ({count} rows)"},
    "voice.open.vt_readonly": {"zh": "已打开工程（只读，已签名）：{name}（{count} 行）", "en": "Opened project (read-only, signed): {name} ({count} rows)"},
    "voice.open.json_retired": {"zh": "本版本只支持 .vt 工程文件", "en": "This build supports .vt project files only"},
    "voice.open.failed": {"zh": "打开失败：{code}", "en": "Open failed: {code}"},
    "voice.open.not_supported": {"zh": "只支持 .vt 工程文件", "en": "Only .vt project files are supported"},
    "voice.open.filter": {"zh": "语音工程", "en": "Voice projects"},
    "voice.project.no_backend": {"zh": "未构建 vtcore 扩展：工程读写不可用（详见「关于与许可」）", "en": "vtcore extension not built: project read/write unavailable (see About & Licenses)"},
    "voice.project.save_failed": {"zh": "工程保存失败：{code}", "en": "Project save failed: {code}"},
    "voice.unlock.done": {"zh": "已解锁并可编辑：{name}（保存将写出未签名容器）", "en": "Unlocked for editing: {name} (saving writes an unsigned container)"},
    "voice.unlock.failed": {"zh": "解锁失败：{code}", "en": "Unlock failed: {code}"},
    "voice.lock.badge": {"zh": "🔒 已签名并锁定：{name}", "en": "🔒 Signed and locked: {name}"},
    "voice.action.verify_vt": {"zh": "校验 .vt…", "en": "Verify .vt…"},
    "voice.verify.title": {"zh": "校验 .vt 文件", "en": "Verify .vt file"},
    "voice.verify.ok": {"zh": "签名有效（{key_id}）", "en": "Signature valid ({key_id})"},
    "voice.verify.ok_trusted": {"zh": "签名有效 · 已信任（{key_id}）", "en": "Signature valid · trusted ({key_id})"},
    "voice.verify.unsigned": {"zh": "未签名：内容自洽校验通过", "en": "Unsigned: structural checks passed"},
    "voice.verify.revoked": {"zh": "签名者密钥已被撤销：{key_id}", "en": "Signer key revoked: {key_id}"},
    "voice.verify.rotated": {"zh": "该工程的签名者已变更且无轮换记录：{key_id}", "en": "Signer changed without a rotation record: {key_id}"},
    "voice.verify.failed": {"zh": "校验失败：{code}", "en": "Verification failed: {code}"},
    "voice.trust.prompt": {"zh": "首次见到该签名者：\n{key_id}\n是否信任并记住？", "en": "First time seeing this signer:\n{key_id}\nTrust and remember?"},
    "voice.trust.remember": {"zh": "信任并记住", "en": "Trust and remember"},
    "voice.trust.once": {"zh": "仅本次", "en": "Just once"},
    "voice.trust.reject": {"zh": "拒绝", "en": "Reject"},
    "voice.trust.once_done": {"zh": "已校验（本次未记住该密钥）", "en": "Verified (key not remembered)"},
    "voice.trust.rejected": {"zh": "已拒绝：未信任的签名者", "en": "Rejected: untrusted signer"},
    "voice.action.export_manifest": {"zh": "导出整包清单…", "en": "Export package manifest…"},
    "voice.action.verify_package": {"zh": "校验整包…", "en": "Verify package…"},
    "voice.manifest.choose": {"zh": "选择整包目录", "en": "Choose package folder"},
    "voice.manifest.exported": {"zh": "清单已写入：{name}（{count} 个文件）", "en": "Manifest written: {name} ({count} files)"},
    "voice.manifest.failed": {"zh": "清单操作失败：{code}", "en": "Manifest failed: {code}"},
    "voice.manifest.report": {"zh": "整包校验：{summary}", "en": "Package check: {summary}"},
    "voice.summary.counts": {"zh": "共 {total} 行 · 已完成 {done} · 待重新生成 {stale} · 未完成 {pending}", "en": "{total} rows · {done} done · {stale} to regenerate · {pending} pending"},
    "voice.choose_output": {"zh": "选择输出目录", "en": "Choose output folder"},
    "voice.backend.demo": {"zh": "未检测到推理服务，当前为演示模式（不产生真实语音）", "en": "No inference service detected; running in demo mode (no real audio)"},
    "voice.backend.ready": {"zh": "推理服务：{name}", "en": "Inference backend: {name}"},
    "voice.backend.connecting": {"zh": "正在连接推理服务…", "en": "Connecting to the inference service…"},
    "voice.pane.train": {"zh": "微调界面", "en": "Fine-tuning"},
    "voice.pane.inference": {"zh": "推理界面", "en": "Inference"},
    "voice.pane.model": {"zh": "模型信息", "en": "Model info"},
    "voice.cosy.note": {"zh": "CosyVoice 3 GGUF 为推理专用模型；微调训练请使用 GPT-SoVITS。", "en": "CosyVoice 3 GGUF is inference-only; use GPT-SoVITS for fine-tuning."},
    "voice.cosy.model_dir": {"zh": "模型目录：{path}", "en": "Model folder: {path}"},
    "voice.cosy.ready": {"zh": "模型文件齐备（{count} 个 GGUF），可开始生成。", "en": "Model files ready ({count} GGUF); you can start generating."},
    "voice.cosy.missing": {"zh": "模型文件缺失（{count}/{need} 个 GGUF）。请到模型选择页查看下载提示。", "en": "Model files missing ({count}/{need} GGUF). See the model page for download hints."},
    "voice.cosy.service": {"zh": "推理服务由工作台自动拉起与停止（本地 HTTP，仅监听本机）。", "en": "The inference service is started and stopped automatically (local HTTP, loopback only)."},
    "voice.params.title_gpt": {"zh": "推理参数（GPT-SoVITS）", "en": "Inference parameters (GPT-SoVITS)"},
    "voice.params.title_cosy": {"zh": "推理参数（CosyVoice 3）", "en": "Inference parameters (CosyVoice 3)"},
    "voice.params.hint": {"zh": "参数随每次合成请求一并下发；不同后端支持的字段不同。", "en": "Parameters are sent with every synthesis request; supported fields differ per backend."},
    "voice.params.toggle": {"zh": "推理参数", "en": "Parameters"},
    "voice.params.speed": {"zh": "语速", "en": "Speed"},
    "voice.params.seed_fixed": {"zh": "固定随机种子", "en": "Fix random seed"},
    "voice.params.seed": {"zh": "随机种子", "en": "Random seed"},
    "voice.params.top_k": {"zh": "top-k 采样", "en": "top-k sampling"},
    "voice.params.top_p": {"zh": "top-p 采样", "en": "top-p sampling"},
    "voice.params.temperature": {"zh": "温度", "en": "Temperature"},
    "voice.params.text_split": {"zh": "文本切分方式", "en": "Text split method"},
    "voice.params.prompt_text": {"zh": "参考音频文本", "en": "Reference audio text"},
    "voice.params.prompt_text_hint": {"zh": "留空则交由后端处理", "en": "Leave empty to let the backend decide"},
    "voice.params.prompt_lang": {"zh": "参考文本语言", "en": "Reference text language"},
    "voice.name.ok": {"zh": "名称可用", "en": "Name is available"},
    "train.group.dataset": {"zh": "数据集", "en": "Dataset"},
    "train.group.hyper": {"zh": "训练超参", "en": "Training hyperparameters"},
    "train.group.stages": {"zh": "阶段", "en": "Stages"},
    "train.hint": {"zh": "训练由上游 GPT-SoVITS 脚本执行，因此必须指定装有 torch 的 Python 解释器；首次使用请先「一键处理数据」。", "en": "Training runs the upstream GPT-SoVITS scripts, so point at a Python interpreter with torch installed; run \"Prepare dataset\" first."},
    "train.field.repo": {"zh": "上游仓库", "en": "Upstream repo"},
    "train.field.python": {"zh": "Python 解释器", "en": "Python interpreter"},
    "train.field.list": {"zh": "数据集清单", "en": "Dataset list"},
    "train.field.wav_dir": {"zh": "音频目录", "en": "Audio folder"},
    "train.field.exp_name": {"zh": "实验名", "en": "Experiment name"},
    "train.field.exp_hint": {"zh": "字母/数字，用作输出目录名", "en": "Letters and digits; used as the output folder name"},
    "train.field.version": {"zh": "模型版本", "en": "Model version"},
    "train.field.gpu": {"zh": "GPU 编号", "en": "GPU numbers"},
    "train.field.half": {"zh": "半精度（fp16）", "en": "Half precision (fp16)"},
    "train.field.s2_epochs": {"zh": "SoVITS 轮数", "en": "SoVITS epochs"},
    "train.field.s2_batch": {"zh": "SoVITS 批大小", "en": "SoVITS batch size"},
    "train.field.s2_save_every": {"zh": "SoVITS 保存间隔（轮）", "en": "SoVITS save every N epochs"},
    "train.field.s2_low_lr": {"zh": "SoVITS 低学习率比例", "en": "SoVITS text low-LR rate"},
    "train.field.s2_lora": {"zh": "LoRA 秩", "en": "LoRA rank"},
    "train.field.s1_epochs": {"zh": "GPT 轮数", "en": "GPT epochs"},
    "train.field.s1_batch": {"zh": "GPT 批大小", "en": "GPT batch size"},
    "train.field.s1_save_every": {"zh": "GPT 保存间隔（轮）", "en": "GPT save every N epochs"},
    "train.action.prep": {"zh": "一键处理数据", "en": "Prepare dataset"},
    "train.action.s2": {"zh": "训练 SoVITS", "en": "Train SoVITS"},
    "train.action.s1": {"zh": "训练 GPT", "en": "Train GPT"},
    "train.action.stop": {"zh": "停止", "en": "Stop"},
    "train.action.browse": {"zh": "浏览…", "en": "Browse…"},
    "train.stage.prep_text": {"zh": "1/5 文本与 BERT 特征", "en": "1/5 Text & BERT features"},
    "train.stage.prep_ssl": {"zh": "2/5 语音自监督特征", "en": "2/5 Self-supervised features"},
    "train.stage.prep_semantic": {"zh": "3/5 语义 Token", "en": "3/5 Semantic tokens"},
    "train.stage.train_s2": {"zh": "4/5 训练 SoVITS", "en": "4/5 Train SoVITS"},
    "train.stage.train_s1": {"zh": "5/5 训练 GPT", "en": "5/5 Train GPT"},
    "train.state.idle": {"zh": "待运行", "en": "Idle"},
    "train.state.running": {"zh": "运行中", "en": "Running"},
    "train.state.done": {"zh": "完成", "en": "Done"},
    "train.state.failed": {"zh": "失败", "en": "Failed"},
    "train.log.placeholder": {"zh": "训练日志会显示在这里", "en": "Training output appears here"},
    "train.log.started": {"zh": "开始训练：{name}", "en": "Training started: {name}"},
    "train.log.stopping": {"zh": "正在停止…", "en": "Stopping…"},
    "train.log.done": {"zh": "全部阶段完成", "en": "All stages completed"},
    "train.log.failed": {"zh": "训练中断或失败，详见日志", "en": "Training stopped or failed; see the log"},
    "train.error.missing_list": {"zh": "请先选择数据集清单（.list）", "en": "Select a dataset list (.list) first"},
    "train.error.missing_exp": {"zh": "请先填写实验名", "en": "Enter an experiment name first"},
    "train.error.busy": {"zh": "已有训练在运行", "en": "A training run is already in progress"},
    "train.tab.tools": {"zh": "数据集工具", "en": "Dataset tools"},
    "train.tab.train": {"zh": "微调训练", "en": "Fine-tuning"},
    "train.tools.slice": {"zh": "语音切分（0b）", "en": "Audio slicing (0b)"},
    "train.tools.slice_inp": {"zh": "音频输入路径（文件或文件夹）", "en": "Audio input path (file or folder)"},
    "train.tools.slice_opt": {"zh": "切分输出目录", "en": "Sliced output folder"},
    "train.tools.threshold": {"zh": "静音阈值 threshold", "en": "Silence threshold"},
    "train.tools.min_length": {"zh": "最短段长 min_length", "en": "Min segment length"},
    "train.tools.min_interval": {"zh": "最短切割间隔 min_interval", "en": "Min cut interval"},
    "train.tools.hop": {"zh": "音量计算步长 hop_size", "en": "Volume hop size"},
    "train.tools.max_sil": {"zh": "切后静音上限 max_sil_kept", "en": "Max trailing silence"},
    "train.tools.max_norm": {"zh": "归一化上限 max", "en": "Normalize max"},
    "train.tools.alpha": {"zh": "混入比例 alpha_mix", "en": "Alpha mix"},
    "train.tools.run_slice": {"zh": "开始切片", "en": "Start slicing"},
    "train.tools.asr": {"zh": "语音识别（0c，生成 .list）", "en": "ASR (0c, builds the .list)"},
    "train.tools.asr_inp": {"zh": "识别输入目录", "en": "ASR input folder"},
    "train.tools.asr_opt": {"zh": "识别输出目录", "en": "ASR output folder"},
    "train.tools.asr_backend": {"zh": "识别方式", "en": "ASR backend"},
    "train.tools.asr_size": {"zh": "模型规模", "en": "Model size"},
    "train.tools.asr_lang": {"zh": "识别语言", "en": "Language"},
    "train.tools.asr_precision": {"zh": "识别精度", "en": "Precision"},
    "train.tools.run_asr": {"zh": "开始识别", "en": "Start ASR"},
    "train.tools.missing_inp": {"zh": "请先填写音频输入路径", "en": "Enter the audio input path first"},
    "train.tools.missing_asr_inp": {"zh": "请先填写识别输入目录", "en": "Enter the ASR input folder first"},
    "train.action.readiness": {"zh": "前置体检", "en": "Pre-check"},
    "train.readiness.header": {"zh": "训练前置产物体检：", "en": "Pre-training artifact check:"},
    "train.readiness.text": {"zh": "文本分词产物", "en": "Text tokens"},
    "train.readiness.bert": {"zh": "BERT 特征", "en": "BERT features"},
    "train.readiness.cnhubert": {"zh": "HuBERT 特征", "en": "HuBERT features"},
    "train.readiness.wav32k": {"zh": "32k 音频", "en": "32k audio"},
    "train.readiness.semantic": {"zh": "语义标注", "en": "Semantic labels"},
    "train.readiness.ready": {"zh": "就绪", "en": "ready"},
    "train.readiness.missing": {"zh": "缺失", "en": "missing"},
    "train.log.weights_found": {"zh": "发现训练产物 —— GPT：{gpt}　SoVITS：{sovits}", "en": "Trained weights found — GPT: {gpt}　SoVITS: {sovits}"},
    "voice.name.empty": {"zh": "名称不能为空", "en": "Name must not be empty"},
    "voice.name.bad_chars": {"zh": "名称含不允许的字符（仅 ASCII 字母/数字/下划线）", "en": "Name contains characters that are not allowed (ASCII letters, digits and underscore only)"},
    "voice.name.too_long": {"zh": "名称过长", "en": "Name is too long"},
    "voice.name.reserved": {"zh": "名称是系统保留名", "en": "Name is reserved by the system"},
    "voice.name.bad_extension": {"zh": "扩展名必须是 .wav", "en": "Extension must be .wav"},
    "voice.name.conflict": {"zh": "同名文件已存在", "en": "A file with this name already exists"},
    "w.001": {"zh": "拖入文件或点击选择", "en": "Drop files here or click to choose"},
    "w.002": {"zh": "支持一次导入多个文件；文件夹会被忽略。", "en": "You can import several files at once; folders are ignored."},
    "w.003": {"zh": "选择文件", "en": "Choose files"},
    "w.004": {"zh": "状态：{0}", "en": "Status: {0}"},
    "w.005": {"zh": "有效音频：{0}", "en": "Valid audio: {0}"},
    "w.006": {"zh": "触发组：{0}", "en": "Triggered groups: {0}"},
    "w.007": {"zh": "缺失组：{0}", "en": "Missing groups: {0}"},
    "w.008": {"zh": "目录选择与扫描", "en": "Folder & scan"},
    "w.009": {"zh": "选择或粘贴目标目录路径", "en": "Choose or paste the target folder path"},
    "w.010": {"zh": "选择目录", "en": "Choose folder"},
    "w.011": {"zh": "开始识别", "en": "Start scan"},
    "w.012": {"zh": "重新识别", "en": "Scan again"},
    "w.013": {"zh": "包含子目录", "en": "Include subfolders"},
    "w.014": {"zh": "状态：未选择目录", "en": "Status: no folder selected"},
    "w.015": {"zh": "有效音频：0", "en": "Valid audio: 0"},
    "w.016": {"zh": "触发组：0", "en": "Triggered groups: 0"},
    "w.017": {"zh": "缺失组：0", "en": "Missing groups: 0"},
    "w.018": {"zh": "状态：", "en": "Status: "},
    "w.019": {"zh": "有效音频：", "en": "Valid audio: "},
    "w.020": {"zh": "触发组：", "en": "Triggered groups: "},
    "w.021": {"zh": "缺失组：", "en": "Missing groups: "},
    "w.022": {"zh": "已处理：{0} / {1}", "en": "Processed: {0} / {1}"},
    "w.023": {"zh": "成功：{0}", "en": "Succeeded: {0}"},
    "w.024": {"zh": "跳过：{0}", "en": "Skipped: {0}"},
    "w.025": {"zh": "失败：{0}", "en": "Failed: {0}"},
    "w.026": {"zh": "等待任务", "en": "Waiting for the task"},
    "w.027": {"zh": "正在准备", "en": "Preparing"},
    "w.028": {"zh": "正在处理", "en": "Processing"},
    "w.029": {"zh": "任务已暂停", "en": "Task paused"},
    "w.030": {"zh": "任务已完成", "en": "Task finished"},
    "w.031": {"zh": "任务部分失败", "en": "Some tasks failed"},
    "w.032": {"zh": "任务失败", "en": "Task failed"},
    "w.033": {"zh": "任务已取消", "en": "Task cancelled"},
    "w.034": {"zh": "进度：%p%", "en": "Progress: %p%"},
    "w.035": {"zh": "任务状态", "en": "Task status"},
    "w.036": {"zh": "状态：等待任务", "en": "Status: waiting for the task"},
    "w.037": {"zh": "已处理：0 / 0", "en": "Processed: 0 / 0"},
    "w.038": {"zh": "成功：0", "en": "Succeeded: 0"},
    "w.039": {"zh": "跳过：0", "en": "Skipped: 0"},
    "w.040": {"zh": "失败：0", "en": "Failed: 0"},
    "w.041": {"zh": "当前文件：", "en": "Current file: "},
    "w.042": {"zh": "开始", "en": "Start"},
    "w.043": {"zh": "暂停", "en": "Pause"},
    "w.044": {"zh": "已处理：", "en": "Processed: "},
    "w.045": {"zh": "成功：", "en": "Succeeded: "},
    "w.046": {"zh": "跳过：", "en": "Skipped: "},
    "w.047": {"zh": "失败：", "en": "Failed: "},
    "w.048": {"zh": "复制前文件数：{0}　计划新增：{1}　复制后文件数：{2}", "en": "Files before copy: {0}　Planned additions: {1}　Files after copy: {2}"},
    "w.049": {"zh": "扫描结果与待确认区", "en": "Scan results & pending confirmation"},
    "w.050": {"zh": "搜索基础名称", "en": "Search base name"},
    "w.051": {"zh": "仅显示缺失组", "en": "Show only missing groups"},
    "w.052": {"zh": "红色：目录中已存在　　白色：待复制补全", "en": "Red: already present　White: to be copied"},
    "w.053": {"zh": "复制前文件数：0　计划新增：0　复制后文件数：0", "en": "Files before copy: 0　Planned additions: 0　Files after copy: 0"},
    "w.054": {"zh": "暂无需要补全的触发组。", "en": "No triggered groups need completion."},
    "w.055": {"zh": "复制前文件数：", "en": "Files before copy: "},
    "w.056": {"zh": "　计划新增：", "en": "　Planned additions: "},
    "w.057": {"zh": "　复制后文件数：", "en": "　Files after copy: "},
    "w.058": {"zh": "类型：{0}　当前：{1} / {2}　缺失：{3}　补全后：{4}\n目录：{5}", "en": "Type: {0}　Current: {1} / {2}　Missing: {3}　After completion: {4}\nFolder: {5}"},
    "w.059": {"zh": "来源：{0}", "en": "Source: {0}"},
    "w.060": {"zh": "上次失败：{0}", "en": "Last failure: {0}"},
    "w.061": {"zh": "已存在文件", "en": "Existing files"},
    "w.062": {"zh": "待补全文件", "en": "Files to complete"},
    "w.063": {"zh": "本组全选", "en": "Select all in group"},
    "w.064": {"zh": "本组取消", "en": "Deselect group"},
    "w.065": {"zh": "类型：", "en": "Type: "},
    "w.066": {"zh": "　当前：", "en": "　Current: "},
    "w.067": {"zh": "　缺失：", "en": "　Missing: "},
    "w.068": {"zh": "　补全后：", "en": "　After completion: "},
    "w.069": {"zh": "\n目录：", "en": "\nFolder: "},
    "w.070": {"zh": "（同名多格式）", "en": "(same name, several formats)"},
    "w.071": {"zh": "来源：", "en": "Source: "},
    "w.072": {"zh": "输出：", "en": "Output: "},
    "w.073": {"zh": "上次失败：", "en": "Last failure: "},
    "w.074": {"zh": "项目组：{0}", "en": "Group: {0}"},
    "w.075": {"zh": "复制模式：{0}\n命名类型：{1}\n源目录：{2}", "en": "Copy mode: {0}\nName type: {1}\nSource folder: {2}"},
    "w.076": {"zh": "待处理 {0} 个，已选 {1} 个", "en": "{0} pending, {1} selected"},
    "w.077": {"zh": "第 {0} 小组来源：{1}", "en": "Subgroup {0} source: {1}"},
    "w.078": {"zh": "平均分配", "en": "Average distribution"},
    "w.079": {"zh": "顺序复制", "en": "Sequential copy"},
    "w.080": {"zh": "（平均分配不可用）", "en": "(average distribution unavailable)"},
    "w.081": {"zh": "　来源重写（平均分配所需）", "en": "　Source rewrite (required by average distribution)"},
    "w.082": {"zh": "项目组：", "en": "Group: "},
    "w.083": {"zh": "复制模式：", "en": "Copy mode: "},
    "w.084": {"zh": "\n命名类型：", "en": "\nName type: "},
    "w.085": {"zh": "\n源目录：", "en": "\nSource folder: "},
    "w.086": {"zh": "该组没有需要补全的文件。", "en": "This group has no files to complete."},
    "w.087": {"zh": "待处理 ", "en": "Pending "},
    "w.088": {"zh": " 个，已选 ", "en": ", selected "},
    "w.089": {"zh": " 个", "en": ""},
    "w.090": {"zh": "　外部文件冲突", "en": "　External file conflict"},
    "w.091": {"zh": "第 ", "en": "Subgroup "},
    "w.092": {"zh": " 小组来源：", "en": " source: "},
    "w.093": {"zh": "来源文件：{0}\n来源目录：{1}", "en": "Source files: {0}\nSource folder: {1}"},
    "w.094": {"zh": "待生成 {0} 个，已选 {1} 个", "en": "{0} to create, {1} selected"},
    "w.095": {"zh": "来源文件：", "en": "Source files: "},
    "w.096": {"zh": "\n来源目录：", "en": "\nSource folder: "},
    "w.097": {"zh": "待生成 ", "en": "To create "},
    "w.098": {"zh": "已识别", "en": "Recognized"},
    "w.099": {"zh": "缺少扩展名", "en": "Missing extension"},
    "w.100": {"zh": "未识别", "en": "Unrecognized"},
    "w.101": {"zh": "已导入 0 个文件", "en": "Imported 0 files"},
    "w.102": {"zh": "清空列表", "en": "Clear list"},
    "w.103": {"zh": "移除", "en": "Remove"},
    "w.104": {"zh": "已导入 ", "en": "Imported "},
    "w.105": {"zh": " 个文件", "en": " files"},
    "ui.238": {"zh": "文件", "en": "File"},
    "ui.239": {"zh": "来源", "en": "Source"},
    "ui.240": {"zh": "结果", "en": "Result"},
    "ui.241": {"zh": "失败", "en": "Failed"},
    "ui.242": {"zh": "项目目录：", "en": "Project folder:"},
    "ui.243": {"zh": "项目目录", "en": "Project folder"},
}

# 修改版自行撰写的说明：法律属性内容，不参与语言切换，固定以中文原文呈现。
# 英文摘要见 MODIFICATION_NOTICE.md 的 "Modification Notice (English Summary)" 一节。
_ABOUT_OURS = """
            <h3>修改版说明</h3>
            <p>本项目是 <b>Beiku</b>（@beikuwawa）原项目 <b>WT-NameRelay</b>
            （<a href="https://github.com/beikuwawa/WT-NameRelay">github.com/beikuwawa/WT-NameRelay</a>，
            beta 0.2.0）的 fork（非官方实验版），由 <b>Diderde</b> 制作与维护，
            不代表原项目作者，也不是原项目的官方版本。</p>
            <p>修改与新增代码以 <b>GNU GPL-3.0-only</b> 授权；原始代码仍按
            WT-NameRelay Source-Available License 1.0 授权。
            完整修改清单见许可页面中的“修改版声明”。</p>
            <hr>
"""

# 原始项目的"关于与许可"内容，逐字保留，不做翻译（法律与署名以原文为准）。
_ABOUT_ORIGINAL = """
            <h3>关于与许可</h3>
            <p>战争雷霆语音包文件名称补全、复制与语音处理工具。</p>
            <p>本工具为非官方第三方工具，不包含游戏官方资源，也不与
            Gaijin Entertainment 或 War Thunder 存在授权、赞助或合作关系。</p>
            <p><b>禁止对官方发布包进行二次售卖、倒卖、付费分发或捆绑收费。</b>
            此声明不替代第三方开源许可证已经授予的权利。</p>
            <p>项目原创部分采用 <b>WT-NameRelay Source-Available License 1.0</b>，
            允许个人非商业使用与同许可源码分享；本项目不是 OSI 定义的开源软件。</p>
            <h4>运行时第三方组件</h4>
            <ul>
              <li>CPython 3.11.5 — PSF License 2.0</li>
              <li>PySide6 6.7.3 / Qt for Python — LGPL-3.0 / GPL-3.0</li>
              <li>PyQtGraph 0.13.7 — MIT</li>
              <li>NumPy 1.26.4 — BSD-3-Clause</li>
              <li>OpenSSL 3.0.10 — Apache-2.0</li>
              <li>FFmpeg N-125829-gfe953596e9-20260728 — LGPL-3.0-or-later</li>
            </ul>
            <p>完整文本可在下方许可查看器与发布目录中查阅。</p>
    """

_current_language: str | None = None
_listeners: list[Callable[[str], None]] = []


def available_languages() -> dict[str, str]:
    return dict(_LANGUAGES)


def _system_language() -> str:
    if QLocale.system().language() == QLocale.Language.Chinese:
        return "zh"
    return "en"


def current_language() -> str:
    global _current_language
    if _current_language is None:
        stored = get_preference(LANGUAGE_KEY)
        if stored in _LANGUAGES:
            _current_language = stored
        else:
            _current_language = _system_language()
    return _current_language


def set_language(language: str) -> None:
    global _current_language
    if language not in _LANGUAGES:
        raise ValueError(f"不支持的语言：{language}")
    if language == _current_language:
        return
    _current_language = language
    set_preference(LANGUAGE_KEY, language)
    for listener in _listeners:
        listener(language)


def on_language_changed(listener: Callable[[str], None]) -> None:
    _listeners.append(listener)


def _walk_widgets(root: QWidget) -> list[QWidget]:
    return list(root.findChildren(QWidget))


def mark(widget: object, kind: str, payload: object) -> object:
    widget.__dict__.setdefault("_i18n_marks", []).append((kind, payload))
    return widget


def _apply_marks_of(widget: object, kinds: tuple[str, ...]) -> None:
    for kind, payload in getattr(widget, "_i18n_marks", ()):
        if kind not in kinds:
            continue
        if kind == "text":
            if isinstance(widget, (QPushButton, QLabel, QCheckBox)):
                widget.setText(tr(payload))
        elif kind == "tree":
            header = getattr(widget, "headerItem", None)
            if callable(header):
                for column, key in enumerate(payload):
                    header().setText(column, tr(key))
        elif kind == "pair":
            labels: list[QLabel] = getattr(widget, "findChildren", lambda _t: [])(QLabel)
            for index, key in enumerate(payload):
                if index < len(labels):
                    labels[index].setText(tr(key))
        elif kind == "list":
            widgets: list[QWidget] = getattr(widget, "findChildren", lambda _t: [])(QWidget)
            for index, key in enumerate(payload):
                if index >= len(widgets):
                    break
                setter = getattr(widgets[index], "setText", None)
                if callable(setter):
                    setter(tr(key))


def _apply_marked(widget: object) -> None:
    _apply_marks_of(widget, ("text", "tree", "pair", "list"))
    if isinstance(widget, QWidget) and any(kind == "scope" for kind, _ in getattr(widget, "_i18n_marks", ())):
        for child in _walk_widgets(widget):
            _apply_marks_of(child, ("text", "tree", "pair", "list"))


def _apply_key(widget: object) -> None:
    key = getattr(widget, "_i18n_key", None)
    if not key:
        return
    if isinstance(widget, (QPushButton, QLabel, QCheckBox)):
        widget.setText(tr(key))


def refresh(root: QWidget) -> None:
    for widget in [root, *_walk_widgets(root)]:
        _apply_key(widget)
        if getattr(widget, "_i18n_marks", None):
            _apply_marked(widget)


def mark_pair(root: object, path: str, keys: tuple[str, ...]) -> None:
    target = root
    for part in path.split("."):
        target = getattr(target, part)
    mark(target, "pair", keys)


def mark_list(root: object, path: str, keys: tuple[str, ...]) -> None:
    target = root
    for part in path.split("."):
        target = getattr(target, part)
    mark(target, "list", keys)


def mark_tree(root: object, path: str, keys: tuple[str, ...]) -> None:
    target = root
    for part in path.split("."):
        target = getattr(target, part)
    mark(target, "tree", keys)


def mark_widget(root: object, path: str, key: str) -> None:
    target = root
    for part in path.split("."):
        target = getattr(target, part)
    mark(target, "text", key)


def register_text(widget: object, key: str) -> None:
    mark(widget, "text", key)


def register_tree(tree: object, keys: tuple[str, ...]) -> None:
    mark(tree, "tree", keys)


def register_pair(frame: object, title_key: str, note_key: str) -> None:
    mark(frame, "pair", (title_key, note_key))


def retrans(root: QWidget) -> None:
    refresh(root)



def i18n_text(key: str) -> str:
    """Mark the nearest enclosing widget with *key* so retrans() can refresh it later."""
    frame = inspect.currentframe()
    caller = frame.f_back if frame is not None else None
    owner = getattr(caller, "f_locals", {}).get("self") if caller is not None else None
    if isinstance(owner, QWidget):
        owner.__dict__["_i18n_key"] = key
    return tr(key)


def i18n_live(key: str) -> str:
    """Translate without registering the widget (for runtime-refreshed texts)."""
    return tr(key)


def about_html() -> str:
    """Composed About page: both parts are legal content and stay language-invariant."""
    return _ABOUT_OURS + _ABOUT_ORIGINAL


def tr(key: str, fallback: str | None = None, **kwargs) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        return fallback if fallback is not None else key
    text = entry.get(current_language()) or entry.get("zh") or fallback or key
    return text.format(**kwargs) if kwargs else text
