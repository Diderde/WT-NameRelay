"""Reusable UI widgets."""

from .animated_stack import AnimatedStack, TransitionDirection
from .auto_scan_result_panel import AutoScanResultPanel
from .confirmation_group import ConfirmationGroup
from .copy_mode_switch import CopyModeSwitch
from .radio_confirmation_group import RadioManualConfirmationGroup
from .completion_group_widget import CompletionGroupWidget
from .directory_selector import DirectorySelector
from .feature_card import FeatureCard
from .file_drop_area import FileDropArea
from .source_file_list import SourceFileList
from .scroll_position_guard import ScrollPositionGuard
from .audio_page_scroll_router import AudioPageScrollRouter
from .task_status_panel import TaskStatusPanel
from .timeline_editor import TimelineEditor
from .pyqtgraph_timeline import PyQtGraphTimeline
from .about_dialog import AboutDialog
from .disclaimer_dialog import DisclaimerDialog
from .license_dialog import LicenseDialog

__all__ = [
    "AnimatedStack",
    "AutoScanResultPanel",
    "AboutDialog",
    "CompletionGroupWidget",
    "ConfirmationGroup",
    "CopyModeSwitch",
    "RadioManualConfirmationGroup",
    "DirectorySelector",
    "DisclaimerDialog",
    "LicenseDialog",
    "FeatureCard",
    "FileDropArea",
    "SourceFileList",
    "ScrollPositionGuard",
    "AudioPageScrollRouter",
    "TaskStatusPanel",
    "TimelineEditor",
    "PyQtGraphTimeline",
    "TransitionDirection",
]
