"""Standalone PyQtGraph timeline prototype used before formal integration."""
from __future__ import annotations

import math
import os
import sys
import tempfile
import threading
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.audio import AudioPreviewService, ExportSettings, FfmpegLocator, WaveformWorker
from app.audio.models import TimelineModel
from app.widgets.pyqtgraph_timeline import PyQtGraphTimeline


def make_test_wav() -> Path:
    path = Path(tempfile.gettempdir()) / "wt_name_relay_timeline_prototype.wav"
    rate = 48_000
    frames = bytearray()
    for index in range(rate * 4):
        value = round(math.sin(index * 2 * math.pi * 440 / rate) * 12_000)
        frames.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(frames)
    return path


def main() -> int:
    app = QApplication(sys.argv)
    widget = PyQtGraphTimeline()
    widget.resize(1000, 260)
    model = TimelineModel()
    source = make_test_wav()
    clip = model.add_audio(source, 4.0)
    decoded: list[tuple] = []
    worker = WaveformWorker(clip.clip_id, source)
    worker.finished.connect(lambda *result: decoded.append(result))
    worker.run()
    if decoded and decoded[0][2] is not None:
        model.set_waveform(clip.clip_id, decoded[0][2])
    widget.set_timeline(model)
    def commit(clip_id: str, start_ms: int, end_ms: int) -> None:
        model.trim_ms(clip_id, start_ms, end_ms)
        widget.set_timeline(model)
    widget.trim_committed.connect(commit)
    widget.show()
    if "--verify" in sys.argv:
        model.trim_ms(clip.clip_id, 425, 3120)
        snapshot = model.snapshot()
        preview = Path(tempfile.gettempdir()) / "wt_name_relay_timeline_prototype_preview.wav"
        results: list[tuple] = []
        renderer = AudioPreviewService(snapshot, ExportSettings(), preview, threading.Event())
        renderer.finished.connect(lambda *result: results.append(result))
        renderer.run()
        actual_ms = FfmpegLocator.probe_duration_ms(preview) if preview.is_file() else 0
        print(
            "prototype",
            {
                "waveform": bool(decoded and decoded[0][2]),
                "trim_start_ms": snapshot.clips[0].source_start_ms,
                "trim_end_ms": snapshot.clips[0].source_end_ms,
                "expected_preview_ms": snapshot.total_duration_ms,
                "actual_preview_ms": actual_ms,
                "left_fixed_zoom": widget.visible_left_seconds == 0,
                "seconds_unit": widget.axis.unit_text == "s",
            },
        )
        preview.unlink(missing_ok=True)
        return 0 if results and results[0][0] and abs(actual_ms - snapshot.total_duration_ms) <= 5 else 1
    if os.environ.get("WT_TIMELINE_PROTOTYPE_AUTOCLOSE"):
        QTimer.singleShot(100, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
