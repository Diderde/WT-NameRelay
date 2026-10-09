# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""语音批量表格模型与行委托（W3）。

- 行身份 = ``row_id``（见 docs/voice-batch-spec.md §1）：编辑内容、重排都不改变身份；
- 模型的编辑面只覆盖**内容字段**（name / text / voice），状态列由双轴合成只读展示；
- 动作列由委托绘制"试听 / 重新生成"两枚按钮，点击以信号形式抛出（页面决定行为）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import IntEnum
from pathlib import Path

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QWidget,
)

from app.i18n import tr
from app.models.voice_table import UiRowState, VoiceRow, VoiceTable
from app.styles import theme


def _option_rect(option: object) -> QRect:
    """QStyleOptionViewItem.rect 的类型安全读取（PySide6 stub 未导出该属性）。"""

    rect = getattr(option, "rect", None)
    return rect if isinstance(rect, QRect) else QRect()


class VoiceColumn(IntEnum):
    STATUS = 0
    NAME = 1
    TEXT = 2
    PROCESS = 3  # 音频处理：进入处理按钮（该行音频送往音频处理页）
    SKIP = 4  # 不用生成：勾选后批量生成跳过该行
    IMPORT = 5  # 导入音频：自备音频替代 TTS 生成
    VOICE = 6
    DURATION = 7
    ACTIONS = 8


_COLUMN_TITLE_KEYS: dict[VoiceColumn, str] = {
    VoiceColumn.STATUS: "voice.col.status",
    VoiceColumn.NAME: "voice.col.name",
    VoiceColumn.TEXT: "voice.col.text",
    VoiceColumn.PROCESS: "voice.col.process",
    VoiceColumn.SKIP: "voice.col.skip",
    VoiceColumn.IMPORT: "voice.col.import",
    VoiceColumn.VOICE: "voice.col.voice",
    VoiceColumn.DURATION: "voice.col.duration",
    VoiceColumn.ACTIONS: "voice.col.actions",
}

#: 状态 → (文案键, 颜色)。颜色**随主题刷新**（见 _ensure_status_style）：
# 绘制与 tests.test_voice_batch 的渲染级像素回归都读本表的 [1]，
# 两边必须共用同一份值，否则像素对不上。
_STATUS_STYLE: dict[UiRowState, tuple[str, str]] = {
    UiRowState.PENDING: ("voice.status.pending", "#7A8794"),
    UiRowState.RUNNING: ("voice.status.running", "#D09A5B"),
    UiRowState.DONE: ("voice.status.done", "#65A77A"),
}

#: 状态 → 色板键（昼夜各一套，见 theme.PALETTES）
_STATUS_COLOUR_KEY: dict[UiRowState, str] = {
    UiRowState.PENDING: "state_pending",
    UiRowState.RUNNING: "state_running",
    UiRowState.DONE: "state_done",
}

_status_style_mode: str | None = None


def _ensure_status_style() -> None:
    """按当前主题刷新徽章色：绘制与像素回归共用 _STATUS_STYLE，故就地改值。

    懒刷新而非监听主题信号——委托的生命周期不受控（测试直接构造、页面
    销毁时序），按需比对模式可保证任何调用路径下颜色都是当前主题的。
    """

    global _status_style_mode
    mode = theme.current_mode()
    if _status_style_mode == mode:
        return
    for state, (text_key, _old) in _STATUS_STYLE.items():
        _STATUS_STYLE[state] = (text_key, theme.color(_STATUS_COLOUR_KEY[state]))
    _status_style_mode = mode

EDITABLE_FIELDS: dict[VoiceColumn, str] = {
    VoiceColumn.NAME: "name",
    VoiceColumn.TEXT: "text",
    VoiceColumn.VOICE: "voice",
}


def format_duration(duration_ms: int) -> str:
    """时长展示：<1s 用毫秒，否则用秒（保留 1 位小数）。"""

    if duration_ms <= 0:
        return "—"
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    return f"{duration_ms / 1000:.1f} s"


