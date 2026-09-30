from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from app.preferences import get_preference, set_preference

THEME_KEY = "ui/theme"
DEFAULT_MODE = "dark"

# 昼夜双主题色板：参考本地 HTML 原型的 :root（白天）与
# html[data-theme="dark"]（黑夜）两套 CSS 变量制作——
# 蓝色 accent（白天 #3b82f6 / 黑夜 #60a5fa）、黑夜为冷调海军蓝（#0b1020 系）、
# 白天为净白蓝灰（#f8f9fc 系）；语义键（success/warning/danger）沿用参考定义。
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "background": "#0b1020",
        "background_alt": "#111827",
        "surface": "#182235",
        "surface_hover": "#243247",
        "surface_pressed": "#141d31",
        "border": "#263149",
        "border_hover": "#3b82f6",
        "text": "#edf3ff",
        "text_muted": "#c3cee0",
        "text_disabled": "#8f9bb0",
        "accent": "#60a5fa",
        "accent_dark": "#3b82f6",
        "accent_hover": "#93c5fd",
        "accent_hover_border": "#bfdbfe",
        "on_accent": "#0b1020",
        "blue": "#3b82f6",
        "success": "#10b981",
        "failure": "#ef4444",
        "button_hover": "#1d2a44",
        "disabled_bg": "#0f172a",
        "disabled_border": "#1c2740",
        "progress_bg": "#0d1426",
        "progress_border": "#1e2a44",
        "drop_border": "#3b4a6b",
        "drag_active_bg": "#14213d",
        "item_border": "#223050",
        "unrecognized_border": "#5c3a44",
        "existing_audio": "#c97b7e",
        "group_bg": "#0f1626",
        "cancel_border": "#6e3f49",
        "triple_bg": "#101828",
        "checkbox_border": "#44506b",
        "checkbox_bg": "#0b1020",
        "header_bg": "#1a2438",
        "scrollbar_handle": "#2e3a55",
        "scrollbar_hover": "#3d4b6e",
        "water_deep": "#0a0f1e",
        "water_gold": "#60a5fa",
        "water_blue": "#2563eb",
        "water_teal": "#10b981",
        "card_glass": "rgba(17, 24, 39, 210)",
        "card_glass_hover": "rgba(36, 50, 71, 220)",
        "card_glass_pressed": "rgba(11, 16, 32, 228)",
        "panel_glass": "rgba(13, 20, 38, 195)",
        "glass_border": "rgba(255, 255, 255, 36)",
        "timeline_clip": "#26334d",
        "timeline_clip_selected": "#3b82f6",
        "timeline_waveform": "#7aa5e0",
        "timeline_waveform_selected": "#bfdbfe",
        "timeline_border": "#44557a",
        "timeline_border_selected": "#60a5fa",
        "timeline_handle": "#60a5fa",
        "timeline_text": "#dbe7ff",
        "timeline_hover_text": "#93c5fd",
        "timeline_hover_line": "#60a5fa",
        "timeline_axis_text": "#8f9bb0",
        "timeline_axis_pen": "#44557a",
        "timeline_playhead": "#60a5fa",
        "timeline_playhead_label": "#93c5fd",
        "timeline_split_flash": "#60a5fa",
    },
    "light": {
        "background": "#f8f9fc",
        "background_alt": "#ffffff",
        "surface": "#ffffff",
        "surface_hover": "#f1f5f9",
        "surface_pressed": "#e2e8f0",
        "border": "#dfe3ec",
        "border_hover": "#2563eb",
        "text": "#1a1a2e",
        "text_muted": "#4a4a5a",
        "text_disabled": "#6b6b7a",
        "accent": "#3b82f6",
        "accent_dark": "#2563eb",
        "accent_hover": "#60a5fa",
        "accent_hover_border": "#93c5fd",
        "on_accent": "#ffffff",
        "blue": "#2563eb",
        "success": "#10b981",
        "failure": "#ef4444",
        "button_hover": "#eef2f7",
        "disabled_bg": "#f1f5f9",
        "disabled_border": "#e2e8f0",
        "progress_bg": "#eef1f6",
        "progress_border": "#dfe3ec",
        "drop_border": "#b6c2d2",
        "drag_active_bg": "#e7effd",
        "item_border": "#e2e8f0",
        "unrecognized_border": "#d9a3a5",
        "existing_audio": "#b04548",
        "group_bg": "#f4f6fa",
        "cancel_border": "#d8aeb0",
        "triple_bg": "#f1f5f9",
        "checkbox_border": "#98a6b4",
        "checkbox_bg": "#ffffff",
        "header_bg": "#eef1f6",
        "scrollbar_handle": "#c9d2dd",
        "scrollbar_hover": "#aeb9c6",
        "water_deep": "#e3eaf4",
        "water_gold": "#3b82f6",
        "water_blue": "#1d4ed8",
        "water_teal": "#0e9f76",
        "card_glass": "rgba(255, 255, 255, 210)",
        "card_glass_hover": "rgba(241, 245, 249, 228)",
        "card_glass_pressed": "rgba(226, 232, 240, 235)",
        "panel_glass": "rgba(248, 249, 252, 190)",
        "glass_border": "rgba(15, 23, 42, 30)",
        "timeline_clip": "#dbe4f0",
        "timeline_clip_selected": "#2563eb",
        "timeline_waveform": "#3b82f6",
        "timeline_waveform_selected": "#1a1a2e",
        "timeline_border": "#a8b3c4",
        "timeline_border_selected": "#1d4ed8",
        "timeline_handle": "#2563eb",
        "timeline_text": "#1a1a2e",
        "timeline_hover_text": "#2563eb",
        "timeline_hover_line": "#2563eb",
        "timeline_axis_text": "#6b6b7a",
        "timeline_axis_pen": "#a8b3c4",
        "timeline_playhead": "#2563eb",
        "timeline_playhead_label": "#1d4ed8",
        "timeline_split_flash": "#2563eb",
    },
}

