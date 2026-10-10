# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TTS 命名规范模式：规范名单文件的解析与校验（GSV 之外的表格规范化）。

规范文件为 UTF-8（容 BOM）纯文本，**路径分节**（v3）：

- 节头 = ``#region <类别>[/<次类>[/<弎类>]]``——斜杠分隔的路径，段数 2~4
  （类别 + 1~3 个子层），按官方文件夹结构书写、深度自适应：
  ``tank/UK/high/gunner``（语言→情绪→职位）、``vws/betty``（语音组→文件）、
  ``wopl/EN``（语言→文件）、``ship/FR/commander/high``（语言→成员→情绪）、
  ``radio/eng/voice1``（语言→组）；
- 类别键固定五个（:data:`SPEC_CATEGORIES`）：``tank`` / ``vws`` / ``ship`` /
  ``wopl`` / ``radio``；其余路径段为自由文本（按钮/分组头原样展示）；
- 节尾 = ``#endregion``（**可省略**：下一个节头隐式结束上一节，文件结束
  隐式结束）；无开启节时的多余 ``#endregion`` 宽容忽略；
- ``#`` 开头的其它注释行与空行照旧忽略；每节内每行一个音频名，
  行序即表序。

校验是**全有或全无**：结构错误（名单行在分节外 / 未知类别 / 路径深度
不合法 / 路径重复 / 缺类别 / 类别下无任何名单）与名字错误（不合法、
**同路径内**大小写不敏感重名）任一出现即整份拒绝，返回逐条错误（带
行号），调用方不落地半份规范。名字用与生成期同一把尺（
VoiceFilenameValidator, WT_DEFAULT）校验，且必须**已是规范形式**。

重名规则（v3 变更）：同一文件名允许出现在**不同路径**下（如 tank/UK/high
与 tank/UK/med 各列一份，或同台词不同情绪各自生成）；同一**路径**内仍然
唯一。表格按当前选中路径展示名单，路径即生成任务的边界。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.services.voice_filename_validator import VoiceFilenameValidator

#: 五个固定类别键（顺序 = UI 显示顺序）；键精确小写匹配。
SPEC_CATEGORIES: tuple[str, ...] = ("tank", "vws", "ship", "wopl", "radio")

#: 节头标记：``#region`` + 空格 + 路径。
REGION_PREFIX = "#region"
#: 节尾标记（可省略）。
ENDREGION_MARKER = "#endregion"
#: 路径段数范围：类别 + 1~3 个子层。
MIN_PATH_DEPTH = 2
MAX_PATH_DEPTH = 4

#: 各类别情绪层的固定取值（按钮文案来源；radio 的情绪在文件名 mood_* 段内）。
EMOTION_VALUES: dict[str, tuple[str, ...]] = {
    "tank": ("high", "med"),
    "ship": ("high", "low", "med"),
}

#: 各类别的子层级语义（按官方文件夹结构，深度自适应）：
#: countries = 国家/语言；emotions = 情绪（high/med…）；members = 成员
#: （职位 gunner…、指挥 chain、电台分组 voiceN）；groups = vws 语音组。
SUBLEVEL_SCHEMA: dict[str, tuple[str, ...]] = {
    "tank": ("countries", "emotions", "members"),
    "ship": ("countries", "members", "emotions"),
    "radio": ("countries", "members"),
    "wopl": ("countries",),
    "vws": ("groups",),
}

#: 成员层（kind = "members"）的内置取值（未加载 txt 时的按钮预览；
#: 官方目录名原文，取全部语言目录的并集——如 chief_f 仅存在于
#: german_new 德语目录）。注意：预览是并集，个别成员在某国家下可能
#: 没有对应资源（以 txt 名单为准）。
CATEGORY_MEMBERS: dict[str, tuple[str, ...]] = {
    "tank": (
        "artillery", "aviation", "chief_f", "chief_m", "commander",
        "driver", "gunner", "loader",
    ),
    "ship": ("commander", "officer", "sailor"),
    "radio": ("common", "voice1", "voice2", "voice3"),
}

#: 未加载规范时的国家/语音组预览（内置；加载 txt 后以 txt 路径段为准）。
CATEGORY_COUNTRIES: dict[str, tuple[str, ...]] = {
    "tank": ("UK", "US", "GE", "RU"),
    "vws": ("betty", "rita", "xiao906"),
    "ship": ("EN", "EN-US", "FR", "DE", "IT", "JP", "RU"),
    "wopl": ("EN", "DE", "RU"),
    "radio": ("EN", "RU"),
}

_CATEGORY_HINT = " / ".join(SPEC_CATEGORIES)


