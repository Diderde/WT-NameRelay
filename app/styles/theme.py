from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


COLORS: dict[str, str] = {
    "background": "#0E141A",
    "background_alt": "#111922",
    "surface": "#18212A",
    "surface_hover": "#1D2833",
    "surface_pressed": "#151D25",
    "border": "#293540",
    "border_hover": "#8A6844",
    "text": "#F1F3F5",
    "text_muted": "#9AA6B2",
    "accent": "#D09A5B",
    "accent_dark": "#A97842",
    "blue": "#6D8DA8",
    "success": "#65A77A",
    "failure": "#C6676A",
}


def _build_stylesheet() -> str:
    return f"""
    QWidget {{
        color: {COLORS['text']};
        font-size: 14px;
    }}
    QMainWindow,
    QWidget#appRoot,
    QWidget#animatedStack,
    QWidget#pageRoot {{
        background-color: {COLORS['background']};
    }}
    QLabel#appTitle {{
        color: {COLORS['text']};
        font-size: 30px;
        font-weight: 700;
    }}
    QLabel#disclaimerTitle {{ color: {COLORS['text']}; font-size: 20px; font-weight: 700; }}
    QLabel#disclaimerText {{ color: {COLORS['text_muted']}; font-size: 14px; }}
    QLabel#disclaimerImportant {{ color: {COLORS['accent']}; font-size: 14px; }}
    QLabel#disclaimerWarning {{ color: {COLORS['failure']}; font-size: 14px; font-weight: 600; }}
    QPushButton#disclaimerContinueButton:enabled {{ color: #10161B; background-color: {COLORS['accent']}; border-color: {COLORS['accent']}; }}
    QLabel#appSubtitle {{
        color: {COLORS['text_muted']};
        font-size: 14px;
    }}
    QLabel#sectionEyebrow {{
        color: {COLORS['accent']};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#pageTitle {{
        color: {COLORS['text']};
        font-size: 24px;
        font-weight: 700;
    }}
    QScrollArea#homeScroll,
    QScrollArea#crewContentScroll,
    QScrollArea#homeScroll > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QScrollArea#crewContentScroll > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QFrame#featureCardSurface {{
        background-color: {COLORS['surface']};
        border: 1px solid {COLORS['border']};
        border-radius: 14px;
    }}
    QFrame#featureCardSurface[hovered="true"],
    QFrame#featureCardSurface[focused="true"] {{
        background-color: {COLORS['surface_hover']};
        border-color: {COLORS['border_hover']};
    }}
    QFrame#featureCardSurface[pressed="true"] {{
        background-color: {COLORS['surface_pressed']};
        border-color: {COLORS['accent_dark']};
    }}
    QLabel#cardTitle {{
        color: {COLORS['text']};
        font-size: 18px;
        font-weight: 650;
    }}
    QLabel#cardDescription {{
        color: {COLORS['text_muted']};
        font-size: 13px;
    }}
    QLabel#cardAction {{
        color: {COLORS['accent']};
        font-size: 13px;
        font-weight: 600;
    }}
    QFrame#placeholderPanel,
    QFrame#taskStatusPanel {{
        background-color: {COLORS['surface']};
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
    }}
    QLabel#placeholderTitle {{
        color: {COLORS['text']};
        font-size: 18px;
        font-weight: 600;
    }}
    QLabel#placeholderText,
    QLabel#mutedLabel {{
        color: {COLORS['text_muted']};
    }}
    QLabel#statusPanelTitle {{
        color: {COLORS['text']};
        font-size: 15px;
        font-weight: 650;
    }}
    QLabel#statusLabel {{
        color: {COLORS['accent']};
        font-weight: 600;
    }}
    QLabel#statusLabel[taskState="completed"] {{ color: {COLORS['success']}; }}
    QLabel#statusLabel[taskState="partial_failed"],
    QLabel#statusLabel[taskState="failed"] {{ color: {COLORS['failure']}; }}
    QLabel#statusLabel[taskState="cancelled"] {{ color: {COLORS['text_muted']}; }}
    QLabel#failureLabel[hasFailures="true"] {{ color: {COLORS['failure']}; }}
    QPushButton {{
        min-height: 34px;
        padding: 0 16px;
        color: {COLORS['text']};
        background-color: {COLORS['surface_hover']};
        border: 1px solid {COLORS['border']};
        border-radius: 7px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        border-color: {COLORS['border_hover']};
        background-color: #222F3B;
    }}
    QPushButton:pressed {{
        background-color: {COLORS['surface_pressed']};
    }}
    QPushButton[audioNavigation="true"]:checked {{
        color: #10161B;
        background-color: {COLORS['accent']};
        border-color: {COLORS['accent']};
    }}
    QPushButton[audioNavigation="true"]:checked:hover {{
        background-color: #DCAA70;
        border-color: #E3B77E;
    }}
    QPushButton[audioNavigation="true"]:checked:pressed {{
        background-color: {COLORS['accent_dark']};
        border-color: {COLORS['accent_dark']};
    }}
    QPushButton:disabled {{
        color: #66727D;
        background-color: #151C23;
        border-color: #222C35;
    }}
    QPushButton#backButton {{
        min-width: 92px;
        padding: 0 14px;
        color: {COLORS['text_muted']};
        background-color: transparent;
    }}
    QPushButton#startButton:enabled {{
        color: #10161B;
        background-color: {COLORS['accent']};
        border-color: {COLORS['accent']};
    }}
    QPushButton#crewStartCopyButton:enabled {{
        color: #10161B;
        background-color: {COLORS['accent']};
        border-color: {COLORS['accent']};
    }}
    QPushButton#crewCancelTaskButton:enabled {{
        color: {COLORS['failure']};
        border-color: #805156;
    }}
    QProgressBar {{
        min-height: 14px;
        max-height: 14px;
        color: {COLORS['text']};
        background-color: #0E151B;
        border: 1px solid #26313A;
        border-radius: 7px;
        text-align: center;
        font-size: 10px;
        font-weight: 600;
    }}
    QProgressBar::chunk {{
        background-color: {COLORS['blue']};
        border-radius: 6px;
    }}
    QProgressBar[taskState="running"]::chunk {{ background-color: {COLORS['accent']}; }}
    QProgressBar[taskState="completed"]::chunk {{ background-color: {COLORS['success']}; }}
    QProgressBar[taskState="partial_failed"]::chunk {{ background-color: {COLORS['failure']}; }}
    QProgressBar[taskState="failed"]::chunk {{ background-color: {COLORS['failure']}; }}
    QFrame#crewManualPanel,
    QFrame#autoRecognitionPanel,
    QFrame#directorySelector,
    QFrame#autoScanResultPanel,
    QFrame#resultPanel,
    QFrame#crewActionBar,
    QFrame#autoActionBar {{
        background-color: {COLORS['surface']};
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
    }}
    QLabel#crewSectionTitle {{
        color: {COLORS['accent']};
        font-size: 20px;
        font-weight: 650;
    }}
    QLabel#crewPanelTitle,
    QLabel#autoRecognitionTitle {{
        color: {COLORS['text']};
        font-size: 18px;
        font-weight: 650;
    }}
    QFrame#fileDropArea {{
        background-color: {COLORS['background_alt']};
        border: 1px dashed #445362;
        border-radius: 10px;
    }}
    QFrame#fileDropArea[dragActive="true"] {{
        background-color: #17232E;
        border-color: {COLORS['accent']};
    }}
    QLabel#dropAreaTitle,
    QLabel#listHeading {{
        color: {COLORS['text']};
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
        background-color: {COLORS['background_alt']};
        border: 1px solid #26333E;
        border-radius: 8px;
    }}
    QFrame#sourceFileItem[recognized="false"] {{
        border-color: #73585A;
    }}
    QLabel#sourceFileName,
    QLabel#confirmationTargetName {{
        color: {COLORS['text']};
        font-weight: 600;
    }}
    QLabel#sourceFilePath,
    QLabel#confirmationTargetMeta,
    QLabel#confirmationGroupSummary {{
        color: {COLORS['text_muted']};
        font-size: 12px;
    }}
    QLabel#assignmentHint {{
        color: {COLORS['blue']};
        font-size: 12px;
    }}
    QLineEdit#directoryPathEdit,
    QLineEdit#autoSearchEdit {{
        min-height: 34px;
        padding: 0 10px;
        color: {COLORS['text']};
        background-color: {COLORS['background_alt']};
        border: 1px solid {COLORS['border']};
        border-radius: 7px;
    }}
    QLineEdit#directoryPathEdit:focus,
    QLineEdit#autoSearchEdit:focus {{ border-color: {COLORS['border_hover']}; }}
    QLabel#autoScanStatus {{ color: {COLORS['accent']}; font-weight: 600; }}
    QLabel#autoLegend,
    QLabel#autoPlanStats {{ color: {COLORS['text_muted']}; font-size: 12px; }}
    QScrollArea#autoResultsScroll,
    QScrollArea#autoResultsScroll > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QFrame#autoCompletionGroup {{
        background-color: #151E27;
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
    }}
    QPushButton#autoGroupToggle {{
        text-align: left;
        color: {COLORS['accent']};
        background: transparent;
        border: none;
        padding: 2px 0;
    }}
    QLabel#autoGroupSummary,
    QLabel#autoMissingMeta {{ color: {COLORS['text_muted']}; font-size: 12px; }}
    QLabel#existingFilesCaption {{ color: {COLORS['text_muted']}; font-weight: 600; }}
    QLabel#missingFilesCaption {{ color: {COLORS['text']}; font-weight: 600; }}
    QLabel#existingAudioFile {{ color: #B76D70; }}
    QLabel#autoMissingTarget {{ color: {COLORS['text']}; font-weight: 600; }}
    QLabel#autoFailureReason {{ color: {COLORS['failure']}; font-size: 12px; }}
    QFrame#autoMissingRow {{
        background-color: {COLORS['background_alt']};
        border: 1px solid #26333E;
        border-radius: 8px;
    }}
    QFrame#autoGroupSeparator {{
        border: none;
        border-top: 1px dashed #3A4652;
        background: transparent;
    }}
    QPushButton#smallActionButton {{ min-height: 28px; padding: 0 10px; font-size: 12px; }}
    QLabel#sourceFileState[recognized="true"] {{ color: {COLORS['success']}; }}
    QLabel#sourceFileState[recognized="false"] {{ color: {COLORS['failure']}; }}
    QFrame#confirmationGroup {{
        background-color: #151E27;
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
    }}
    QFrame#radioAverageTriple {{
        background-color: #121B23;
        border: 1px dashed #3A4652;
        border-radius: 8px;
    }}
    QFrame#confirmationSeparator {{
        border: none;
        border-top: 1px dashed #3A4652;
        background: transparent;
    }}
    QLabel#confirmationGroupTitle {{
        color: {COLORS['accent']};
        font-weight: 650;
    }}
    QLabel#confirmationGroupCount {{ color: {COLORS['blue']}; }}
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid #536270;
        border-radius: 3px;
        background: #0D141A;
    }}
    QCheckBox::indicator:checked {{
        background: {COLORS['accent']};
        border-color: {COLORS['accent']};
    }}
    QTreeWidget#resultsTree {{
        background-color: {COLORS['background_alt']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        alternate-background-color: #151E27;
    }}
    QTreeWidget#resultsTree::item {{ padding: 5px; }}
    QHeaderView::section {{
        background-color: #202C37;
        color: {COLORS['text_muted']};
        border: none;
        border-bottom: 1px solid {COLORS['border']};
        padding: 6px;
        font-weight: 600;
    }}
    QSplitter#crewManualSplitter::handle {{ background: transparent; }}
    QSplitter#autoScanSplitter::handle {{ background: transparent; }}
    QScrollBar:vertical {{
        width: 12px;
        background: transparent;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        min-height: 28px;
        background: #34414D;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{ background: #4B5C6A; }}
    QScrollBar::handle:vertical:pressed {{ background: {COLORS['accent']}; }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{ height: 0; }}
    """


def apply_theme(application: QApplication) -> None:
    """Apply a stable cross-platform Qt style and the application palette."""
    application.setStyle("Fusion")
    application.setFont(QFont("Microsoft YaHei UI", 10))

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["background"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["background_alt"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["background"]))
    application.setPalette(palette)
    application.setStyleSheet(_build_stylesheet())
