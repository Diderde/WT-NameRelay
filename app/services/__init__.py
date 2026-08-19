"""Future file-processing service boundaries."""

from .bank_service import BankFileService
from .bank_copy_task_builder import BankCopyTaskBuilder
from .bank_filename_parser import BankFilenameParser
from .bank_name_repository import BankNameRepository
from .bank_pair_matcher import BankPairMatcher
from .auto_completion_analyzer import AutoCompletionAnalyzer
from .auto_scan_service import AutoScanService
from .base_service import BaseTaskService
from .copy_task_builder import CopyTaskBuilder
from .crew_name_parser import CrewNameParser
from .crew_name_repository import CrewNameRepository
from .crew_service import CrewFileService
from .directory_scanner import DirectoryScanner, SUPPORTED_AUDIO_SUFFIXES
from .radio_service import RadioFileService
from .radio_average_plan_builder import RadioAveragePlanBuilder, RadioImportLimitViolation
from .radio_staged_service import DistributionFileCopyService, RadioStagedFileService
from .matrix_group_planner import MatrixGroupLayout, MatrixGroupPlanner, MatrixSubgroup
from .average_distribution import (
    AUDIO_SUFFIX_PRIORITY,
    AudioProcessingSourceAdapter,
    AverageDistributionPlanner,
    RadioManualSourceAdapter,
    SourceCandidateNormalizer,
)

__all__ = [
    "AutoCompletionAnalyzer",
    "AutoScanService",
    "BankFileService",
    "BankCopyTaskBuilder",
    "BankFilenameParser",
    "BankNameRepository",
    "BankPairMatcher",
    "BaseTaskService",
    "CopyTaskBuilder",
    "CrewFileService",
    "CrewNameParser",
    "CrewNameRepository",
    "DirectoryScanner",
    "RadioFileService",
    "RadioAveragePlanBuilder",
    "RadioImportLimitViolation",
    "RadioStagedFileService",
    "DistributionFileCopyService",
    "MatrixGroupLayout",
    "MatrixGroupPlanner",
    "MatrixSubgroup",
    "SUPPORTED_AUDIO_SUFFIXES",
    "AUDIO_SUFFIX_PRIORITY",
    "AudioProcessingSourceAdapter",
    "AverageDistributionPlanner",
    "RadioManualSourceAdapter",
    "SourceCandidateNormalizer",
]
