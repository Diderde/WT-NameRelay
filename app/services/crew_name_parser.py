from __future__ import annotations

import os
from pathlib import Path

from app.models import RecognitionState, SourceFile

from .crew_name_repository import CrewNameRepository


class CrewNameParser:
    """Turn an actual source-file path into an exact recognition record."""

    def __init__(self, repository: CrewNameRepository) -> None:
        self._repository = repository

    def parse(self, file_path: str | Path) -> SourceFile:
        absolute_path = Path(os.path.abspath(os.fspath(file_path)))
        suffix = absolute_path.suffix
        normalized_path = os.path.normcase(os.fspath(absolute_path))
        if not suffix:
            return SourceFile(
                path=absolute_path,
                normalized_path=normalized_path,
                file_name=absolute_path.name,
                stem=absolute_path.name,
                suffix="",
                state=RecognitionState.NO_EXTENSION,
                reason="文件没有扩展名，无法识别。",
            )

        stem = absolute_path.stem
        group = self._repository.lookup(stem)
        if group is None:
            return SourceFile(
                path=absolute_path,
                normalized_path=normalized_path,
                file_name=absolute_path.name,
                stem=stem,
                suffix=suffix,
                state=RecognitionState.UNKNOWN_NAME,
                reason="文件名不在当前模块的名称库中。",
            )
        return SourceFile(
            path=absolute_path,
            normalized_path=normalized_path,
            file_name=absolute_path.name,
            stem=stem,
            suffix=suffix,
            state=RecognitionState.RECOGNIZED,
            group_base=group.base_name,
            group_key=group.group_key,
        )
