"""Future file-processing service boundaries."""

from .auto_completion_analyzer import AutoCompletionAnalyzer
from .auto_scan_service import AutoScanService
from .average_distribution import (
    AUDIO_SUFFIX_PRIORITY,
    AudioProcessingSourceAdapter,
    AverageDistributionPlanner,
    RadioManualSourceAdapter,
    SourceCandidateNormalizer,
)
from .bank_copy_task_builder import BankCopyTaskBuilder
from .bank_filename_parser import BankFilenameParser
from .bank_name_repository import BankNameRepository
from .bank_pair_matcher import BankPairMatcher
from .bank_service import BankFileService
from .base_service import BaseTaskService
from .copy_task_builder import CopyTaskBuilder
from .crew_name_parser import CrewNameParser
from .crew_name_repository import CrewNameRepository
from .crew_service import CrewFileService
from .directory_scanner import SUPPORTED_AUDIO_SUFFIXES, DirectoryScanner
from .matrix_group_planner import MatrixGroupLayout, MatrixGroupPlanner, MatrixSubgroup
from .radio_average_plan_builder import (
    RadioAveragePlanBuilder,
    RadioImportLimitViolation,
)
from .radio_service import RadioFileService
from .radio_staged_service import DistributionFileCopyService, RadioStagedFileService

__all__ = [
    "AUDIO_SUFFIX_PRIORITY",
    "SUPPORTED_AUDIO_SUFFIXES",
    "AudioProcessingSourceAdapter",
    "AutoCompletionAnalyzer",
    "AutoScanService",
    "AverageDistributionPlanner",
    "BankCopyTaskBuilder",
    "BankFileService",
    "BankFilenameParser",
    "BankNameRepository",
    "BankPairMatcher",
    "BaseTaskService",
    "CopyTaskBuilder",
    "CrewFileService",
    "CrewNameParser",
    "CrewNameRepository",
    "DirectoryScanner",
    "DistributionFileCopyService",
    "MatrixGroupLayout",
    "MatrixGroupPlanner",
    "MatrixSubgroup",
    "RadioAveragePlanBuilder",
    "RadioFileService",
    "RadioImportLimitViolation",
    "RadioManualSourceAdapter",
    "RadioStagedFileService",
    "SourceCandidateNormalizer",
]
