from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from .models import (
    AudioClip,
    BlankClip,
    ExportSettings,
    TimelineClipKind,
    TimelineClipSnapshot,
    TimelineItem,
    TimelineSnapshot,
)

_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True, slots=True)
class MatrixWriteResult:
    target: Path
    succeeded: bool
    overwritten: bool = False
    error: str = ""


class FfmpegLocator:
    @staticmethod
    def bin_dir() -> Path:
        return Path(__file__).resolve().parents[1] / "resources" / "ffmpeg" / "bin"

    @classmethod
    def executable(cls, name: str) -> Path:
        path = cls.bin_dir() / f"{name}.exe"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    @classmethod
    def probe_duration(cls, path: Path) -> float:
        result = subprocess.run(
            [
                str(cls.executable("ffprobe")),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FLAGS,
            check=True,
        )
        return float(json.loads(result.stdout)["format"]["duration"])

    @classmethod
    def probe_duration_ms(cls, path: Path) -> int:
        return max(1, round(cls.probe_duration(path) * 1000))


def snapshot_from_items(
    items: tuple[TimelineItem, ...],
    sample_rate: int,
    channels: int,
) -> TimelineSnapshot:
    """Compatibility bridge for callers outside the audio page."""
    clips: list[TimelineClipSnapshot] = []
    for item in items:
        if isinstance(item, AudioClip):
            clips.append(
                TimelineClipSnapshot(
                    item.clip_id,
                    TimelineClipKind.AUDIO,
                    item.source_path,
                    item.trim_start_ms,
                    item.effective_end_ms,
                    item.duration_ms,
                )
            )
        elif isinstance(item, BlankClip):
            clips.append(
                TimelineClipSnapshot(
                    item.clip_id,
                    TimelineClipKind.BLANK,
                    None,
                    0,
                    item.duration_ms,
                    item.duration_ms,
                )
            )
    return TimelineSnapshot(tuple(clips), sum(clip.duration_ms for clip in clips), 0, sample_rate, channels)


class AudioExportService(QObject):
    progress = Signal(str, int, str)
    finished = Signal(bool, str, object)

    def __init__(
        self,
        source: TimelineSnapshot | tuple[TimelineItem, ...],
        settings: ExportSettings,
        target: Path,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.snapshot = (
            source
            if isinstance(source, TimelineSnapshot)
            else snapshot_from_items(source, settings.sample_rate, settings.channels)
        )
        self.target = target
        self.cancel_event = cancel_event
        self._process: subprocess.Popen[str] | None = None

    def _filter(self) -> tuple[list[str], str]:
        inputs: list[str] = []
        filters: list[str] = []
        labels: list[str] = []
        layout = "mono" if self.settings.channels == 1 else "stereo"
        for index, clip in enumerate(self.snapshot.clips):
            if clip.kind is TimelineClipKind.AUDIO:
                if clip.source_path is None or not clip.source_path.is_file():
                    raise FileNotFoundError(clip.source_path)
                inputs += ["-i", str(clip.source_path)]
                start = clip.source_start_ms / 1000
                end = clip.source_end_ms / 1000
                filters.append(
                    f"[{index}:a]atrim=start={start:.3f}:end={end:.3f},"
                    f"asetpts=PTS-STARTPTS[a{index}]"
                )
            else:
                inputs += [
                    "-f",
                    "lavfi",
                    "-t",
                    f"{clip.duration_ms / 1000:.3f}",
                    "-i",
                    f"anullsrc=r={self.settings.sample_rate}:cl={layout}",
                ]
                filters.append(f"[{index}:a]asetpts=PTS-STARTPTS[a{index}]")
            labels.append(f"[a{index}]")
        final = (
            f"concat=n={len(labels)}:v=0:a=1,"
            f"aresample={self.settings.sample_rate},aformat=channel_layouts={layout}"
        )
        if self.settings.normalize_mode == "loudness":
            final += f",loudnorm=I={self.settings.normalize_target}:TP=-1.0:LRA=11"
        elif self.settings.normalize_mode == "peak":
            final += f",volume={self.settings.normalize_target}dB"
        return inputs, ";".join(filters) + ";" + "".join(labels) + final + "[out]"

    @staticmethod
    def _consume_stderr(
        stream,
        messages: queue.Queue[str | None],
    ) -> None:
        try:
            for line in stream:
                messages.put(line)
        finally:
            messages.put(None)

    def _terminate_process(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        deadline = time.monotonic() + 2.0
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if process.poll() is None:
            process.kill()

    def _run_ffmpeg(self, target: Path) -> None:
        inputs, filter_complex = self._filter()
        codec = {
            "16-bit PCM": "pcm_s16le",
            "24-bit PCM": "pcm_s24le",
            "32-bit Float": "pcm_f32le",
        }[self.settings.bit_depth]
        command = [
            str(FfmpegLocator.executable("ffmpeg")),
            "-y",
            "-hide_banner",
            "-nostdin",
            "-progress",
            "pipe:2",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-c:a",
            codec,
            "-threads",
            str(self.settings.worker_threads),
            str(target),
        ]
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FLAGS,
            bufsize=1,
        )
        assert self._process.stderr is not None
        messages: queue.Queue[str | None] = queue.Queue()
        reader = threading.Thread(
            target=self._consume_stderr,
            args=(self._process.stderr, messages),
            daemon=True,
        )
        reader.start()
        stderr_done = False
        while self._process.poll() is None or not stderr_done:
            if self.cancel_event.is_set():
                self._terminate_process()
            try:
                line = messages.get(timeout=0.04)
            except queue.Empty:
                continue
            if line is None:
                stderr_done = True
            elif line.startswith(("out_time_ms=", "out_time_us=")):
                raw = line.partition("=")[2].strip()
                try:
                    processed_ms = int(raw) // 1000
                    total_ms = max(1, self.snapshot.total_duration_ms)
                    percent = 35 + min(50, round(processed_ms / total_ms * 50))
                except ValueError:
                    percent = 70
                self.progress.emit("正在写入", percent, self.target.name)
        reader.join(timeout=0.2)
        self._process.stderr.close()
        code = self._process.returncode
        if self.cancel_event.is_set():
            raise RuntimeError("任务已取消")
        if code:
            raise RuntimeError(f"FFmpeg 导出失败（退出码 {code}）")

    @Slot()
    def run(self) -> None:
        temporary: Path | None = None
        try:
            if not self.snapshot.clips:
                raise ValueError("音轨为空")
            self.progress.emit("正在准备", 5, self.target.name)
            self.target.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(
                prefix=f".{self.target.name}.",
                suffix=".part.wav",
                dir=self.target.parent,
            )
            os.close(fd)
            temporary = Path(name)
            self.progress.emit("正在解码、裁切与拼接", 35, self.target.name)
            self._run_ffmpeg(temporary)
            self.progress.emit("正在验证", 90, self.target.name)
            actual_ms = FfmpegLocator.probe_duration_ms(temporary)
            tolerance_ms = max(5, round(1000 / max(1, self.settings.sample_rate)) + 1)
            if abs(actual_ms - self.snapshot.total_duration_ms) > tolerance_ms:
                raise RuntimeError(
                    "输出时长验证失败："
                    f"预计 {self.snapshot.total_duration_ms} ms，实际 {actual_ms} ms"
                )
            os.replace(temporary, self.target)
            temporary = None
            self.progress.emit("已完成", 100, self.target.name)
            self.finished.emit(True, "导出成功", self.target)
        except Exception as error:
            self.finished.emit(False, str(error), None)
        finally:
            self._terminate_process()
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class AudioPreviewService(AudioExportService):
    """Render one immutable timeline snapshot into a temporary WAV preview."""


class AudioMatrixExportService(AudioExportService):
    """Render once, then atomically publish one WAV to three JSON targets."""

    target_finished = Signal(object)

    def __init__(
        self,
        source: TimelineSnapshot | tuple[TimelineItem, ...],
        settings: ExportSettings,
        targets: tuple[Path, Path, Path],
        cancel_event: threading.Event,
    ) -> None:
        if len(targets) != 3:
            raise ValueError("平均分配导出必须包含三个目标")
        super().__init__(source, settings, targets[0], cancel_event)
        self.targets = targets

    def _verify(self, rendered: Path) -> None:
        actual_ms = FfmpegLocator.probe_duration_ms(rendered)
        tolerance_ms = max(5, round(1000 / max(1, self.settings.sample_rate)) + 1)
        if abs(actual_ms - self.snapshot.total_duration_ms) > tolerance_ms:
            raise RuntimeError(
                "输出时长验证失败："
                f"预计 {self.snapshot.total_duration_ms} ms，实际 {actual_ms} ms"
            )

    @Slot()
    def run(self) -> None:
        results: list[MatrixWriteResult] = []
        try:
            if not self.snapshot.clips:
                raise ValueError("音轨为空")
            with tempfile.TemporaryDirectory(prefix="WT-NameRelay-audio-matrix-") as raw:
                rendered = Path(raw) / "rendered.wav"
                self.progress.emit("正在渲染一次音轨", 5, rendered.name)
                self._run_ffmpeg(rendered)
                if self.cancel_event.is_set():
                    raise RuntimeError("任务已取消")
                self.progress.emit("正在验证渲染结果", 70, rendered.name)
                self._verify(rendered)

                for index, target in enumerate(self.targets):
                    if self.cancel_event.is_set():
                        raise RuntimeError("任务已取消")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    existed = target.exists()
                    temporary: Path | None = None
                    descriptor: int | None = None
                    try:
                        descriptor, name = tempfile.mkstemp(
                            prefix=f".{target.name}.", suffix=".part", dir=target.parent
                        )
                        temporary = Path(name)
                        with rendered.open("rb") as source_stream, os.fdopen(descriptor, "wb") as target_stream:
                            descriptor = None
                            shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
                        os.replace(temporary, target)
                        temporary = None
                        result = MatrixWriteResult(target, True, existed)
                    except (OSError, PermissionError) as error:
                        result = MatrixWriteResult(target, False, existed, str(error))
                    finally:
                        if descriptor is not None:
                            os.close(descriptor)
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
                    results.append(result)
                    self.target_finished.emit(result)
                    self.progress.emit(
                        f"正在写入第 {index + 1}/3 个目标",
                        75 + round((index + 1) / 3 * 25),
                        target.name,
                    )

            failures = [result for result in results if not result.succeeded]
            if failures:
                details = "；".join(f"{item.target.name}: {item.error}" for item in failures)
                self.finished.emit(False, f"平均分配导出部分失败：{details}", tuple(results))
            else:
                self.finished.emit(True, "平均分配导出成功：一次渲染，三个目标已写入", tuple(results))
        except Exception as error:
            self.finished.emit(False, str(error), tuple(results))
        finally:
            self._terminate_process()