class VoiceTableModel(QAbstractTableModel):
    """可编辑表格模型：行身份=row_id，结构变化与内容编辑以信号通知页面。

    **命名规范模式**（表格规范化）：``spec_names`` 非空时表格被规范锁定——
    行集合与顺序恒等于规范名单、NAME 列只读、结构变更（add/duplicate/
    remove/move）一律拒绝；``apply_spec`` 按名字对账继承旧表内容，
    ``clear_spec`` 解锁并清空。
    """

    rows_changed = Signal()
    row_edited = Signal(str)

    def __init__(self, table: VoiceTable | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._table = table if table is not None else VoiceTable()
        self._spec_names: tuple[str, ...] | None = None

    # —— Qt 模型接口 ——
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._table.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(VoiceColumn)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object | None:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            column = VoiceColumn(section)
            return tr(_COLUMN_TITLE_KEYS[column])
        return section + 1

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object | None:
        if not index.isValid():
            return None
        row = self._table.rows[index.row()]
        column = VoiceColumn(index.column())
        if role == Qt.ItemDataRole.ToolTipRole:
            if column is VoiceColumn.STATUS:
                return self.status_tooltip(row)
            if column is VoiceColumn.NAME:
                # 官方名普遍 30~50 字符，列宽不够时悬停看全名
                return row.name
            if column is VoiceColumn.IMPORT and row.imported_audio:
                return row.imported_audio
            return None
        if column is VoiceColumn.SKIP and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if row.skip_generation else Qt.CheckState.Unchecked
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return None
        if column is VoiceColumn.STATUS:
            text = tr(_STATUS_STYLE[row.ui_state()][0])
            if row.needs_regeneration:
                text = f"{text} · {tr('voice.status.regenerate')}"
            return text
        if column is VoiceColumn.NAME:
            return row.name
        if column is VoiceColumn.TEXT:
            return row.text
        if column is VoiceColumn.IMPORT:
            return Path(row.imported_audio).name if row.imported_audio else ""
        if column is VoiceColumn.VOICE:
            return row.voice
        if column is VoiceColumn.DURATION:
            return format_duration(row.duration_ms)
        return ""

    def setData(self, index: QModelIndex | QPersistentModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid():
            return False
        row = self._table.rows[index.row()]
        if role == Qt.ItemDataRole.CheckStateRole and VoiceColumn(index.column()) is VoiceColumn.SKIP:
            checked = Qt.CheckState(value) is Qt.CheckState.Checked
            if row.skip_generation == checked:
                return False
            row.skip_generation = checked
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            self.row_edited.emit(row.row_id)
            return True
        if role != Qt.ItemDataRole.EditRole:
            return False
        field_name = EDITABLE_FIELDS.get(VoiceColumn(index.column()))
        if field_name is None:
            return False
        if field_name == "name" and self._spec_names is not None:
            return False  # 规范锁定：NAME 列只读（双闸之一，flags 之外的兜底）
        text = str(value)
        if getattr(row, field_name) == text:
            return False
        setattr(row, field_name, text)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.row_edited.emit(row.row_id)
        return True

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if VoiceColumn(index.column()) in EDITABLE_FIELDS:
            if VoiceColumn(index.column()) is VoiceColumn.NAME and self._spec_names is not None:
                return base  # 规范锁定：NAME 列只读
            return base | Qt.ItemFlag.ItemIsEditable
        if VoiceColumn(index.column()) is VoiceColumn.SKIP:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    # —— 命名规范模式 ——
    @property
    def spec_names(self) -> tuple[str, ...] | None:
        """当前规范名单（未加载规范时 None）。"""

        return self._spec_names

    def apply_spec(self, names: Sequence[str], carry: VoiceTable | None = None) -> int:
        """应用命名规范：按名单重建整表并锁定；返回对账继承的行数。

        ``carry`` 为旧表（如有）：同名（大小写不敏感）行继承内容
        （text/voice）、会话级字段（imported_audio/skip_generation）与
        生成状态（job/artifact/双 hash/audio_path/duration_ms/error——
        text 未变则 spec_hash 仍有效，与打开 `.vt` 应用旁车状态同性质），
        多余行丢弃、缺失行新建（row_id 全新）。结构变化以整表重置通知
        视图。
        """

        if not names:
            raise ValueError("规范名单为空")
        carry_map = {}
        if carry is not None:
            for row in carry.rows:
                carry_map.setdefault(row.name.casefold(), row)
        table = VoiceTable(id_factory=self._table.id_factory)
        kept = 0
        for name in names:
            row = table.add_row(name=name)
            old = carry_map.get(name.casefold())
            if old is not None:
                row.row_id = old.row_id  # 同名行身份不变（.vt 往返/旁车状态依赖它）
                row.text = old.text
                row.voice = old.voice
                row.extra = dict(old.extra)
                row.imported_audio = old.imported_audio
                row.skip_generation = old.skip_generation
                row.job = old.job
                row.artifact = old.artifact
                row.spec_hash = old.spec_hash
                row.output_hash = old.output_hash
                row.audio_path = old.audio_path
                row.duration_ms = old.duration_ms
                row.error_code = old.error_code
                row.error_message = old.error_message
                kept += 1
        self.beginResetModel()
        self._table = table
        self._spec_names = tuple(names)
        self.endResetModel()
        self.rows_changed.emit()
        return kept

    def clear_spec(self) -> None:
        """解除规范锁定并清空表格（测试与换流程用）。"""

        self.beginResetModel()
        self._table = VoiceTable(id_factory=self._table.id_factory)
        self._spec_names = None
        self.endResetModel()
        self.rows_changed.emit()

    # —— 业务接口 ——
    def table(self) -> VoiceTable:
        return self._table

    def set_table(self, table: VoiceTable) -> None:
        self.beginResetModel()
        self._table = table
        self.endResetModel()
        self.rows_changed.emit()

    def rows(self) -> tuple[VoiceRow, ...]:
        return tuple(self._table.rows)

    def row_at(self, row_index: int) -> VoiceRow | None:
        if 0 <= row_index < len(self._table.rows):
            return self._table.rows[row_index]
        return None

    def row_id_at(self, row_index: int) -> str:
        row = self.row_at(row_index)
        return row.row_id if row is not None else ""

    def index_of(self, row_id: str) -> int:
        return self._table.index_of(row_id)

    def _emit_row_inserted(self, position: int) -> None:
        self.beginInsertRows(QModelIndex(), position, position)
        self.endInsertRows()
        self.rows_changed.emit()

    def add_row(self, *, name: str = "", text: str = "", voice: str = "") -> VoiceRow:
        if self._spec_names is not None:
            raise RuntimeError("命名规范已锁定：行集合由规范名单决定，不能添加行")
        position = len(self._table.rows)
        self.beginInsertRows(QModelIndex(), position, position)
        row = self._table.add_row(name=name, text=text, voice=voice)
        self.endInsertRows()
        self.rows_changed.emit()
        return row

    def duplicate_row(self, row_id: str) -> VoiceRow | None:
        if self._spec_names is not None:
            raise RuntimeError("命名规范已锁定：不能复制行")
        position = self.index_of(row_id)
        if position < 0:
            return None
        self.beginInsertRows(QModelIndex(), position + 1, position + 1)
        clone = self._table.duplicate_row(row_id)
        self.endInsertRows()
        if clone is not None:
            self.rows_changed.emit()
        return clone

    def remove_row(self, row_id: str) -> bool:
        if self._spec_names is not None:
            raise RuntimeError("命名规范已锁定：行集合由规范名单决定，不能删除行")
        position = self.index_of(row_id)
        if position < 0:
            return False
        self.beginRemoveRows(QModelIndex(), position, position)
        removed = self._table.remove_row(row_id)
        self.endRemoveRows()
        if removed:
            self.rows_changed.emit()
        return removed

    def move_row(self, row_id: str, target_index: int) -> bool:
        if self._spec_names is not None:
            raise RuntimeError("命名规范已锁定：行顺序由规范名单决定，不能移动行")
        source = self.index_of(row_id)
        if source < 0 or source == target_index:
            return False
        moved = self._table.move_row(row_id, target_index)
        if not moved:
            return False
        self.layoutChanged.emit()
        self.rows_changed.emit()
        return True

    def refresh_row(self, row_id: str) -> None:
        """状态/时长等非内容字段变化后刷新该行显示。"""

        position = self.index_of(row_id)
        if position < 0:
            return
        left = self.index(position, int(VoiceColumn.STATUS))
        right = self.index(position, int(VoiceColumn.DURATION))
        self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole])

    def status_tooltip(self, row: VoiceRow) -> str:
        parts = [tr(_STATUS_STYLE[row.ui_state()][0])]
        if row.skip_generation:
            parts.append(tr("voice.col.skip"))
        if row.needs_regeneration:
            parts.append(tr("voice.tip.stale"))
        if row.error_message:
            parts.append(row.error_message)
        return " · ".join(parts)


