# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""人声/背景音分离服务：模型注册表 + 权重下载 + 批量队列 + MSST 推理调度。

目标场景：**动漫/影视片段**的对白与背景音（BGM + 效果音）分离，其次音乐素材。

引擎与模型策略（许可证均逐仓核实，2026-10-01）：
- 推理引擎 = 上游 `ZFTurbo/Music-Source-Separation-Training`（MIT，独立检出
  `TTS model/MSST`，subprocess 调用，参照 GPT-SoVITS 的隔离先例）；
  MSST-WebUI（SUC-DriverOld）为 AGPL-3.0，其代码一律不引用、不拷贝；
- 片段对白分离 = BandIt v2 DnR（对白/效果音/音乐三轨，CC-BY-SA-4.0，Zenodo
  官方权重）：DnR 数据集不含日语，故无日语专用权重；普通话 cmn 与多语言
  multi 可用，日语原声效果未验证；架构 BandIt/BandIt v2 均 Apache-2.0；
- 音乐素材人声/伴奏 = `AEmotionStudio/roformer-models`（MIT）社区检查点
  （viperx / unwa / becruily，动漫歌社区主力训练者）；
- CC-BY-NC 系（BandIt v1 权重、Sucial 三件套）一律不进默认清单：公共 GPL
  工具不得替用户接受禁商用条款；支持自定义模型目录，由用户自担许可。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from app.audio.ffmpeg_service import BACKGROUND_FLAGS
from app.i18n import tr
from app.paths import PROJECT_ROOT

LOGGER = logging.getLogger("wt_name_relay")

# 权重/上游目录曾写成相对路径，进程工作目录一变（快捷方式、
# 打包启动器、从别处起脚本）模型目录就整体错位到 CWD 下——锚到项目根
SEPARATION_ROOT = PROJECT_ROOT / "TTS model" / "MSST"
UPSTREAM_REPO = "https://github.com/ZFTurbo/Music-Source-Separation-Training"
UPSTREAM_RAW = "https://raw.githubusercontent.com/ZFTurbo/Music-Source-Separation-Training/main"
#: HF 下载走镜像，失败回退官方域
HF_MIRROR = "https://hf-mirror.com"
HF_PRIMARY = "https://huggingface.co"
#: AEmotionStudio/roformer-models（MIT）：音乐模型仓内 config.yaml + model.safetensors
SONG_MODEL_REPO = "AEmotionStudio/roformer-models"
#: BandIt v2 DnR（CC-BY-SA-4.0）：Zenodo 官方权重 + MSST 仓内 config
DNR_ZENODO_RECORD = "https://zenodo.org/records/12701995/files"
#: 本机加速器的 CONNECT 隧道：GitHub 系直连被重置时的显式代理兜底
LOCAL_GITHUB_PROXY = "http://127.0.0.1:26561"

#: 单素材推理超时（秒）：长素材 + TTA 三倍耗时留足余量，批量按素材数放大
_INFERENCE_TIMEOUT_S = 3600
#: 结果缓存标记文件名（记录源 mtime_ns + size，同源同模型不重跑）
_STAMP_NAME = "separation_source_stamp.json"
#: 分离产物里算"音频"的后缀（MSST 输出 wav 为主，保守多收几种）
_AUDIO_EXTS = (".wav", ".flac", ".mp3", ".ogg", ".m4a", ".opus")
#: 人声/对白轨的文件名标记：dialogue（DnR 三轨）/ vocals（音乐两轨）都命中
_VOCAL_MARKERS = ("dialogue", "vocal")
#: 联动导出的文件名后缀：<原名>-vocal.<ext>
VOCAL_SUFFIX = "-vocal"


class _CancelledError(RuntimeError):
    """用户取消正在跑的推理（内部信号，不外泄到任务详情）。"""