class SpecError(ValueError):
    """规范文件不可用（解析失败或校验未过）；message 面向用户直接展示。"""


@dataclass(frozen=True, slots=True)
class SpecEntry:
    """一条规范：行号（文件内 1 起含注释行计数）+ 音频名。"""

    line_number: int
    name: str


@dataclass(frozen=True, slots=True)
class SpecDocument:
    """按路径组织的有序规范（v3）。

    ``categories`` = 文件内出现的类别序；``paths`` = 完整路径串
    （``"tank/UK/high/gunner"``）→ 该节条目（文件内行序）；``header_lines``
    = 各路径节头出现过的全部行号（首行给"空节"引用，重复行给"路径重复"）。
    解析只做结构归集，校验统一在 :func:`validate_spec_entries`。
    """

    categories: tuple[str, ...]
    paths: Mapping[str, tuple[SpecEntry, ...]]
    header_lines: Mapping[str, tuple[int, ...]]

    def entries_for(self, path: str) -> tuple[SpecEntry, ...]:
        """取某路径的条目（路径不存在时返回空元组）。"""

        return tuple(self.paths.get(path, ()))

    def names(self, path: str) -> tuple[str, ...]:
        """取某路径的名单（音频名序列，顺序即表序）。"""

        return tuple(entry.name for entry in self.entries_for(path))

    def items_in_file_order(self) -> tuple[tuple[str, SpecEntry], ...]:
        """按文件内节序摊平全部条目：``(路径串, 条目)`` 序列。"""

        return tuple(
            (path, entry) for path, entries in self.paths.items() for entry in entries
        )

    def sub_options(self, prefix: tuple[str, ...]) -> tuple[str, ...]:
        """给定路径前缀，返回下一层的去重选项（文件内首次出现序）。

        例：``sub_options(("tank",))`` → 全部国家段；``sub_options(("tank",
        "UK"))`` → 该国全部情绪段。前缀长度已达 :data:`MAX_PATH_DEPTH` 时
        返回空元组。
        """

        if len(prefix) >= MAX_PATH_DEPTH:
            return ()
        seen: list[str] = []
        for path in self.paths:
            segments = tuple(path.split("/"))
            if len(segments) <= len(prefix) or segments[: len(prefix)] != prefix:
                continue
            option = segments[len(prefix)]
            if option not in seen:
                seen.append(option)
        return tuple(seen)

    def path_header_line(self, path: str) -> int:
        """某路径节头首次出现的行号（0 = 该路径不存在）。"""

        lines = self.header_lines.get(path, ())
        return lines[0] if lines else 0

    def repeat_lines(self, path: str) -> tuple[int, ...]:
        """某路径重复节头的行号（不含首次；无重复返回空元组）。"""

        return tuple(self.header_lines.get(path, ()))[1:]


def _region_key(line: str) -> tuple[bool, str]:
    """节头行 → ``(True, 路径串)``；非节头行 → ``(False, "")``。

    ``#region <路径>`` 按**首空格**切分（比 ``split()`` 宽容：``#region
    tank/UK`` 多余空格不会误判）；路径原样返回，合法性交由校验层。
    """

    parts = line.split(" ", 1)
    if parts[0] != REGION_PREFIX:
        return False, ""
    return True, (parts[1].strip() if len(parts) > 1 else "")


def parse_spec_file(path: Path) -> SpecDocument:
    """读规范文件为按路径组织的文档；不可读/非 UTF-8 抛 SpecError。

    结构归集阶段只把"名单行出现在任何 #region 之前"判为致命（旧版无节头
    文件即落此错误）；其余（未知类别 / 深度不合法 / 路径重复 / 缺类别 /
    空节）留给 :func:`validate_spec_entries` 全量判定。
    """

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise SpecError(f"无法读取规范文件：{error}") from error
    except UnicodeDecodeError as error:
        raise SpecError(f"规范文件不是 UTF-8 编码：{error}") from error

    sections: dict[str, list[SpecEntry]] = {}
    header_lines: dict[str, list[int]] = {}
    current: str | None = None
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            is_region, key = _region_key(line)
            if is_region:
                # 重复节头：条目仍归集到同一路径（重复由校验层按行号报错）；
                # 裸 #region（无路径）不静默吞掉，路径为空串 → 校验层报出
                if key not in sections:
                    sections[key] = []
                header_lines.setdefault(key, []).append(line_number)
                current = key
                continue
            if line == ENDREGION_MARKER:
                # 结束当前节；无开启节的多余 #endregion 宽容忽略
                current = None
            continue
        if current is None:
            raise SpecError(
                f"第 {line_number} 行「{line}」：名单行出现在任何 #region 之前"
                f"（本版本要求路径分节格式：#region {_CATEGORY_HINT}/…）"
            )
        sections[current].append(SpecEntry(line_number=line_number, name=line))
    if not sections:
        raise SpecError(
            "规范文件为空（没有 #region 分节；本版本要求路径分节格式："
            f"#region {_CATEGORY_HINT}/…）"
        )
    return SpecDocument(
        categories=tuple(
            dict.fromkeys(path.split("/")[0] for path in sections)
        ),
        paths={key: tuple(value) for key, value in sections.items()},
        header_lines={key: tuple(value) for key, value in header_lines.items()},
    )


