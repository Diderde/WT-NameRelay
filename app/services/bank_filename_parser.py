from __future__ import annotations

import os
import re
from pathlib import Path

from app.models import BankFile, BankFileRole

_ASSETS = re.compile(r"^_crew_dialogs_(common|ground)_(.+)\.assets\.bank$")
_MAIN = re.compile(r"^_crew_dialogs_(common|ground)_(.+)\.bank$")


class BankFilenameParser:
    """Strictly parse Bank names, prioritising the longer assets suffix."""

    def parse(self, value: str | Path) -> BankFile:
        path = Path(os.path.abspath(os.fspath(value)))
        match = _ASSETS.match(path.name)
        if match:
            return BankFile(path, match[1], match[2], BankFileRole.ASSETS)
        match = _MAIN.match(path.name)
        if match:
            return BankFile(path, match[1], match[2], BankFileRole.MAIN)
        return BankFile(path, reason="不支持的 Bank 文件名")
