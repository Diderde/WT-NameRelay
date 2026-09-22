from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from app.preferences import get_preference, set_preference

THEME_KEY = "ui/theme"
DEFAULT_MODE = "dark"

PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "background": "#0E141A",
        "background_alt": "#111922",
        "surface": "#18212A",
        "surface_hover": "#1D2833",
        "surface_pressed": "#151D25",
        "border": "#293540",
        "border_hover": "#8A6844",
        "text": "#F1F3F5",
        "text_muted": "#9AA6B2",
        "text_disabled": "#66727D",
        "accent": "#D09A5B",
        "accent_dark": "#A97842",
        "accent_hover": "#DCAA70",
        "accent_hover_border": "#E3B77E",
        "on_accent": "#10161B",
        "blue": "#6D8DA8",
        "success": "#65A77A",
        "failure": "#C6676A",
        "button_hover": "#222F3B",
        "disabled_bg": "#151C23",
        "disabled_border": "#222C35",
        "progress_bg": "#0E151B",
        "progress_border": "#26313A",
        "drop_border": "#445362",
        "drag_active_bg": "#17232E",
        "item_border": "#26333E",
        "unrecognized_border": "#73585A",
        "existing_audio": "#B76D70",
        "group_bg": "#151E27",
        "cancel_border": "#805156",
        "triple_bg": "#121B23",
        "checkbox_border": "#536270",
        "checkbox_bg": "#0D141A",
        "header_bg": "#202C37",
        "scrollbar_handle": "#34414D",
        "scrollbar_hover": "#4B5C6A",
        "water_deep": "#081420",
        "water_gold": "#D09A5B",
        "water_blue": "#6D8DA8",
        "water_teal": "#3E8E7E",
        "card_glass": "rgba(24, 33, 42, 208)",
        "card_glass_hover": "rgba(31, 42, 53, 220)",
        "card_glass_pressed": "rgba(20, 28, 36, 228)",
        "panel_glass": "rgba(21, 30, 39, 190)",
        "glass_border": "rgba(255, 255, 255, 36)",
        "timeline_clip": "#334351",
        "timeline_clip_selected": "#b97838",
        "timeline_waveform": "#91b8cc",
        "timeline_waveform_selected": "#d7edf6",
        "timeline_border": "#63798b",
        "timeline_border_selected": "#e3a353",
        "timeline_handle": "#e3a353",
        "timeline_text": "#dce7ef",
        "timeline_hover_text": "#a9cddd",
        "timeline_hover_line": "#8fbed6",
        "timeline_axis_text": "#9eb3c2",
        "timeline_axis_pen": "#63798b",
        "timeline_playhead": "#e3a353",
        "timeline_playhead_label": "#f0b66a",
        "timeline_split_flash": "#e3a353",
    },
    "light": {
        "background": "#F4F6F9",
        "background_alt": "#FFFFFF",
        "surface": "#FFFFFF",
        "surface_hover": "#EEF2F7",
        "surface_pressed": "#E3E9F0",
        "border": "#C9D3DD",
        "border_hover": "#A97842",
        "text": "#1C2530",
        "text_muted": "#5D6C7B",
        "text_disabled": "#9AA6B2",
        "accent": "#B4773B",
        "accent_dark": "#94612F",
        "accent_hover": "#C68A4F",
        "accent_hover_border": "#D09A5B",
        "on_accent": "#FFFFFF",
        "blue": "#3E6B96",
        "success": "#2E7D4F",
        "failure": "#B04548",
        "button_hover": "#E4EAF1",
        "disabled_bg": "#EDF1F5",
        "disabled_border": "#D9E0E8",
        "progress_bg": "#E9EEF3",
        "progress_border": "#D3DCE4",
        "drop_border": "#A9B7C5",
        "drag_active_bg": "#FBF1E4",
        "item_border": "#D6DEE6",
        "unrecognized_border": "#CBA6A8",
        "existing_audio": "#9E4B4E",
        "group_bg": "#F1F4F8",
        "cancel_border": "#D8AEB0",
        "triple_bg": "#EDF1F6",
        "checkbox_border": "#98A6B4",
        "checkbox_bg": "#FFFFFF",
        "header_bg": "#E8EDF3",
        "scrollbar_handle": "#C4CED8",
        "scrollbar_hover": "#A7B5C3",
        "water_deep": "#D9E4EF",
        "water_gold": "#C68A4F",
        "water_blue": "#3E6B96",
        "water_teal": "#2E7D66",
        "card_glass": "rgba(255, 255, 255, 198)",
        "card_glass_hover": "rgba(255, 255, 255, 220)",
        "card_glass_pressed": "rgba(233, 238, 244, 228)",
        "panel_glass": "rgba(255, 255, 255, 180)",
        "glass_border": "rgba(255, 255, 255, 215)",
        "timeline_clip": "#c7d2de",
        "timeline_clip_selected": "#b4773b",
        "timeline_waveform": "#3e6b96",
        "timeline_waveform_selected": "#1c2530",
        "timeline_border": "#93a3b4",
        "timeline_border_selected": "#8a5a28",
        "timeline_handle": "#b4773b",
        "timeline_text": "#1c2530",
        "timeline_hover_text": "#3e6b96",
        "timeline_hover_line": "#3e6b96",
        "timeline_axis_text": "#5d6c7b",
        "timeline_axis_pen": "#93a3b4",
        "timeline_playhead": "#b4773b",
        "timeline_playhead_label": "#8a5a28",
        "timeline_split_flash": "#b4773b",
    },
}

_active_mode: str | None = None
_system_scheme_connected = False
_MODE_LISTENERS: list[Callable[[str], None]] = []


def on_mode_changed(listener: Callable[[str], None]) -> None:
    """注册主题模式变化监听（QSS 之外的自绘控件用）。"""
    _MODE_LISTENERS.append(listener)


def _notify_mode_changed(mode: str) -> None:
    for listener in _MODE_LISTENERS:
        listener(mode)


def _on_system_scheme_changed(_scheme) -> None:
    """Live-follow the OS light/dark switch while the user has no explicit choice."""
    if _stored_mode() is not None:
        return
    application = QApplication.instance()
    if application is None:
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
    stored = get_preference(THEME_KEY)
    return stored if stored in PALETTES else None


def current_mode() -> str:
    global _active_mode
    if _active_mode is None:
        stored = _stored_mode()
        _active_mode = stored if stored is not None else _system_mode()
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
