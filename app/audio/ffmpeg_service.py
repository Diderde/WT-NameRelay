from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.paths import temp_dir

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

# 输出格式档案：编码参数（含质量项）、封装器与扩展名。
# 全部为随包 LGPL 构建内已启用的编码器，见 FFMPEG_BUILD_INFO.md。
_FORMAT_PROFILES: dict[str, tuple[str, str, str]] = {
    "wav": "pcm",
    "mp3": "libmp3lame",
    "flac": "flac",
    "opus": "libopus",
    "m4a": "aac",
}
_MUXERS = {"wav": "wav", "mp3": "mp3", "flac": "flac", "opus": "opus", "m4a": "ipod"}

# 线性振幅阈值（这些 ffmpeg 选项不接受 dB 后缀，需换算）。
_SILENCE_THRESHOLD_LINEAR = 0.0178  # 约 -35 dB


def format_codec_args(settings: ExportSettings) -> list[str]:
    """按导出格式返回编码器与质量参数（质量为空时使用各格式默认档）。"""
    fmt = settings.output_format if settings.output_format in _FORMAT_PROFILES else "wav"
    if fmt == "wav":
        codec = {
            "16-bit PCM": "pcm_s16le",
            "24-bit PCM": "pcm_s24le",
            "32-bit Float": "pcm_f32le",
        }[settings.bit_depth]
        return ["-c:a", codec]
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", settings.quality or "192k"]
    if fmt == "flac":
        return ["-c:a", "flac", "-compression_level", settings.quality or "5"]
    if fmt == "opus":
        return ["-c:a", "libopus", "-b:a", settings.quality or "96k"]
    return ["-c:a", "aac", "-b:a", settings.quality or "192k"]


def output_extension(settings: ExportSettings) -> str:
    fmt = settings.output_format if settings.output_format in _FORMAT_PROFILES else "wav"
    return fmt


def loudness_cache_key(snapshot: TimelineSnapshot, settings: ExportSettings) -> tuple:
    """两遍 loudnorm 测量值的缓存键：影响 pre-loudnorm 链与响度目标的全部字段。"""
    return (
        snapshot.version,
        snapshot.total_duration_ms,
        settings.sample_rate,
        settings.channels,
        settings.normalize_target,
        settings.fade_ms,
        settings.trim_silence,
        settings.denoise,
        settings.denoise_strength,
        settings.declick,
        settings.deesser,
        settings.voice_preset,
    )