_active_mode: str | None = None
_system_scheme_connected = False
_MODE_LISTENERS: list[Callable[[str], None]] = []


def on_mode_changed(listener: Callable[[str], None]) -> None:
    """注册主题模式变化监听（QSS 之外的自绘控件用）。"""
    _MODE_LISTENERS.append(listener)


def off_mode_changed(listener: Callable[[str], None]) -> None:
    """退订主题模式监听：控件销毁后必须摘除回调，避免打到已删除的 C++ 对象上。"""
    try:
        _MODE_LISTENERS.remove(listener)
    except ValueError:
        pass


def _notify_mode_changed(mode: str) -> None:
    for listener in _MODE_LISTENERS:
        listener(mode)


def _on_system_scheme_changed(_scheme) -> None:
    """系统明暗切换实时生效；用户已手动选择主题时保持用户选择不跟系统。"""
    application = QApplication.instance()
    if application is None:
        return
    if _stored_mode() is not None:
        return
    global _active_mode
    _active_mode = None
    apply_theme(application)
    _notify_mode_changed(current_mode())


def available_modes() -> tuple[str, ...]:
    return tuple(PALETTES)


def _system_mode() -> str:
    application = QApplication.instance()
    if application is None:
        return DEFAULT_MODE
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Light:
        return "light"
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    return DEFAULT_MODE


def _stored_mode() -> str | None:
    """历史主题偏好：手动切换入口恢复后重新参与取值（见 current_mode）。"""

    stored = get_preference(THEME_KEY)
    return stored if stored in PALETTES else None


def current_mode() -> str:
    """当前模式：手动选择（set_mode/历史偏好）优先，从未选择过则跟随系统。"""

    global _active_mode
    if _active_mode is None:
        stored = _stored_mode()
        _active_mode = stored if stored else _system_mode()
    return _active_mode


