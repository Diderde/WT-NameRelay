"""Immutable domain models used by the crew manual-copy workflow."""

from .copy_task import (
    ConflictPolicy,
    CopyBatchResult,
    CopyPlan,
    CopyResult,
    CopyResultStatus,
    CopyTask,
    CrewGroupPlan,
    ManualBatchState,
    TargetAssignment,
)
from .crew_name_group import CrewGroupType, CrewNameGroup
from .completion_group import AutoCompletionAnalysis, CompletionGroup
from .directory_scan_result import AutoScanState, DirectoryScanResult, ScannedDirectory
from .source_file import RecognitionState, SourceFile
from .average_distribution import ConflictKind, DistributionPlan, SourceCandidate, TargetBucket, TargetOperation
from .bank_models import BankCountryAssignment, BankCountryGroup, BankFile, BankFileRole
from .radio_copy import (
    ManualCopyMode,
    RadioManualGroupPlan,
    RadioSourceUnit,
    RadioStagedCopyPlan,
    RadioTargetAssignment,
    RadioTargetConflictKind,
    RadioTargetOperation,
    RadioTargetTriple,
)

__all__ = [
    "AutoCompletionAnalysis",
    "BankCountryAssignment",
    "BankCountryGroup",
    "BankFile",
    "BankFileRole",
    "AutoScanState",
    "CompletionGroup",
    "ConflictPolicy",
    "CopyBatchResult",
    "CopyPlan",
    "CopyResult",
    "CopyResultStatus",
    "CopyTask",
    "CrewGroupPlan",
    "ManualBatchState",
    "CrewGroupType",
    "CrewNameGroup",
    "DirectoryScanResult",
    "RecognitionState",
    "SourceFile",
    "ConflictKind",
    "DistributionPlan",
    "SourceCandidate",
    "TargetBucket",
    "TargetOperation",
    "ScannedDirectory",
    "TargetAssignment",
    "ManualCopyMode",
    "RadioManualGroupPlan",
    "RadioSourceUnit",
    "RadioStagedCopyPlan",
    "RadioTargetAssignment",
    "RadioTargetConflictKind",
    "RadioTargetOperation",
    "RadioTargetTriple",
]