@dataclass(frozen=True)
class ModelSpec:
    """一个可下载的分离模型：元数据 + 许可证 + 分轨下载地址。

    标题与备注走 i18n 键（title_key/note_key）；变体里专有名词保留原文
    （variant），普通词走 variant_key。
    """

    key: str
    title_key: str
    variant: str
    variant_key: str  # 普通词变体的 i18n 键；空串表示用 variant 原文
    note_key: str
    license: str
    source: str  # 界面展示用出处
    model_type: str  # MSST --model_type
    #: (config, weights) 各自的候选下载地址，依次尝试
    config_urls: tuple[str, ...]
    weights_urls: tuple[str, ...]
    stems_hint: tuple[str, ...]  # 展示用；实际以下载到的 config 为准

    def display_title(self) -> str:
        variant = tr(self.variant_key) if self.variant_key else self.variant
        return f"{tr(self.title_key)} · {variant}"

    def display_note(self) -> str:
        return tr(self.note_key)


def _song_spec(key: str, title_key: str, variant: str, note_key: str,
               subdir: str) -> ModelSpec:
    base = f"{SONG_MODEL_REPO}/resolve/main/{subdir}"
    return ModelSpec(
        key=key, title_key=title_key, variant=variant, variant_key="",
        note_key=note_key, license="MIT",
        source=SONG_MODEL_REPO, model_type="mel_band_roformer",
        config_urls=(f"{HF_MIRROR}/{base}/config.yaml",
                     f"{HF_PRIMARY}/{base}/config.yaml"),
        weights_urls=(f"{HF_MIRROR}/{base}/model.safetensors",
                      f"{HF_PRIMARY}/{base}/model.safetensors"),
        stems_hint=("vocals", "instrumental"))


def _dnr_spec(key: str, variant: str, variant_key: str, note_key: str,
              checkpoint: str) -> ModelSpec:
    return ModelSpec(
        key=key, title_key="separate.kind.dnr", variant=variant,
        variant_key=variant_key, note_key=note_key, license="CC-BY-SA-4.0",
        source="Zenodo 12701995 · BandIt v2", model_type="bandit_v2",
        config_urls=(f"{UPSTREAM_RAW}/configs/config_dnr_bandit_v2_mus64.yaml",),
        weights_urls=(f"{DNR_ZENODO_RECORD}/{checkpoint}?download=1",),
        stems_hint=("dialogue", "sfx", "music"))


#: v1 清单：片段对白优先（动漫/影视素材），音乐素材人声/伴奏其后
MODEL_REGISTRY: tuple[ModelSpec, ...] = (
    _dnr_spec("dnr_cmn", "CMN", "separate.variant.cmn",
              "separate.model.note.dnr_cmn", "checkpoint-cmn.ckpt"),
    _dnr_spec("dnr_multi", "Multi", "separate.variant.multi",
              "separate.model.note.dnr_multi", "checkpoint-multi.ckpt"),
    _dnr_spec("dnr_eng", "ENG", "separate.variant.eng",
              "separate.model.note.dnr_eng", "checkpoint-eng.ckpt"),
    _song_spec("vocals_becruily", "separate.kind.vocals", "becruily",
               "separate.model.note.vocals_becruily",
               "mel_band_roformer/vocals_becruily"),
    _song_spec("vocals_unwa_ft", "separate.kind.vocals", "unwa_ft",
               "separate.model.note.vocals_unwa_ft",
               "mel_band_roformer/vocals_unwa_ft"),
    _song_spec("vocals_viperx", "separate.kind.vocals", "viperx",
               "separate.model.note.vocals_viperx",
               "mel_band_roformer/vocals_viperx"),
    _song_spec("dereverb", "separate.kind.dereverb", "",
               "separate.model.note.dereverb",
               "mel_band_roformer/dereverb"),
    _song_spec("denoise", "separate.kind.denoise", "",
               "separate.model.note.denoise",
               "mel_band_roformer/denoise"),
)


def model_by_key(key: str) -> ModelSpec | None:
    for spec in MODEL_REGISTRY:
        if spec.key == key:
            return spec
    return None