def set_mode(mode: str) -> None:
    if mode not in PALETTES:
        raise ValueError(f"不支持的主题模式：{mode}")
    set_preference(THEME_KEY, mode)
    application = QApplication.instance()
    if application is not None:
        apply_theme(application, mode)
    _notify_mode_changed(current_mode())


def color(key: str) -> str:
    return PALETTES[current_mode()][key]


def _build_stylesheet(colors: dict[str, str]) -> str:
    return f"""
    QWidget {{
        color: {colors['text']};
        font-size: 14px;
    }}
    QMainWindow {{
        background-color: {colors['background']};
    }}
    QWidget#appRoot,
    QWidget#animatedStack,
    QWidget#pageRoot {{
        background: transparent;
    }}
    QLabel#appTitle {{
        color: {colors['text']};
        font-size: 30px;
        font-weight: 700;
    }}
    QLabel#disclaimerTitle {{ color: {colors['text']}; font-size: 20px; font-weight: 700; }}
    QLabel#disclaimerText {{ color: {colors['text_muted']}; font-size: 14px; }}
    QLabel#aboutFooter {{ color: {colors['text_muted']}; font-size: 11px; }}
    QLabel#disclaimerRepoHint {{ color: {colors['text_muted']}; font-weight: 700; }}
    QLabel#disclaimerImportant {{ color: {colors['accent']}; font-size: 14px; }}
    QLabel#disclaimerWarning {{ color: {colors['failure']}; font-size: 14px; font-weight: 600; }}
    QPushButton#disclaimerContinueButton:enabled {{ color: {colors['on_accent']}; background-color: {colors['accent']}; border-color: {colors['accent']}; }}
    QLabel#appSubtitle {{
        color: {colors['text_muted']};
        font-size: 14px;
    }}
    QLabel#sectionEyebrow {{
        color: {colors['accent']};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#pageTitle {{
        color: {colors['text']};
        font-size: 24px;
        font-weight: 700;
    }}
    QScrollArea#homeScroll,
    QScrollArea#crewContentScroll,
    QScrollArea#copyGroupScroll,
    QScrollArea#audioProcessingScroll,
    QScrollArea#homeScroll > QWidget > QWidget,
    QScrollArea#crewContentScroll > QWidget > QWidget,
    QScrollArea#copyGroupScroll > QWidget > QWidget,
    QScrollArea#audioProcessingScroll > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QFrame#featureCardSurface {{
        background-color: {colors['card_glass']};
        border: 1px solid {colors['glass_border']};
        border-radius: 14px;
    }}
    QFrame#featureCardSurface[hovered="true"],
    QFrame#featureCardSurface[focused="true"] {{
        background-color: {colors['card_glass_hover']};
        border-color: {colors['border_hover']};
    }}
    QFrame#featureCardSurface[pressed="true"] {{
        background-color: {colors['card_glass_pressed']};
        border-color: {colors['accent_dark']};
    }}
    QLabel#cardTitle {{
        color: {colors['text']};
        font-size: 18px;
        font-weight: 650;
    }}
    QLabel#cardDescription {{
        color: {colors['text_muted']};
        font-size: 13px;
    }}
    QLabel#cardAction {{
        color: {colors['accent']};
        font-size: 13px;
        font-weight: 600;
    }}
    QFrame#placeholderPanel,
    QFrame#taskStatusPanel {{
        background-color: {colors['panel_glass']};
        border: 1px solid {colors['glass_border']};
        border-radius: 12px;
    }}
    QLabel#placeholderTitle {{
        color: {colors['text']};
        font-size: 18px;
        font-weight: 600;
    }}
    QLabel#placeholderText,
    QLabel#mutedLabel {{
        color: {colors['text_muted']};
    }}
    QLabel#statusPanelTitle {{
        color: {colors['text']};
        font-size: 15px;
        font-weight: 650;
    }}
    QLabel#statusLabel {{
        color: {colors['accent']};
        font-weight: 600;
    }}
    QLabel#statusLabel[taskState="completed"] {{ color: {colors['success']}; }}
    QLabel#statusLabel[taskState="partial_failed"],
    QLabel#statusLabel[taskState="failed"] {{ color: {colors['failure']}; }}
    QLabel#statusLabel[taskState="cancelled"] {{ color: {colors['text_muted']}; }}
    QLabel#failureLabel[hasFailures="true"] {{ color: {colors['failure']}; }}
    QLabel#hubTag[hubState="ok"] {{ color: {colors['success']}; }}
    QLabel#hubTag[hubState="bad"] {{ color: {colors['failure']}; }}
    QLabel#hubSectionTitle {{
        color: {colors['text']};
        font-size: 16px;
        font-weight: 650;
    }}
    QPushButton {{
        min-height: 34px;
        padding: 0 16px;
        color: {colors['text']};
        background-color: {colors['surface_hover']};
        border: 1px solid {colors['border']};
        border-radius: 7px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        border-color: {colors['border_hover']};
        background-color: {colors['button_hover']};
    }}
    QPushButton:pressed {{
        background-color: {colors['surface_pressed']};
    }}
    QPushButton[audioNavigation="true"]:checked {{
        color: {colors['on_accent']};
        background-color: {colors['accent']};
        border-color: {colors['accent']};
    }}
    QPushButton[audioNavigation="true"]:checked:hover {{
        background-color: {colors['accent_hover']};
        border-color: {colors['accent_hover_border']};
    }}
    QPushButton[audioNavigation="true"]:checked:pressed {{
        background-color: {colors['accent_dark']};
        border-color: {colors['accent_dark']};
    }}
    QPushButton:disabled {{
        color: {colors['text_disabled']};
        background-color: {colors['disabled_bg']};
        border-color: {colors['disabled_border']};
    }}
    QPushButton#backButton {{
        min-width: 92px;
        padding: 0 14px;
        color: {colors['text_muted']};
        background-color: transparent;
        border: 2px solid {colors['border']};
    }}
    QPushButton#startButton:enabled {{
        color: {colors['on_accent']};
        background-color: {colors['accent']};
        border-color: {colors['accent']};
    }}
    QPushButton#crewStartCopyButton:enabled {{
        color: {colors['on_accent']};
        background-color: {colors['accent']};
        border-color: {colors['accent']};
    }}
    QPushButton#crewCancelTaskButton:enabled {{
        color: {colors['failure']};
        border-color: {colors['cancel_border']};
    }}
    QProgressBar {{
        min-height: 14px;
        max-height: 14px;
        color: {colors['text']};
        background-color: {colors['progress_bg']};
        border: 1px solid {colors['progress_border']};
        border-radius: 7px;
        text-align: center;
        font-size: 10px;
        font-weight: 600;
    }}
    QProgressBar::chunk {{
        background-color: {colors['blue']};
        border-radius: 6px;
    }}
    QProgressBar[taskState="running"]::chunk {{ background-color: {colors['accent']}; }}
    QProgressBar[taskState="completed"]::chunk {{ background-color: {colors['success']}; }}
    QProgressBar[taskState="partial_failed"]::chunk {{ background-color: {colors['failure']}; }}
    QProgressBar[taskState="failed"]::chunk {{ background-color: {colors['failure']}; }}
    QFrame#voicePane {{
        background-color: {colors['panel_glass']};
        border: 1px solid {colors['glass_border']};
        border-radius: 12px;
    }}
    QGroupBox#trainToolGroup {{
        background-color: {colors['panel_glass']};
        border: 1px solid {colors['glass_border']};
        border-radius: 10px;
        margin-top: 10px;
        padding: 8px 6px 6px 6px;
        font-weight: 600;
    }}
    QGroupBox#trainToolGroup::title {{
        subcontrol-origin: border;
        left: 10px;
        padding: 0 4px;
        color: {colors['accent']};
    }}
    QFrame#crewManualPanel,
    QFrame#autoRecognitionPanel,
    QFrame#directorySelector,
    QFrame#autoScanResultPanel,
    QFrame#resultPanel,
    QFrame#crewActionBar,
    QFrame#autoActionBar {{
        background-color: {colors['panel_glass']};
        border: 1px solid {colors['glass_border']};
        border-radius: 12px;
    }}
    QLabel#crewSectionTitle {{
        color: {colors['accent']};
        font-size: 20px;
        font-weight: 650;
    }}
    QLabel#crewPanelTitle,
    QLabel#autoRecognitionTitle {{
        color: {colors['text']};
        font-size: 18px;
        font-weight: 650;
    }}
    QFrame#fileDropArea {{
        background-color: {colors['background_alt']};
        border: 1px dashed {colors['drop_border']};
        border-radius: 10px;
    }}
    QFrame#fileDropArea[dragActive="true"] {{
        background-color: {colors['drag_active_bg']};
        border-color: {colors['accent']};
    }}
    QLabel#dropAreaTitle,
    QLabel#listHeading {{
        color: {colors['text']};
        font-weight: 600;
    }}
    QLabel#dropAreaTitle {{ font-size: 16px; }}
    QScrollArea#sourceFileScroll,
    QScrollArea#confirmationScroll,
    QScrollArea#sourceFileScroll > QWidget > QWidget,
    QScrollArea#confirmationScroll > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QFrame#sourceFileItem,
    QFrame#confirmationTargetRow {{
        background-color: {colors['background_alt']};
        border: 1px solid {colors['item_border']};
        border-radius: 8px;
    }}
    QFrame#sourceFileItem[recognized="false"] {{
        border-color: {colors['unrecognized_border']};
    }}
    QLabel#sourceFileName,
    QLabel#confirmationTargetName {{
        color: {colors['text']};
        font-weight: 600;
    }}
    QLabel#sourceFilePath,
    QLabel#confirmationTargetMeta,
    QLabel#confirmationGroupSummary {{
        color: {colors['text_muted']};
        font-size: 12px;
    }}
    QLabel#assignmentHint {{
        color: {colors['blue']};
        font-size: 12px;
    }}
    QLineEdit#directoryPathEdit,
    QLineEdit#autoSearchEdit {{
        min-height: 34px;
        padding: 0 10px;
        color: {colors['text']};
        background-color: {colors['background_alt']};
        border: 1px solid {colors['border']};
        border-radius: 7px;
    }}
    QLineEdit#directoryPathEdit:focus,
    QLineEdit#autoSearchEdit:focus {{ border-color: {colors['border_hover']}; }}
    QLabel#autoScanStatus {{ color: {colors['accent']}; font-weight: 600; }}
    QLabel#autoLegend,
    QLabel#autoPlanStats {{ color: {colors['text_muted']}; font-size: 12px; }}
    QScrollArea#autoResultsScroll,
    QScrollArea#autoResultsScroll > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QFrame#autoCompletionGroup {{
        background-color: {colors['group_bg']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
    }}
    QPushButton#autoGroupToggle {{
        text-align: left;
        color: {colors['accent']};
        background: transparent;
        border: none;
        padding: 2px 0;
    }}
    QLabel#autoGroupSummary,
    QLabel#autoMissingMeta {{ color: {colors['text_muted']}; font-size: 12px; }}
    QLabel#existingFilesCaption {{ color: {colors['text_muted']}; font-weight: 600; }}
    QLabel#missingFilesCaption {{ color: {colors['text']}; font-weight: 600; }}
    QLabel#existingAudioFile {{ color: {colors['existing_audio']}; }}
    QLabel#autoMissingTarget {{ color: {colors['text']}; font-weight: 600; }}
    QLabel#autoFailureReason {{ color: {colors['failure']}; font-size: 12px; }}
    QFrame#autoMissingRow {{
        background-color: {colors['background_alt']};
        border: 1px solid {colors['item_border']};
        border-radius: 8px;
    }}
    QFrame#autoGroupSeparator {{
        border: none;
        border-top: 1px dashed {colors['scrollbar_handle']};
        background: transparent;
    }}
    QPushButton#smallActionButton {{ min-height: 28px; padding: 0 10px; font-size: 12px; }}
    QLabel#sourceFileState[recognized="true"] {{ color: {colors['success']}; }}
    QLabel#sourceFileState[recognized="false"] {{ color: {colors['failure']}; }}
    QFrame#confirmationGroup {{
        background-color: {colors['group_bg']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
    }}
    QFrame#radioAverageTriple {{
        background-color: {colors['triple_bg']};
        border: 1px dashed {colors['scrollbar_handle']};
        border-radius: 8px;
    }}
    QFrame#confirmationSeparator {{
        border: none;
        border-top: 1px dashed {colors['scrollbar_handle']};
        background: transparent;
    }}
    QLabel#confirmationGroupTitle {{
        color: {colors['accent']};
        font-weight: 650;
    }}
    QLabel#confirmationGroupCount {{ color: {colors['blue']}; }}
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid {colors['checkbox_border']};
        border-radius: 3px;
        background: {colors['checkbox_bg']};
    }}
    QCheckBox::indicator:checked {{
        background: {colors['accent']};
        border-color: {colors['accent']};
    }}
    QTreeWidget#resultsTree {{
        background-color: {colors['background_alt']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        alternate-background-color: {colors['group_bg']};
    }}
    QTreeWidget#resultsTree::item {{ padding: 5px; }}
    QHeaderView::section {{
        background-color: {colors['header_bg']};
        color: {colors['text_muted']};
        border: none;
        border-bottom: 1px solid {colors['border']};
        padding: 6px;
        font-weight: 600;
    }}
    QListWidget#licenseList {{
        background-color: {colors['background_alt']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        padding: 4px;
    }}
    QListWidget#licenseList::item {{ padding: 8px; border-radius: 6px; }}
    QListWidget#licenseList::item:hover {{ background: {colors['surface_hover']}; }}
    QListWidget#licenseList::item:selected {{
        background: {colors['accent']};
        color: {colors['on_accent']};
    }}
    QLabel#licensePageTitle {{ color: {colors['accent']}; font-size: 16px; font-weight: 650; }}
    QTextBrowser#licenseBrowser {{ background: transparent; border: none; font-size: 13px; }}
    QSplitter#crewManualSplitter::handle {{ background: transparent; }}
    QSplitter#autoScanSplitter::handle {{ background: transparent; }}
    QScrollBar:vertical {{
        width: 12px;
        background: transparent;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        min-height: 28px;
        background: {colors['scrollbar_handle']};
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {colors['scrollbar_hover']}; }}
    QScrollBar::handle:vertical:pressed {{ background: {colors['accent']}; }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{ height: 0; }}
    """


def apply_theme(application: QApplication, mode: str | None = None) -> None:
    """Apply a stable cross-platform Qt style and the application palette."""
    global _active_mode, _system_scheme_connected
    if mode in PALETTES:
        _active_mode = mode
    else:
        _active_mode = current_mode()
    colors = PALETTES[_active_mode]
    if not _system_scheme_connected:
        QGuiApplication.styleHints().colorSchemeChanged.connect(_on_system_scheme_changed)
        _system_scheme_connected = True
    application.setStyle("Fusion")
    application.setFont(QFont("Microsoft YaHei UI", 10))

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["background"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["background_alt"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["background"]))
    application.setPalette(palette)
    application.setStyleSheet(_build_stylesheet(colors))
