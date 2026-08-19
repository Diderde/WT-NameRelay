"""Repeatable offscreen benchmark for the PyQtGraph timeline."""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.audio.models import TimelineModel, WaveformEnvelope
from app.widgets.pyqtgraph_timeline import PyQtGraphTimeline


def make_silence(path: Path, duration_ms: int = 4_000) -> Path:
    rate = 48_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\0\0" * round(duration_ms * rate / 1000))
    return path


def envelope() -> WaveformEnvelope:
    base = tuple(
        (-abs(((index % 97) / 96) - 0.5), abs(((index % 83) / 82) - 0.5))
        for index in range(16_384)
    )
    levels = [base]
    while len(levels[-1]) > 64:
        previous = levels[-1]
        levels.append(
            tuple(
                (
                    min(value[0] for value in previous[index : index + 4]),
                    max(value[1] for value in previous[index : index + 4]),
                )
                for index in range(0, len(previous), 4)
            )
        )
    return WaveformEnvelope(tuple(levels), 8_000, 32_000)


def run_case(app: QApplication, count: int, source: Path) -> dict[str, float | int]:
    model = TimelineModel()
    cached = envelope()
    for _ in range(count):
        clip = model.add_audio(source, 4.0)
        model.set_waveform(clip.clip_id, cached)
    timeline = PyQtGraphTimeline()
    timeline.resize(1100, 280)
    timeline.show()
    tracemalloc.start()
    started = time.perf_counter()
    timeline.set_timeline(model)
    app.processEvents()
    initial_ms = (time.perf_counter() - started) * 1000
    frames: list[float] = []
    for index in range(90):
        ratio = (index % 30) / 29
        pps = 2 * ((1000 / 2) ** ratio)
        tick = time.perf_counter()
        timeline.set_pixels_per_second(pps)
        app.processEvents()
        frames.append((time.perf_counter() - tick) * 1000)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timeline.close()
    app.processEvents()
    return {
        "clip_count": count,
        "duration_ms": model.duration_ms,
        "initial_render_ms": round(initial_ms, 3),
        "zoom_frame_average_ms": round(statistics.mean(frames), 3),
        "zoom_frame_max_ms": round(max(frames), 3),
        "tracemalloc_peak_mib": round(peak / 1024 / 1024, 3),
    }


def main() -> int:
    app = QApplication.instance() or QApplication([])
    source = make_silence(Path(tempfile.gettempdir()) / "wt_timeline_benchmark.wav")
    report = {
        "backend": "PyQtGraph 0.13.7",
        "numpy": "1.26.4",
        "maximum_pixels_per_second": 1000,
        "cases": [run_case(app, count, source) for count in (1, 10, 30)],
    }
    output = ROOT / "reports" / "timeline_performance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