def parse_loudnorm_json(stderr: str) -> dict | None:
    """从 loudnorm print_format=json 的输出中解析测量值。"""
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.DOTALL)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if any(key not in data for key in required):
        return None
    return data


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
        try:
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
                timeout=120,
            )
        except subprocess.TimeoutExpired as error:
            # 损坏/异常媒体可能让 ffprobe 长时间无响应，超时转为可见失败。
            raise RuntimeError(f"音频探测超时：{path}") from error
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
        measurement_cache: dict | None = None,
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
        # 页面层共享的两遍 loudnorm 测量缓存：试听与正式导出复用同一份
        # 测量值，保证"试听=导出"，也避免重复分析。键见 loudness_cache_key。
        self.measurement_cache = measurement_cache
        self._process: subprocess.Popen[str] | None = None

    def _filter(
        self,
        measurement: dict | None = None,
        loudness_probe: bool = False,
    ) -> tuple[list[str], str]:
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
                segment = (
                    f"[{index}:a]atrim=start={start:.3f}:end={end:.3f},"
                    f"asetpts=PTS-STARTPTS"
                )
                fade = self._clip_fade_args(clip.duration_ms)
                if fade:
                    segment += f",{fade}"
                filters.append(segment + f"[a{index}]")
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
        post = self._chain_post_concat(measurement, loudness_probe)
        if post:
            final += "," + post
        return inputs, ";".join(filters) + ";" + "".join(labels) + final + "[out]"

    def _clip_fade_args(self, duration_ms: int) -> str:
        """片段级淡入淡出；时长不足时收缩到三分之一，避免淡入淡出交叠。"""
        fade_ms = min(self.settings.fade_ms, duration_ms // 3) if duration_ms > 0 else 0
        if fade_ms <= 0:
            return ""
        fade_s = fade_ms / 1000
        out_start = max(0.0, duration_ms / 1000 - fade_s)
        return (
            f"afade=t=in:st=0:d={fade_s:.3f},"
            f"afade=t=out:st={out_start:.3f}:d={fade_s:.3f}"
        )

    def _chain_post_concat(self, measurement: dict | None, loudness_probe: bool) -> str:
        """拼接后的统一处理链，顺序：修饰 → 修复/降噪 → EQ/动态 → 响度。

        两遍 loudnorm 的分析遍（loudness_probe=True）与施用遍共用本链，
        保证测量对象与实际渲染对象一致。
        """
        s = self.settings
        parts: list[str] = []
        if s.trim_silence == "edges":
            threshold = _SILENCE_THRESHOLD_LINEAR
            parts.append(
                f"silenceremove=start_periods=1:start_threshold={threshold},areverse,"
                f"silenceremove=start_periods=1:start_threshold={threshold},areverse"
            )
        if s.voice_preset == "low_cut":
            parts.append("highpass=f=80")
        elif s.voice_preset == "voice":
            parts.append("highpass=f=80,equalizer=f=3200:width_type=q:width=1.0:g=2.5")
        elif s.voice_preset == "broadcast":
            # acompressor/alimiter 的阈值均为线性值：0.126≈-18dB，0.84≈-1.5dB；
            # alimiter latency=true 补偿 lookahead 延迟，输出时长保持不变。
            parts.append(
                "highpass=f=80,"
                "acompressor=threshold=0.126:ratio=3:attack=10:release=160:makeup=2,"
                "alimiter=limit=0.84:latency=true"
            )
        if s.denoise == "afftdn":
            parts.append(f"afftdn=nr={max(1, min(48, s.denoise_strength))}:nf=-25")
        elif s.denoise == "anlmdn":
            parts.append("anlmdn=s=0.0005")
        if s.declick:
            parts.append("adeclick")
        if s.deesser:
            parts.append("deesser=i=0.4:m=0.3")
        if s.normalize_mode == "loudness":
            if loudness_probe:
                parts.append(
                    f"loudnorm=I={s.normalize_target:g}:TP=-1.0:LRA=11:print_format=json"
                )
            elif measurement is not None:
                parts.append(
                    f"loudnorm=I={s.normalize_target:g}:TP=-1.0:LRA=11:"
                    f"measured_I={measurement['input_i']}:measured_TP={measurement['input_tp']}:"
                    f"measured_LRA={measurement['input_lra']}:measured_thresh={measurement['input_thresh']}:"
                    f"offset={measurement['target_offset']}:linear=true"
                )
            else:
                parts.append(f"loudnorm=I={s.normalize_target:g}:TP=-1.0:LRA=11")
        elif s.normalize_mode == "speech":
            parts.append("speechnorm=e=12:r=0.0005")
        elif s.normalize_mode == "peak":
            parts.append(f"volume={s.normalize_target}dB")
        if s.gain_db:
            # 整体增益在归一化之后追加：语义为"在归一化结果上整体加减"。
            parts.append(f"volume={s.gain_db:g}dB")
        return ",".join(parts)

    def _resolve_measurement(self) -> dict | None:
        """两遍 loudnorm 的测量值：优先读共享缓存，否则跑分析遍（可取消）。"""
        if self.settings.normalize_mode != "loudness":
            return None
        key = loudness_cache_key(self.snapshot, self.settings)
        if self.measurement_cache is not None and key in self.measurement_cache:
            return self.measurement_cache[key]
        self.progress.emit("正在分析响度", 20, self.target.name)
        measurement = self._analyze_loudness()
        if self.measurement_cache is not None:
            self.measurement_cache[key] = measurement
        return measurement

    def _analyze_loudness(self) -> dict:
        """第一遍：以与正式渲染相同的 pre-loudnorm 链测量响度（输出到空设备）。"""
        inputs, filter_complex = self._filter(loudness_probe=True)
        command = [
            str(FfmpegLocator.executable("ffmpeg")),
            "-nostdin",
            "-hide_banner",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-f",
            "null",
            "NUL",
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_FLAGS,
        )
        assert process.stderr is not None
        try:
            while True:
                try:
                    _, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if self.cancel_event.is_set():
                        # 取消必须即时生效，不等分析遍自然结束。
                        process.terminate()
                        process.wait(timeout=5)
                        raise RuntimeError("任务已取消")
                    continue
        except BaseException:
            process.terminate()
            process.wait(timeout=5)
            raise
        if self.cancel_event.is_set():
            raise RuntimeError("任务已取消")
        if process.returncode != 0:
            raise RuntimeError(f"响度分析失败（退出码 {process.returncode}）")
        measurement = parse_loudnorm_json(stderr)
        if measurement is None:
            raise RuntimeError("响度分析输出解析失败")
        return measurement

    def _validate_duration(self, actual_ms: int) -> None:
        """输出时长校验；去首尾静音会缩短时长，仅要求非负且不超过上限。"""
        expected = self.snapshot.total_duration_ms
        tolerance = max(5, round(1000 / max(1, self.settings.sample_rate)) + 1)
        if self.settings.voice_preset == "broadcast":
            tolerance += 10
        if self.settings.output_format in ("opus", "m4a"):
            # Opus 预跳与 AAC 帧对齐会让首帧填零，实测约 +5~7 ms。
            tolerance += 15
        if self.settings.trim_silence == "edges":
            if not 0 < actual_ms <= expected + tolerance:
                raise RuntimeError(
                    f"输出时长异常：应不超过 {expected} ms，实际 {actual_ms} ms"
                )
            return
        if abs(actual_ms - expected) > tolerance:
            raise RuntimeError(
                f"输出时长验证失败：预计 {expected} ms，实际 {actual_ms} ms"
            )

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
        measurement = self._resolve_measurement()
        self.progress.emit("正在解码、裁切与拼接", 30, self.target.name)
        inputs, filter_complex = self._filter(measurement=measurement)
        codec_args = format_codec_args(self.settings)
        muxer = _MUXERS[self.settings.output_format if self.settings.output_format in _MUXERS else "wav"]
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
            *codec_args,
            "-threads",
            str(self.settings.worker_threads),
            "-f",
            muxer,
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
                    # ffmpeg 的 out_time_ms/out_time_us 实际均为微秒（历史怪癖），
                    # //1000 恰好换算为毫秒；两个键都监听以兼容不同构建。
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
                suffix=f".part{output_extension(self.settings)}",
                dir=self.target.parent,
            )
            os.close(fd)
            temporary = Path(name)
            self._run_ffmpeg(temporary)
            self.progress.emit("正在验证", 90, self.target.name)
            self._validate_duration(FfmpegLocator.probe_duration_ms(temporary))
            temporary.replace(self.target)
            temporary = None
            self.progress.emit("已完成", 100, self.target.name)
            self.finished.emit(True, "导出成功", self.target)
        except Exception as error:  # noqa: BLE001  # 工作线程边界：统一转为失败信号  # 工作线程边界：统一转为失败信号
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
        # 平均分配"渲染一次、字节复制三份"的语义绑定 WAV，忽略格式选择。
        super().__init__(
            source,
            replace(settings, output_format="wav", quality=""),
            targets[0],
            cancel_event,
        )
        self.targets = targets

    def _verify(self, rendered: Path) -> None:
        self._validate_duration(FfmpegLocator.probe_duration_ms(rendered))

    @Slot()
    def run(self) -> None:
        results: list[MatrixWriteResult] = []
        try:
            if not self.snapshot.clips:
                raise ValueError("音轨为空")
            with tempfile.TemporaryDirectory(prefix="WT-NameRelay-audio-matrix-", dir=str(temp_dir())) as raw:
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
                        temporary.replace(target)
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
        except Exception as error:  # noqa: BLE001  # 工作线程边界：统一转为失败信号  # 工作线程边界：统一转为失败信号
            self.finished.emit(False, str(error), tuple(results))
        finally:
            self._terminate_process()