def pick_vocal_stem(out_dir: Path) -> Path | None:
    """从一次分离的产出目录里挑"人声/对白"那一轨。

    文件名带 dialogue/vocal 标记的优先（DnR 的 dialogue、音乐模型的
    vocals 都命中）；没有标记时仅在**唯一产物**下兜底——多轨分不清谁
    是人声，瞎挑一轨塞进说话人素材目录比不导出更害人。
    """
    try:
        audio = [p for p in sorted(out_dir.iterdir())
                 if p.is_file() and p.suffix.lower() in _AUDIO_EXTS]
    except OSError:
        return None
    if not audio:
        return None
    for path in audio:
        lowered = path.stem.lower()
        if any(marker in lowered for marker in _VOCAL_MARKERS):
            return path
    return audio[0] if len(audio) == 1 else None


def models_dir(root: Path | None = None) -> Path:
    base = root if root is not None else SEPARATION_ROOT
    return base / "models"


def upstream_dir(root: Path | None = None) -> Path:
    base = root if root is not None else SEPARATION_ROOT
    return base / "Music-Source-Separation-Training"


def resolve_python(configured: str = "") -> str:
    """推理子进程的 Python：优先用户配置，缺省回落系统 python。"""
    return configured or "python"


def model_target(spec: ModelSpec, root: Path | None = None) -> tuple[Path, Path]:
    base = models_dir(root) / spec.key
    return (base / "config.yaml", base / "model.safetensors")


def is_model_ready(spec: ModelSpec, root: Path | None = None) -> bool:
    config, weights = model_target(spec, root)
    return (config.is_file() and config.stat().st_size > 0
            and weights.is_file() and weights.stat().st_size > 1024)


def build_inference_args(spec: ModelSpec, input_folder: Path,
                         store_dir: Path, root: Path | None = None,
                         python_exec: str = "", use_tta: bool = False
                         ) -> list[str]:
    """组装 MSST `inference.py` 的命令行。

    2026-10-02 对照上游 `utils/settings.py::parse_args_inference` 逐参核实：
    权重参数是 `--start_check_point`（此前误传 `--checkpoint_path`，argparse
    直接拒绝）；批量输入只收 `--input_folder`（不存在 `--input_audio`），
    因此多素材合并为一次进程时须先把它们汇聚进同一个暂存目录。
    """
    config, weights = model_target(spec, root)
    args = [resolve_python(python_exec),
            str(upstream_dir(root) / "inference.py"),
            "--model_type", spec.model_type,
            "--config_path", str(config),
            "--start_check_point", str(weights),
            "--input_folder", str(input_folder),
            "--store_dir", str(store_dir)]
    if use_tta:
        args.append("--use_tta")
    return args


def stage_inputs(paths: list[Path], staging: Path) -> dict[str, Path]:
    """把散落的输入汇聚成 `--input_folder` 需要的目录：同名自动加序号。

    优先硬链接（同卷零拷贝），跨卷或文件系统不支持时回落复制。
    返回 暂存文件名 -> 源路径 的映射，输出目录按暂存名回填各任务。
    """
    staging.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, Path] = {}
    used: set[str] = set()
    for src in paths:
        src = Path(src)
        stem = src.stem or "input"
        name, serial = stem, 1
        while name in used:
            serial += 1
            name = f"{stem}_{serial}"
        used.add(name)
        target = staging / f"{name}{src.suffix.lower()}"
        try:
            os.link(src, target)
        except OSError:
            shutil.copy2(src, target)
        mapping[target.stem] = src
    return mapping


@dataclass
class SeparationJob:
    """队列里的一个处理项：一个素材 × 一个模型。"""

    path: Path
    spec: ModelSpec
    job_id: int
    status: str = "waiting"  # waiting | running | done | failed
    detail: str = ""