def validate_spec_entries(document: SpecDocument, validator: VoiceFilenameValidator) -> list[str]:
    """逐条校验文档结构与名字；全部合法返回空列表，否则返回带行号的可读错误列表。

    结构与名字**一起**全量检查（调用方一次拿到全部问题）：

    1. 类别键未知（第一段不在 :data:`SPEC_CATEGORIES`，拼错不静默纠错）；
    2. 同一路径重复出现；
    3. 路径深度不合法（须为类别 + 1~3 个子层，即 2~4 段）；
    4. 五类缺任何一类、或该类下没有任何名单（跨该类全部路径合计）；
    5. 名单行本身不合法（WT_DEFAULT 同尺 + 必须已是规范形式）；
    6. 重名查重为**同路径内**大小写不敏感（不同路径允许同名——同台词的
       不同情绪录音本就同名；表格按当前路径展示，路径即生成任务边界）。
    """

    errors: list[str] = []
    category_totals: dict[str, int] = {}
    for path in document.paths:
        segments = path.split("/") if path else []
        line_number = document.path_header_line(path)
        if not segments:
            # 裸 #region（无路径）被 parse 层有意保留为空串路径
            # （见 parse_spec_file 注释），这里必须报可读错误——曾直接
            # segments[0] IndexError 崩溃（复核实验实测）。
            errors.append(
                f"第 {line_number} 行：裸 #region（缺路径；格式：#region {_CATEGORY_HINT}/<子层>…）"
            )
            continue
        category = segments[0]
        if category not in SPEC_CATEGORIES:
            if not document.repeat_lines(path):
                errors.append(
                    f"第 {line_number} 行：未知类别「{category}」"
                    f"（只能是 {_CATEGORY_HINT} 之一，须精确小写）"
                )
            continue
        if document.repeat_lines(path):
            for repeat_line in document.repeat_lines(path):
                errors.append(f"第 {repeat_line} 行：路径「{path}」重复出现（每条路径最多一节）")
            continue
        if not document.entries_for(path):
            errors.append(f"第 {line_number} 行：路径「{path}」为空节（至少一个音频名）")
            continue
        if len(segments) < MIN_PATH_DEPTH or len(segments) > MAX_PATH_DEPTH:
            errors.append(
                f"第 {line_number} 行：路径「{path}」深度不合法"
                f"（{MIN_PATH_DEPTH}~{MAX_PATH_DEPTH} 段：类别 + 1~3 个子层）"
            )
            continue
        category_totals[category] = category_totals.get(category, 0) + len(
            document.entries_for(path)
        )
    for category in SPEC_CATEGORIES:
        if category_totals.get(category, 0) <= 0:
            errors.append(f"缺少「{category}」类的名单（五类每类至少一个音频名）")

    for path, entries in document.paths.items():
        segments = path.split("/") if path else []
        if not segments or segments[0] not in SPEC_CATEGORIES:
            continue
        if len(segments) < MIN_PATH_DEPTH or len(segments) > MAX_PATH_DEPTH:
            continue
        seen: dict[str, tuple[str, int]] = {}
        for entry in entries:
            canonical = entry.name.strip()
            if canonical != validator.normalize(canonical):
                errors.append(
                    f"第 {entry.line_number} 行「{entry.name}」不是规范形式"
                    f"（应为 {validator.normalize(canonical)}）"
                )
                continue
            key = canonical.casefold()
            first = seen.get(key)
            if first is not None:
                errors.append(
                    f"第 {entry.line_number} 行「{entry.name}」与第 {first[1]} 行"
                    f"「{first[0]}」在同一路径内重名（大小写不敏感）"
                )
                continue
            result = validator.validate(
                entry.name, existing=tuple(name for name, _line in seen.values())
            )
            if not result.ok:
                errors.append(
                    f"第 {entry.line_number} 行「{entry.name}」：{result.reason_code}"
                )
                continue
            seen[key] = (entry.name, entry.line_number)
    return errors
