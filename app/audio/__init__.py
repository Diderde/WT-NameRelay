"""Audio-processing domain models and background services."""

from .models import (
    AudioClip,
    BlankClip,
    ExportSettings,
    TimelineClipKind,
    TimelineClipSnapshot,
    TimelineEditKind,
    TimelineLocation,
    TimelineModel,
    TimelineSnapshot,
    TimelineSplitResult,
    TimelineUndoResult,
    WaveformEnvelope,
)
from .project_service import AudioProjectService, ProjectGroupRepository
from .ffmpeg_service import (
    FfmpegLocator,
    AudioExportService,
    AudioPreviewService,
    AudioMatrixExportService,
    MatrixWriteResult,
)
from .waveform_service import WaveformCache, WaveformWorker

__all__ = [
    "AudioClip",
    "BlankClip",
    "ExportSettings",
    "TimelineClipKind",
    "TimelineClipSnapshot",
    "TimelineEditKind",
    "TimelineLocation",
    "TimelineModel",
    "TimelineSnapshot",
    "TimelineSplitResult",
    "TimelineUndoResult",
    "WaveformEnvelope",
    "AudioProjectService",
    "ProjectGroupRepository",
    "FfmpegLocator",
    "AudioExportService",
    "AudioPreviewService",
    "AudioMatrixExportService",
    "MatrixWriteResult",
    "WaveformCache",
    "WaveformWorker",
]
