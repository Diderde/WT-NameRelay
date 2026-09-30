"""Audio-processing domain models and background services."""

from .analysis_service import (
    LoudnessScanWorker,
    SpectrumWorker,
    parse_ebur128_summary,
)
from .ffmpeg_service import (
    AudioExportService,
    AudioMatrixExportService,
    AudioPreviewService,
    FfmpegLocator,
    MatrixWriteResult,
    format_codec_args,
    loudness_cache_key,
    output_extension,
    parse_loudnorm_json,
)
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
from .silence_service import SilenceDetectWorker, parse_silence_log
from .waveform_service import WaveformCache, WaveformWorker

__all__ = [
    "AudioClip",
    "AudioExportService",
    "AudioMatrixExportService",
    "AudioPreviewService",
    "AudioProjectService",
    "BlankClip",
    "ExportSettings",
    "FfmpegLocator",
    "LoudnessScanWorker",
    "MatrixWriteResult",
    "ProjectGroupRepository",
    "SilenceDetectWorker",
    "SpectrumWorker",
    "TimelineClipKind",
    "TimelineClipSnapshot",
    "TimelineEditKind",
    "TimelineLocation",
    "TimelineModel",
    "TimelineSnapshot",
    "TimelineSplitResult",
    "TimelineUndoResult",
    "WaveformCache",
    "WaveformEnvelope",
    "WaveformWorker",
    "format_codec_args",
    "loudness_cache_key",
    "output_extension",
    "parse_ebur128_summary",
    "parse_loudnorm_json",
    "parse_silence_log",
]