class SeparationQueue:
    """单工作线程批量队列：保序、可查进度、结果经回调回 GUI 线程。

    线程约定与视频页一致：工作线程只做下载/子进程，完成态经 `on_event`
    回调抛出（页面侧接 Qt 信号再触碰控件）。
    """

    def __init__(self, output_root: Path, python_exec: str = "",
                 root: Path | None = None) -> None:
        self._output_root = Path(output_root)
        self._python_exec = python_exec
        self._root = root
        self._lock = threading.Lock()
        self._queue: deque[SeparationJob] = deque()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._proc: subprocess.Popen | None = None
        self.use_tta = False  # 入队前可置位：暴露上游 --use_tta（三倍耗时换质量）
        #: 联动导出目录（视频裁剪页的说话人素材目录）；None = 不联动，
        #: 分离产物留在 separations 目录。入队前由页面按当前选择设置。
        self.export_dir: Path | None = None
        #: 本轮已联动导出的文件（工作线程追加、页面只读汇总）
        self.exported: list[Path] = []
        self.jobs: list[SeparationJob] = []
        self.on_event = None  # callable(job) | None，工作线程内调用

    # ---------------------------------------------------------------- state

    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue) + (1 if self.is_busy() else 0)

    def _emit(self, job: SeparationJob) -> None:
        if self.on_event is not None:
            try:
                self.on_event(job)
            except Exception:
                LOGGER.exception("separation queue event callback failed")

    # ---------------------------------------------------------------- queue

    def enqueue(self, paths: list[Path], spec: ModelSpec) -> list[SeparationJob]:
        added: list[SeparationJob] = []
        with self._lock:
            base = max((job.job_id for job in self.jobs), default=0)
            for offset, path in enumerate(paths, start=1):
                job = SeparationJob(path=Path(path), spec=spec,
                                    job_id=base + offset)
                self.jobs.append(job)
                self._queue.append(job)
                added.append(job)
            # 取消旗标曾只在"起新线程"时清除：上一轮取消后
            # 线程仍在处理当前项，此时再入队的新任务会撞上残留的取消旗标，
            # 排到队里却永不被执行。入队即清除，取消语义只对已排队项生效
            self._cancel.clear()
            if not self.is_busy():
                self._thread = threading.Thread(
                    target=self._work, name="clip-separate", daemon=True)
                self._thread.start()
        return added

    def cancel_pending(self) -> int:
        """清空未开始的项并终止正在跑的推理进程。返回清掉的条数。"""
        with self._lock:
            dropped = 0
            for job in self._queue:
                job.status = "cancelled"
                dropped += 1
            self._queue.clear()
            proc = self._proc
        self._cancel.set()
        if proc is not None and proc.poll() is None:
            proc.kill()  # 运行中的推理立即终止（RoFormer 一节可达分钟级，不能干等）
        return dropped

    # ---------------------------------------------------------------- worker

    def _work(self) -> None:
        while True:
            with self._lock:
                if not self._queue or self._cancel.is_set():
                    return
                batch = [self._queue.popleft()]
                spec = batch[0].spec
                # 同模型连续任务合并为一次子进程：RoFormer 每次模型加载要
                # 数十秒，逐文件起进程时批量导入是大头浪费
                while (self._queue and self._queue[0].spec is spec):
                    batch.append(self._queue.popleft())
            for job in batch:
                job.status = "running"
                self._emit(job)
            try:
                self._run_batch(batch)
            except _CancelledError:
                for job in batch:
                    if job.status == "running":
                        job.status = "cancelled"
                        job.detail = "cancelled"
                        self._emit(job)
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                for job in batch:
                    if job.status == "running":
                        job.status = "failed"
                        job.detail = str(exc)[-400:]
                        self._emit(job)

    def _run_batch(self, batch: list[SeparationJob]) -> None:
        spec = batch[0].spec
        if not is_model_ready(spec, self._root):
            self._download_model(spec)
        pending: list[SeparationJob] = []
        for job in batch:
            out_dir = self._output_root / spec.key / job.path.stem
            if self._cache_hit(out_dir, job.path):
                job.status = "done"
                job.detail = f"cache: {out_dir}"
                self._emit(job)
                self._export_after_done(job, out_dir, job.path)
                continue
            pending.append(job)
        if not pending:
            return
        staging = self._output_root / "_staging" / f"batch_{time.time_ns()}"
        try:
            mapping = stage_inputs([job.path for job in pending], staging)
            store_dir = self._output_root / spec.key
            store_dir.mkdir(parents=True, exist_ok=True)
            args = build_inference_args(
                spec, staging, store_dir, root=self._root,
                python_exec=self._python_exec, use_tta=self.use_tta)
            self._execute(args, pending, mapping, store_dir)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _execute(self, args: list[str], pending: list[SeparationJob],
                 mapping: dict[str, Path], store_dir: Path) -> None:
        log_path = store_dir / "msst_inference.log"
        with open(log_path, "a", encoding="utf-8", newline="\n") as log:
            log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} "
                      f"batch={len(pending)} tta={self.use_tta} ===\n")
            log.flush()
            proc = subprocess.Popen(
                args, stdout=log, stderr=log, cwd=str(upstream_dir(self._root)),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | BACKGROUND_FLAGS)
            with self._lock:
                self._proc = proc
            deadline = time.monotonic() + _INFERENCE_TIMEOUT_S * len(pending)
            while proc.poll() is None:
                if self._cancel.is_set():
                    proc.kill()
                    proc.wait(timeout=30)  # 收尸防僵尸句柄（kill 后等退即刻回）
                    raise _CancelledError()
                if time.monotonic() > deadline:
                    proc.kill()
                    proc.wait(timeout=30)
                    raise RuntimeError(
                        f"MSST inference timeout ({int(_INFERENCE_TIMEOUT_S * len(pending))}s)")
                time.sleep(1.0)
            with self._lock:
                self._proc = None
        if self._cancel.is_set():
            raise _CancelledError()
        if proc.returncode != 0:
            raise RuntimeError(
                f"MSST inference failed (exit {proc.returncode}): "
                f"{self._log_tail(log_path)}")
        for job in pending:
            stem = Path(self._staged_name(job.path, mapping)).stem
            out_dir = store_dir / stem
            produced = sorted(p.name for p in out_dir.iterdir()) \
                if out_dir.is_dir() else []
            if not produced:
                job.status = "failed"
                job.detail = f"no stems produced: {out_dir}"
            else:
                job.status = "done"
                job.detail = str(out_dir)
                self._write_stamp(out_dir, job.path)
                self._export_after_done(job, out_dir, job.path)
            self._emit(job)

    def _export_after_done(self, job: SeparationJob, out_dir: Path,
                           source: Path) -> None:
        """分离成功后把人声/对白轨联动复制进说话人素材目录（可选）。

        失败不影响任务本身（分离是成功的）：导出失败记进 detail，由界面
        汇总给用户。
        """
        if self.export_dir is None:
            return
        pick = pick_vocal_stem(out_dir)
        if pick is None:
            job.detail = f"{job.detail}\nexport: no vocal stem found"
            return
        target_dir = Path(self.export_dir)
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = self._export_target(target_dir, source, pick, out_dir)
            shutil.copy2(pick, target)
        except OSError as exc:
            job.detail = f"{job.detail}\nexport failed: {str(exc)[-160:]}"
            return
        self.exported.append(target)
        job.detail = f"{job.detail}\nexport: {target.name}"
        # 记进 stamp：同源再处理（缓存命中）时不重复导出一份 -vocal-2
        self._write_stamp(out_dir, source, exported=str(target))

    def _export_target(self, target_dir: Path, source: Path, pick: Path,
                       out_dir: Path) -> Path:
        """导出目标路径：<原名>-vocal.<后缀>；撞名时区分两种情况。

        上一轮同一个产物导出的那份（stamp 有记录）→ 原地覆盖（源更新后
        重跑，人声就该替换旧的）；别人放的或别的来源占了名 → 递增让位，
        不覆盖不属于自己的文件。
        """
        base = f"{source.stem}{VOCAL_SUFFIX}"
        suffix = pick.suffix.lower()
        target = target_dir / f"{base}{suffix}"
        previous = self._read_exported(out_dir)
        if target.exists() and Path(previous or "") != target:
            serial = 1
            while True:
                serial += 1
                target = target_dir / f"{base}-{serial}{suffix}"
                if not target.exists():
                    break
        return target

    @staticmethod
    def _staged_name(source: Path, mapping: dict[str, Path]) -> str:
        """源路径 -> 暂存文件名（stage_inputs 映射的逆查）。"""
        for name, path in mapping.items():
            if Path(path) == Path(source):
                return name
        return source.stem

    @staticmethod
    def _log_tail(log_path: Path, limit: int = 400) -> str:
        try:
            return log_path.read_text(encoding="utf-8",
                                      errors="replace").strip()[-limit:]
        except OSError:
            return "(log unavailable)"

    @staticmethod
    def _cache_hit(out_dir: Path, source: Path) -> bool:
        """同源同模型已有产出即跳过：stamp 记 mtime_ns+size，源变则重跑。"""
        try:
            stamp = json.loads(
                (out_dir / _STAMP_NAME).read_text(encoding="utf-8"))
            stat = source.stat()
            if (int(stamp.get("mtime_ns", -1)) != stat.st_mtime_ns
                    or int(stamp.get("size", -1)) != stat.st_size):
                return False
        except (OSError, ValueError):
            return False
        return any(p.name != _STAMP_NAME for p in out_dir.iterdir())

    @staticmethod
    def _write_stamp(out_dir: Path, source: Path,
                     exported: str | None = None) -> None:
        try:
            stat = source.stat()
            payload: dict = {"mtime_ns": stat.st_mtime_ns,
                             "size": stat.st_size}
            if exported:
                payload["exported"] = exported
            (out_dir / _STAMP_NAME).write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass  # 缓存戳只是加速：写失败仅损失下次的跳过

    @staticmethod
    def _read_exported(out_dir: Path) -> str | None:
        """stamp 里记录的上次联动导出目标；没导出过/读不到返回 None。"""
        try:
            stamp = json.loads(
                (out_dir / _STAMP_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        value = stamp.get("exported")
        return str(value) if value else None

    # ---------------------------------------------------------------- assets

    def _download_model(self, spec: ModelSpec) -> None:
        """config + weights 落盘：各候选地址依次尝试，边下边写临时名。"""
        config, weights = model_target(spec, self._root)
        config.parent.mkdir(parents=True, exist_ok=True)
        plan = ((config, spec.config_urls), (weights, spec.weights_urls))
        for target, urls in plan:
            # `_fetch` 的约定是"空串=成功"，这里却按"非空=
            # 成功"分支：下载成功反被判失败（抛出 no source），下载失败却把
            # 残缺的 .part 顶成正式权重文件。判定方向改回"空串即成功"
            floor = 1024 if target.name.endswith(".safetensors") else 1
            if target.is_file() and target.stat().st_size >= floor:
                continue
            tmp = target.with_name(target.name + ".part")
            last_error = "no source"
            for url in urls:
                if self._cancel.is_set():
                    tmp.unlink(missing_ok=True)
                    raise _CancelledError()  # 取消不等 curl：权重下载可达 GB 级
                error = self._fetch(url, tmp)
                if not error:
                    tmp.replace(target)
                    last_error = ""
                    break
                last_error = error
                tmp.unlink(missing_ok=True)
            if last_error:
                raise RuntimeError(
                    f"download failed [{target.name}]: {last_error}")

    def _fetch(self, url: str, target: Path) -> str:
        """curl 单源下载；返回空串=成功，否则为错误摘要。

        直连优先（省代理）；GitHub 系直连常被重置，追加显式代理候选。
        """
        commands = [
            ["curl", "--ssl-no-revoke", "-L", "--fail", "--max-time", "1800",
             "-o", str(target), url],
            ["curl", "-L", "--fail", "--max-time", "1800", "-o", str(target),
             url],
        ]
        if "github" in url or "zenodo" in url:
            commands.append(
                ["curl", "--ssl-no-revoke", "-x", LOCAL_GITHUB_PROXY, "-L",
                 "--fail", "--max-time", "1800", "-o", str(target), url])
        last_error = ""
        for command in commands:
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=1900,
                    check=False)
            except (OSError, subprocess.SubprocessError) as exc:
                last_error = str(exc)
                continue
            if result.returncode == 0 and target.is_file() \
                    and target.stat().st_size > 0:
                return ""
            last_error = f"curl exit {result.returncode}"
        return last_error