def default_audio_picker(parent: QWidget) -> str:
    """参考音频的文件选择对话框（模块级函数，测试可整体注入替换）。

    强制 Qt 非原生对话框：2026-10-02 实机崩溃（logs/video_clip_crash.log
    Windows fatal exception 0xc0000374 堆损坏，栈顶即本函数）定位为原生
    文件对话框与 Shell 扩展/COM 的原生层 bug——与 Python 代码无关，
    界内无法防御，只能绕开原生对话框。"""

    path, _filter = QFileDialog.getOpenFileName(
        parent, tr("voice.voice.browse"), "", tr("voice.voice.filter"),
        options=QFileDialog.Option.DontUseNativeDialog)
    return path


class VoicePathEditor(QWidget):
    """「参考音频」列（原"音色"列）的编辑器：路径文本框 + 「…」选择按钮（GSV 与 CosyVoice 共用）。

    用容器而不是 QLineEdit 本身当编辑器：模态文件对话框会把焦点从行编辑器夺走，
    QLineEdit 的 ``editingFinished`` 会因此立刻触发，被视图当成"提交并关闭编辑器"。
    容器编辑器没有这个自动提交接线，提交时机完全由本类与委托控制。
    """

    #: 路径经「…」选定 → 委托据此立即 commitData（手动输入则在编辑器关闭时提交）
    path_changed = Signal()

    def __init__(self, parent: QWidget | None = None, picker: Callable[[QWidget], str] | None = None) -> None:
        super().__init__(parent)
        self._picker = picker or default_audio_picker
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.path_input = QLineEdit(self)
        self.browse_button = QToolButton(self)
        self.browse_button.setText("…")
        self.browse_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 点它不许从行编辑器夺走焦点
        self.browse_button.setToolTip(tr("voice.voice.browse"))
        self.browse_button.clicked.connect(self._browse)
        layout.addWidget(self.path_input, 1)
        layout.addWidget(self.browse_button)

    def path(self) -> str:
        return self.path_input.text()

    def set_path(self, value: str) -> None:
        self.path_input.setText(value)

    def _browse(self) -> None:
        # 模态对话框必须退出当前点击事件栈后再开：在编辑器按钮的槽里
        # 同步开模态框是重入隐患（配合原生对话框即上面登记的堆损坏）
        QTimer.singleShot(0, self._run_picker)

    def _run_picker(self) -> None:
        if not self._picker:  # 编辑器已提交关闭的兜底
            return
        chosen = self._picker(self)
        if chosen:
            self.set_path(chosen)
            self.path_changed.emit()


