"""Visible Windows-only harness for manually checking the audio page."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from app.pages.audio_processing_page import AudioProcessingPage
from app.styles.theme import apply_theme
from tools.timeline_pyqtgraph_prototype import make_test_wav


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    page = AudioProcessingPage()
    page.setWindowTitle("WT-Tool 音轨组件验证")
    page.resize(1280, 900)
    page.show()
    page._add_audio_paths([str(make_test_wav())])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
