# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""语音批量表格模型与行委托（W3）。

- 行身份 = ``row_id``（见 docs/voice-batch-spec.md §1）：编辑内容、重排都不改变身份；
- 模型的编辑面只覆盖**内容字段**（name / text / voice），状态列由双轴合成只读展示；
- 动作列由委托绘制"试听 / 重新生成"两枚按钮，点击以信号形式抛出（页面决定行为）。
"""

from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from app.i18n import tr
from app.models.voice_table import UiRowState, VoiceRow, VoiceTable


def _option_rect(option: object) -> QRect:
    """QStyleOptionViewItem.rect 的类型安全读取（PySide6 stub 未导出该属性）。"""

    rect = getattr(option, "rect", None)
    return rect if isinstance(rect, QRect) else QRect()


class VoiceColumn(IntEnum):
    STATUS = 0
    NAME = 1
    TEXT = 2
    VOICE = 3
    DURATION = 4
    ACTIONS = 5


_COLUMN_TITLE_KEYS: dict[VoiceColumn, str] = {
    VoiceColumn.STATUS: "voice.col.status",
    VoiceColumn.NAME: "voice.col.name",
    VoiceColumn.TEXT: "voice.col.text",
    VoiceColumn.VOICE: "voice.col.voice",
    VoiceColumn.DURATION: "voice.col.duration",
    VoiceColumn.ACTIONS: "voice.col.actions",
}

_STATUS_STYLE: dict[UiRowState, tuple[str, str]] = {
    UiRowState.PENDING: ("voice.status.pending", "#7A8794"),
    UiRowState.RUNNING: ("voice.status.running", "#D09A5B"),
    UiRowState.DONE: ("voice.status.done", "#65A77A"),
}

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
    """可编辑表格模型：行身份=row_id，结构变化与内容编辑以信号通知页面。"""

    rows_changed = Signal()
    row_edited = Signal(str)

    def __init__(self, table: VoiceTable | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._table = table if table is not None else VoiceTable()

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
            return None
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
        if column is VoiceColumn.VOICE:
            return row.voice
        if column is VoiceColumn.DURATION:
            return format_duration(row.duration_ms)
        return ""

    def setData(self, index: QModelIndex | QPersistentModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        field_name = EDITABLE_FIELDS.get(VoiceColumn(index.column()))
        if field_name is None:
            return False
        row = self._table.rows[index.row()]
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
            return base | Qt.ItemFlag.ItemIsEditable
        return base

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
        position = len(self._table.rows)
        self.beginInsertRows(QModelIndex(), position, position)
        row = self._table.add_row(name=name, text=text, voice=voice)
        self.endInsertRows()
        self.rows_changed.emit()
        return row

    def duplicate_row(self, row_id: str) -> VoiceRow | None:
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
        if row.needs_regeneration:
            parts.append(tr("voice.tip.stale"))
        if row.error_message:
            parts.append(row.error_message)
        return " · ".join(parts)


class VoiceRowDelegate(QStyledItemDelegate):
    """行委托：状态列画徽章，动作列画两枚按钮（点击抛信号）。"""

    preview_requested = Signal(str)
    regenerate_requested = Signal(str)

    ACTION_GAP = 6
    ACTION_MIN_WIDTH = 58

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
        if column is VoiceColumn.STATUS:
            self._paint_badge(painter, option, index, str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
            return
        if column is VoiceColumn.ACTIONS:
            self._paint_actions(painter, option)
            return
        super().paint(painter, option, index)

    def _paint_badge(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex, text: str
    ) -> None:
        model = index.model()
        item = model.row_at(index.row()) if model is not None and hasattr(model, "row_at") else None
        colour = _STATUS_STYLE[item.ui_state()][1] if item is not None else "#7A8794"
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        badge = _option_rect(option).adjusted(6, 6, -6, -6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        painter.setOpacity(0.22)
        painter.drawRoundedRect(badge, badge.height() / 2, badge.height() / 2)
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(colour)))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _paint_actions(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for rect, label, accent in (
            (self.action_rects(_option_rect(option))[0], tr("voice.action.preview"), False),
            (self.action_rects(_option_rect(option))[1], tr("voice.action.regenerate"), True),
        ):
            colour = QColor("#D09A5B") if accent else QColor("#8A96A2")
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
        if event.type() != QEvent.Type.MouseButtonRelease or VoiceColumn(QModelIndex(index).column()) is not VoiceColumn.ACTIONS:
            return False
        position = event.position().toPoint()  # type: ignore[attr-defined]
        preview_rect, regenerate_rect = self.action_rects(_option_rect(option))
        cell_index = QModelIndex(index)
        row_id = ""
        if hasattr(model, "row_id_at"):
            row_id = model.row_id_at(cell_index.row())  # type: ignore[attr-defined]
        if not row_id:
            return False
        if preview_rect.contains(position):
            self.preview_requested.emit(row_id)
            return True
        if regenerate_rect.contains(position):
            self.regenerate_requested.emit(row_id)
            return True
        return False