class VoiceRowDelegate(QStyledItemDelegate):
    """行委托：状态列画徽章，动作列画两枚按钮（点击抛信号），参考音频列用带「…」的编辑器。"""

    preview_requested = Signal(str)
    regenerate_requested = Signal(str)
    import_requested = Signal(str)
    process_requested = Signal(str)

    ACTION_GAP = 6
    ACTION_MIN_WIDTH = 58
    #: 状态徽章色块在字形墨迹上下的留白（单侧，逻辑像素）
    BADGE_PAD_Y = 3

    def __init__(self, parent: QObject | None = None, *, audio_picker: Callable[[QWidget], str] | None = None) -> None:
        super().__init__(parent)
        self._audio_picker = audio_picker or default_audio_picker

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QWidget:
        if VoiceColumn(QModelIndex(index).column()) is VoiceColumn.VOICE:
            editor = VoicePathEditor(parent, picker=self._audio_picker)
            editor.path_changed.connect(lambda editor=editor: self.commitData.emit(editor))
            return editor
        return super().createEditor(parent, option, index)  # type: ignore[return-value]

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:
        if isinstance(editor, VoicePathEditor):
            editor.set_path(str(index.data(Qt.ItemDataRole.EditRole) or ""))
            return
        super().setEditorData(editor, index)

    def setModelData(
        self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        if isinstance(editor, VoicePathEditor):
            model.setData(index, editor.path(), Qt.ItemDataRole.EditRole)
            return
        super().setModelData(editor, model, index)

    def action_rects(self, cell: QRect) -> tuple[QRect, QRect]:
        """把单元格切成"试听 / 重新生成"两枚按钮的矩形（供绘制与点击共用）。"""

        margin = 4
        available = max(0, cell.width() - margin * 2 - self.ACTION_GAP)
        width = max(1, available // 2)
        height = max(20, cell.height() - 10)
        top = cell.top() + (cell.height() - height) // 2
        left = QRect(cell.left() + margin, top, width, height)
        right = QRect(left.right() + self.ACTION_GAP + 1, top, width, height)
        return left, right

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        column = VoiceColumn(index.column())
        if option.state & QStyle.StateFlag.State_Selected:
            # 视图先用调色板 Highlight 铺整行选中底（Qt6
            # PE_PanelItemViewRow），品牌亮蓝落在按深底取色的自绘按钮上，
            # 文字对比度掉到 ~1.1:1（2026-10-04 用户反馈）。委托自铺
            # selection_bg 并摘掉 Selected 态：正文列以常规字色落在深底上，
            # 自绘按钮回到与未选中行一致的可读区间。不走视图级调色板覆盖：
            # 应用级 QSS 存在时它会在构造期 polish 被吞，时机不可控。
            painter.fillRect(_option_rect(option), QColor(theme.color("selection_bg")))
            option.state &= ~QStyle.StateFlag.State_Selected
        if column is VoiceColumn.STATUS:
            self._paint_badge(painter, option, index, str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
            return
        if column is VoiceColumn.ACTIONS:
            self._paint_actions(painter, option)
            return
        if column is VoiceColumn.SKIP:
            self._paint_skip_cell(painter, option, index)
            return
        if column is VoiceColumn.PROCESS:
            self._paint_cell_button(painter, option, tr("voice.process.enter"), accent=False)
            return
        if column is VoiceColumn.IMPORT:
            label = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            self._paint_cell_button(
                painter, option, label or tr("voice.import.pick"), accent=True)
            return
        super().paint(painter, option, index)

    @staticmethod
    def cell_button_rect(cell: QRect) -> QRect:
        """PROCESS/IMPORT 单按钮占格矩形（与点击命中测试共用）。"""
        return cell.adjusted(6, 6, -6, -6)

    def _paint_cell_button(self, painter: QPainter, option: QStyleOptionViewItem,
                           label: str, *, accent: bool, filled: bool = False) -> None:
        """单按钮单元格（进行处理 / 导入音频 / 禁止生成）：与动作列同款描边风格。"""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.cell_button_rect(_option_rect(option))
        colour = QColor(theme.color("row_action_accent") if accent else theme.color("row_action"))
        if filled:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.setOpacity(0.18)
            painter.drawRoundedRect(rect, 6, 6)
            painter.setOpacity(1.0)
        painter.setPen(QPen(colour))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 6, 6)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _paint_skip_cell(self, painter: QPainter, option: QStyleOptionViewItem,
                         index: QModelIndex | QPersistentModelIndex) -> None:
        """禁止单元格画成整格状态按钮：默认复选框热区只有小方块，且自定义
        editorEvent 从未调 super()——点击毫无反应、状态无从辨认；文字状态
        让所见即所选。"""
        checked = index.data(Qt.ItemDataRole.CheckStateRole) is Qt.CheckState.Checked
        label = tr("voice.skip.forbidden") if checked else tr("voice.skip.forbid")
        self._paint_cell_button(painter, option, label, accent=checked, filled=checked)

    def _paint_badge(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex, text: str
    ) -> None:
        model = index.model()
        item = model.row_at(index.row()) if model is not None and hasattr(model, "row_at") else None
        _ensure_status_style()  # 绘制前对齐当前主题，保证与 _STATUS_STYLE 同值
        colour = _STATUS_STYLE[item.ui_state()][1] if item is not None else theme.color("state_pending")
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cell = _option_rect(option)
        # 色块必须按"字形墨迹"取高，不能按字体排版盒：
        # boundingRect 给的是 ascent+descent 的排版盒，CJK 字形只占中间一段
        # ——实测 Microsoft YaHei UI 14px：盒 18px、墨迹仅 12px，按盒取高
        # 做出 26px 的色块（2.17 倍字高），字上下各空 7px，看着就是"色块
        # 没盖住字"（2026-10-04 用户反馈）。改由 tightBoundingRect 取真实
        # 墨迹高（实测多数字号比真实墨迹偏大 1~2px，个别字号偏小 1px，
        # 由 BADGE_PAD_Y 留白兜住：多缩放 × 12~24px 字号实测余量均 >= 2px），
        # 色块以墨迹中心为心、上下留白对称。
        metrics = painter.fontMetrics()
        tight = metrics.tightBoundingRect(text)
        box = metrics.boundingRect(cell, Qt.AlignmentFlag.AlignCenter, text)
        # 墨迹中心：tightBoundingRect 以基线为原点（实测 24px 雅黑 top=-20 /
        # bottom=3，即墨迹从基线上 20 到下 4）。基线 = 排版盒顶 + ascent，
        # 盒心不等于墨迹中心（实测墨迹比盒心低 1~2px，色块按盒心摆会偏上）。
        baseline = box.top() + metrics.ascent()
        ink_centre = baseline + (tight.top() + tight.bottom() + 1) / 2
        pill_height = min(cell.height() - 4, tight.height() + 2 * self.BADGE_PAD_Y)
        pill_top = round(ink_centre - pill_height / 2)
        # 兜底：格高不足时色块宁可贴边也不许让字从色块里冒出去
        pill_top = max(cell.top() + 1, min(pill_top, cell.bottom() - pill_height))
        badge = QRect(cell.left() + 6, pill_top, cell.width() - 12, pill_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        painter.setOpacity(0.22)
        painter.drawRoundedRect(badge, badge.height() / 2, badge.height() / 2)
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(colour)))
        painter.drawText(cell, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _paint_actions(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for rect, label, accent in (
            (self.action_rects(_option_rect(option))[0], tr("voice.action.preview"), False),
            (self.action_rects(_option_rect(option))[1], tr("voice.action.regenerate"), True),
        ):
            colour = QColor(theme.color("row_action_accent") if accent else theme.color("row_action"))
            painter.setPen(QPen(colour))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        column = VoiceColumn(QModelIndex(index).column())
        if column not in (VoiceColumn.ACTIONS, VoiceColumn.PROCESS, VoiceColumn.IMPORT, VoiceColumn.SKIP):
            return False
        position = event.position().toPoint()  # type: ignore[attr-defined]
        if hasattr(model, "row_id_at"):
            row_id = model.row_id_at(QModelIndex(index).row())  # type: ignore[attr-defined]
        else:
            row_id = ""
        if not row_id:
            return False
        if column is VoiceColumn.ACTIONS:
            preview_rect, regenerate_rect = self.action_rects(_option_rect(option))
            if preview_rect.contains(position):
                self.preview_requested.emit(row_id)
                return True
            if regenerate_rect.contains(position):
                self.regenerate_requested.emit(row_id)
                return True
            return False
        if self.cell_button_rect(_option_rect(option)).contains(position):
            if column is VoiceColumn.SKIP:
                # 自定义 editorEvent 从未调 super()，默认复选框
                # 切换被遮蔽——点勾选框毫无反应；改为整格点击切换
                checked = index.data(Qt.ItemDataRole.CheckStateRole) is Qt.CheckState.Checked
                model.setData(
                    index,
                    Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked,
                    Qt.ItemDataRole.CheckStateRole)
                return True
            if column is VoiceColumn.PROCESS:
                self.process_requested.emit(row_id)
            else:
                self.import_requested.emit(row_id)
            return True
        return False