"""Immutable domain models used by the crew manual-copy workflow."""

from .average_distribution import (
    ConflictKind,
    DistributionPlan,
    SourceCandidate,
    TargetBucket,
    TargetOperation,
)
from .bank_models import BankCountryAssignment, BankCountryGroup, BankFile, BankFileRole
from .completion_group import AutoCompletionAnalysis, CompletionGroup
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
from .directory_scan_result import AutoScanState, DirectoryScanResult, ScannedDirectory
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
from .source_file import RecognitionState, SourceFile

__all__ = [
    "AutoCompletionAnalysis",
    "AutoScanState",
    "BankCountryAssignment",
    "BankCountryGroup",
    "BankFile",
    "BankFileRole",
    "CompletionGroup",
    "ConflictKind",
    "ConflictPolicy",
    "CopyBatchResult",
    "CopyPlan",
    "CopyResult",
    "CopyResultStatus",
    "CopyTask",
    "CrewGroupPlan",
    "CrewGroupType",
    "CrewNameGroup",
    "DirectoryScanResult",
    "DistributionPlan",
    "ManualBatchState",
    "ManualCopyMode",
    "RadioManualGroupPlan",
    "RadioSourceUnit",
    "RadioStagedCopyPlan",
    "RadioTargetAssignment",
    "RadioTargetConflictKind",
    "RadioTargetOperation",
    "RadioTargetTriple",
    "RecognitionState",
    "ScannedDirectory",
    "SourceCandidate",
    "SourceFile",
    "TargetAssignment",
    "TargetBucket",
    "TargetOperation",
]
