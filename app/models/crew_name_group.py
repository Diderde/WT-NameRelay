from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CrewGroupType(str, Enum):
    """Supported name-suffix forms shared by every copy module."""

    SINGLE = "single"
    DOUBLE = "double"
    MIXED = "mixed"
    V_SUFFIX = "v_suffix"
    NUMERIC_SUFFIX = "numeric_suffix"
    MATRIX_SUFFIX = "matrix_suffix"
    V_MATRIX_SUFFIX = "v_matrix_suffix"


@dataclass(frozen=True, slots=True)
class CrewNameGroup:
    """Names that can be completed from one recognised file stem."""

    group_key: str
    base_name: str
    group_type: CrewGroupType
    names: tuple[str, ...]
