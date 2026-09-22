# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""微调栏：GPT-SoVITS 数据集配置 + 五阶段执行 + 实时日志。

执行链路全部在 `app/services/tts_training.py`；本控件只负责表单、阶段状态与日志展示。
训练子进程必须用**带 torch 的那套 Python 环境**（不是本应用的 venv），故解释器可指定。
"""

from __future__ import annotations

import queue
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text, tr
from app.paths import temp_dir
from app.services import tts_training as training

#: 上游仓库位置（相对本仓库根）
GSV_RELATIVE = Path("TTS model") / "GPT-SoVITS"
#: 日志与状态刷新间隔（毫秒）
PUMP_INTERVAL_MS = 120

STAGE_LABEL_KEYS = {
    training.STAGE_PREP_TEXT: "train.stage.prep_text",
    training.STAGE_PREP_SSL: "train.stage.prep_ssl",
    training.STAGE_PREP_SEMANTIC: "train.stage.prep_semantic",
    training.STAGE_TRAIN_S2: "train.stage.train_s2",
    training.STAGE_TRAIN_S1: "train.stage.train_s1",
}
STATE_LABEL_KEYS = {
    training.STAGE_RUNNING: "train.state.running",
    training.STAGE_DONE: "train.state.done",
    training.STAGE_FAILED: "train.state.failed",
}


def gsv_root() -> Path:
    """上游 GPT-SoVITS 仓库根（训练子进程的 CWD 必须是它）。"""

    return Path(__file__).resolve().parents[2] / GSV_RELATIVE


class TtsTrainPanel(QWidget):
    """左栏：数据集与超参表单 + 阶段执行 + 日志。"""

    #: 训练完成（done）后探得的新权重路径 (gpt_path, sovits_path)；空串表示未发现
    weights_discovered = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state: dict[str, str] = {}
        self._last_exp = ""
        self.runner = training.TrainingRunner(temp_dir() / "tts-train-logs")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 子页结构（照官方 webui 工作流）：数据集工具(0b 切片 / 0c ASR) → 微调训练(一键三连 / s2 / s1)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("trainToolTabs")

        tools_tab = QWidget()
        tools_layout = QVBoxLayout(tools_tab)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)

        slice_group = QGroupBox(i18n_text("train.tools.slice"))
        slice_group.setObjectName("trainToolGroup")
        slice_form = QFormLayout(slice_group)
        self.slice_inp_input = QLineEdit()
        self.slice_opt_input = QLineEdit(str(gsv_root() / "output" / "slicer_opt"))
        self.slice_threshold_input = QLineEdit("-34")
        self.slice_min_length_input = QLineEdit("4000")
        self.slice_min_interval_input = QLineEdit("300")
        self.slice_hop_input = QLineEdit("10")
        self.slice_max_sil_input = QLineEdit("500")
        self.slice_max_input = QLineEdit("0.9")
        self.slice_alpha_input = QLineEdit("0.25")
        slice_form.addRow(i18n_text("train.tools.slice_inp"), self.slice_inp_input)
        slice_form.addRow(i18n_text("train.tools.slice_opt"), self.slice_opt_input)
        slice_form.addRow(i18n_text("train.tools.threshold"), self.slice_threshold_input)
        slice_form.addRow(i18n_text("train.tools.min_length"), self.slice_min_length_input)
        slice_form.addRow(i18n_text("train.tools.min_interval"), self.slice_min_interval_input)
        slice_form.addRow(i18n_text("train.tools.hop"), self.slice_hop_input)
        slice_form.addRow(i18n_text("train.tools.max_sil"), self.slice_max_sil_input)
        slice_form.addRow(i18n_text("train.tools.max_norm"), self.slice_max_input)
        slice_form.addRow(i18n_text("train.tools.alpha"), self.slice_alpha_input)
        tools_layout.addWidget(slice_group)

        asr_group = QGroupBox(i18n_text("train.tools.asr"))
        asr_group.setObjectName("trainToolGroup")
        asr_form = QFormLayout(asr_group)
        self.asr_inp_input = QLineEdit()
        self.asr_opt_input = QLineEdit(str(gsv_root() / "output" / "asr_opt"))
        self.asr_backend_input = QComboBox()
        self.asr_backend_input.addItems(tuple(training.ASR_BACKENDS))
        self.asr_backend_input.setCurrentText(training.DEFAULT_ASR_BACKEND)
        self.asr_backend_input.currentTextChanged.connect(self._apply_asr_backend_constraints)
        self.asr_size_input = QComboBox()
        self.asr_size_input.setEditable(True)
        self.asr_size_input.addItems(("large-v3", "large-v2", "medium", "small"))
        self.asr_size_input.setCurrentText("large-v3")
        self.asr_lang_input = QComboBox()
        self.asr_lang_input.addItems(("zh", "ja", "en", "ko", "yue"))
        self.asr_precision_input = QComboBox()
        self.asr_precision_input.addItems(("float16", "float32", "int8"))
        self._apply_asr_backend_constraints(self.asr_backend_input.currentText())
        asr_form.addRow(i18n_text("train.tools.asr_inp"), self.asr_inp_input)
        asr_form.addRow(i18n_text("train.tools.asr_opt"), self.asr_opt_input)
        asr_form.addRow(i18n_text("train.tools.asr_backend"), self.asr_backend_input)
        asr_form.addRow(i18n_text("train.tools.asr_size"), self.asr_size_input)
        asr_form.addRow(i18n_text("train.tools.asr_lang"), self.asr_lang_input)
        asr_form.addRow(i18n_text("train.tools.asr_precision"), self.asr_precision_input)
        tools_layout.addWidget(asr_group)

        self.slice_button = QPushButton(i18n_text("train.tools.run_slice"))
        self.asr_button = QPushButton(i18n_text("train.tools.run_asr"))
        tool_actions = QHBoxLayout()
        tool_actions.addWidget(self.slice_button)
        tool_actions.addWidget(self.asr_button)
        tool_actions.addStretch(1)
        tools_layout.addLayout(tool_actions)
        tools_layout.addStretch(1)
        self.tabs.addTab(tools_tab, i18n_text("train.tab.tools"))

        train_tab = QWidget()
        train_layout = QVBoxLayout(train_tab)
        train_layout.setContentsMargins(0, 0, 0, 0)
        train_layout.setSpacing(8)

        # 两栏高度有限：表单与阶段区放进滚动容器，日志区固定最小高度（布局挤压修复）
        train_scroll = QScrollArea()
        train_scroll.setObjectName("trainFormScroll")
        train_scroll.setWidgetResizable(True)
        train_scroll.setFrameShape(QFrame.Shape.NoFrame)
        train_scroll.setWidget(train_tab)
        self.tabs.addTab(train_scroll, i18n_text("train.tab.train"))
        root.addWidget(self.tabs, 1)

        self.hint = QLabel(i18n_text("train.hint"))
        self.hint.setObjectName("mutedLabel")
        self.hint.setWordWrap(True)
        train_layout.addWidget(self.hint)

        self.dataset_group = QGroupBox(i18n_text("train.group.dataset"))
        self.dataset_group.setObjectName("trainToolGroup")
        form = QFormLayout(self.dataset_group)
        self.repo_label = QLabel(str(gsv_root()))
        self.repo_label.setObjectName("mutedLabel")
        self.repo_label.setWordWrap(True)
        form.addRow(QLabel(i18n_text("train.field.repo")), self.repo_label)

        self.python_input = _path_row(form, i18n_text("train.field.python"), self._browse_python)
        self.list_input = _path_row(form, i18n_text("train.field.list"), self._browse_list)
        self.wav_input = _path_row(form, i18n_text("train.field.wav_dir"), self._browse_dir)
        self.exp_input = QLineEdit()
        self.exp_input.setPlaceholderText(i18n_text("train.field.exp_hint"))
        form.addRow(QLabel(i18n_text("train.field.exp_name")), self.exp_input)
        self.version_input = QComboBox()
        self.version_input.addItems(training.VERSIONS)
        self.version_input.setCurrentText("v2ProPlus")
        form.addRow(QLabel(i18n_text("train.field.version")), self.version_input)
        self.gpu_input = QLineEdit("0")
        form.addRow(QLabel(i18n_text("train.field.gpu")), self.gpu_input)
        self.half_input = QCheckBox(i18n_text("train.field.half"))
        self.half_input.setChecked(True)
        form.addRow(QLabel(""), self.half_input)
        train_layout.addWidget(self.dataset_group)

        self.hyper_group = QGroupBox(i18n_text("train.group.hyper"))
        self.hyper_group.setObjectName("trainToolGroup")
        hyper = QFormLayout(self.hyper_group)
        self.s2_epochs_input = _spin(hyper, "train.field.s2_epochs", 1, 1000, 8)
        self.s2_batch_input = _spin(hyper, "train.field.s2_batch", 1, 128, 6)
        self.s2_save_input = _spin(hyper, "train.field.s2_save_every", 1, 100, 4)
        self.s2_low_lr_input = QDoubleSpinBox()
        self.s2_low_lr_input.setRange(0.0, 1.0)
        self.s2_low_lr_input.setSingleStep(0.1)
        self.s2_low_lr_input.setDecimals(2)
        self.s2_low_lr_input.setValue(0.4)
        hyper.addRow(QLabel(i18n_text("train.field.s2_low_lr")), self.s2_low_lr_input)
        self.s2_lora_input = _spin(hyper, "train.field.s2_lora", 1, 256, 32)
        self.s1_epochs_input = _spin(hyper, "train.field.s1_epochs", 1, 1000, 15)
        self.s1_batch_input = _spin(hyper, "train.field.s1_batch", 1, 128, 6)
        self.s1_save_input = _spin(hyper, "train.field.s1_save_every", 1, 100, 5)
        train_layout.addWidget(self.hyper_group)

        actions = QHBoxLayout()
        self.prep_button = QPushButton(i18n_text("train.action.prep"))
        self.s2_button = QPushButton(i18n_text("train.action.s2"))
        self.s1_button = QPushButton(i18n_text("train.action.s1"))
        self.readiness_button = QPushButton(i18n_text("train.action.readiness"))
        self.stop_button = QPushButton(i18n_text("train.action.stop"))
        self.stop_button.setEnabled(False)
        for widget in (self.prep_button, self.s2_button, self.s1_button, self.readiness_button, self.stop_button):
            actions.addWidget(widget)
        actions.addStretch(1)
        train_layout.addLayout(actions)

        self.stage_labels: dict[str, QLabel] = {}
        stages = QGroupBox(i18n_text("train.group.stages"))
        stages.setObjectName("trainToolGroup")
        stages_layout = QVBoxLayout(stages)
        for key in training.STAGE_ORDER:
            label = QLabel()
            label.setObjectName("mutedLabel")
            self.stage_labels[key] = label
            stages_layout.addWidget(label)
        train_layout.addWidget(stages)
        train_layout.addStretch(1)
        train_scroll.setWidget(train_tab)
        self.tabs.addTab(train_scroll, i18n_text("train.tab.train"))
        root.addWidget(self.tabs, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.log_view.setPlaceholderText(i18n_text("train.log.placeholder"))
        self.log_view.setMinimumHeight(140)
        root.addWidget(self.log_view)

        self.slice_button.clicked.connect(self._start_slice)
        self.asr_button.clicked.connect(self._start_asr)
        self.prep_button.clicked.connect(lambda: self._start(("prep",)))
        self.s2_button.clicked.connect(lambda: self._start(("s2",)))
        self.s1_button.clicked.connect(lambda: self._start(("s1",)))
        self.readiness_button.clicked.connect(self._run_readiness)
        self.stop_button.clicked.connect(self._stop)

        self._pump = QTimer(self)
        self._pump.setInterval(PUMP_INTERVAL_MS)
        self._pump.timeout.connect(self._drain)
        self._pump.start()

        self.retranslate()

    # —— 表单辅助 ——
    def _browse_python(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, i18n_text("train.field.python"), "", "Python (python*.exe);;All files (*)")
        if path:
            self.python_input.setText(path)

    def _browse_list(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, i18n_text("train.field.list"), "", "Dataset list (*.list);;All files (*)")
        if path:
            self.list_input.setText(path)

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, i18n_text("train.field.wav_dir"))
        if path:
            self.wav_input.setText(path)

    # —— 契约 ——
    @property
    def is_running(self) -> bool:
        return self.runner.is_running

    def config(self) -> training.TrainConfig:
        """按表单构造训练配置（路径字段原样传入，由上游自行校验）。"""

        return training.TrainConfig(
            repo=gsv_root(),
            inp_text=Path(self.list_input.text().strip()),
            inp_wav_dir=Path(self.wav_input.text().strip()),
            exp_name=self.exp_input.text().strip(),
            version=self.version_input.currentText(),
            gpu_numbers=self.gpu_input.text().strip() or "0",
            is_half=self.half_input.isChecked(),
            python_exec=self.python_input.text().strip(),
            s2_epochs=self.s2_epochs_input.value(),
            s2_batch_size=self.s2_batch_input.value(),
            s2_save_every_epoch=self.s2_save_input.value(),
            s2_text_low_lr_rate=round(self.s2_low_lr_input.value(), 2),
            s2_lora_rank=self.s2_lora_input.value(),
            s1_epochs=self.s1_epochs_input.value(),
            s1_batch_size=self.s1_batch_input.value(),
            s1_save_every_epoch=self.s1_save_input.value(),
        )

    def invalid_reason(self) -> str:
        """返回不能开始训练的原因（空串表示可以开始）。"""

        config = self.config()
        if not config.inp_text.name:
            return tr("train.error.missing_list")
        if not config.exp_name:
            return tr("train.error.missing_exp")
        return ""

    def _start(self, groups: tuple[str, ...]) -> None:
        if self.runner.is_running:
            self._append(tr("train.error.busy"))
            return
        reason = self.invalid_reason()
        if reason:
            self._append(reason)
            return
        config = self.config()
        self._last_exp = config.exp_name
        wanted = {
            "prep": (training.STAGE_PREP_TEXT, training.STAGE_PREP_SSL, training.STAGE_PREP_SEMANTIC),
            "s2": (training.STAGE_TRAIN_S2,),
            "s1": (training.STAGE_TRAIN_S1,),
        }
        keys = tuple(key for group in groups for key in wanted[group])
        stages = [stage for stage in training.build_stages(config) if stage.key in keys]
        self._state = {stage.key: "" for stage in stages}
        self._refresh_stages()
        self.log_view.clear()
        self._append(tr("train.log.started", name=config.exp_name))
        self.runner.start(stages)
        self._set_running(True)

    def _stop(self) -> None:
        self._append(tr("train.log.stopping"))
        self.runner.stop()
        self._set_running(False)

    # —— 数据集工具（0b 切片 / 0c ASR；argv 契约与 webui.py 一致）——
    def _apply_asr_backend_constraints(self, backend: str) -> None:
        """按识别方式联动语言/规模/精度可选项（与上游 asr_dict 约束一致）。"""

        meta = training.ASR_BACKENDS.get(backend)
        if meta is None:
            return

        def refill(combo: QComboBox, values: tuple[str, ...], keep: str) -> None:
            combo.clear()
            combo.addItems(values)
            if keep in values:
                combo.setCurrentText(keep)

        refill(self.asr_lang_input, tuple(meta["langs"]), self.asr_lang_input.currentText())
        if not self.asr_size_input.isEditable() or not any(
            self.asr_size_input.currentText() == value for value in meta["sizes"]
        ):
            refill(self.asr_size_input, tuple(meta["sizes"]), self.asr_size_input.currentText())
        refill(self.asr_precision_input, tuple(meta["precisions"]), self.asr_precision_input.currentText())

    def _start_slice(self) -> None:
        if self.runner.is_running:
            self._append(tr("train.error.busy"))
            return
        inp = self.slice_inp_input.text().strip()
        if not inp:
            self._append(tr("train.tools.missing_inp"))
            return
        params = training.SliceParams(
            inp=Path(inp),
            opt_root=Path(self.slice_opt_input.text().strip() or str(gsv_root() / "output" / "slicer_opt")),
            threshold=self.slice_threshold_input.text().strip() or "-34",
            min_length=self.slice_min_length_input.text().strip() or "4000",
            min_interval=self.slice_min_interval_input.text().strip() or "300",
            hop_size=self.slice_hop_input.text().strip() or "10",
            max_sil_kept=self.slice_max_sil_input.text().strip() or "500",
            max_norm=self.slice_max_input.text().strip() or "0.9",
            alpha_mix=self.slice_alpha_input.text().strip() or "0.25",
        )
        self.asr_inp_input.setText(str(params.opt_root))
        self.wav_input.setText(str(params.opt_root))
        self._run_tool("slice", training.slice_commands(self.config(), params))

    def _start_asr(self) -> None:
        if self.runner.is_running:
            self._append(tr("train.error.busy"))
            return
        inp = self.asr_inp_input.text().strip()
        if not inp:
            self._append(tr("train.tools.missing_asr_inp"))
            return
        params = training.AsrParams(
            inp=Path(inp),
            opt_dir=Path(self.asr_opt_input.text().strip() or str(gsv_root() / "output" / "asr_opt")),
            backend=self.asr_backend_input.currentText(),
            model_size=self.asr_size_input.currentText().strip() or "large-v3",
            language=self.asr_lang_input.currentText().strip() or "zh",
            precision=self.asr_precision_input.currentText().strip() or "float16",
        )
        self._run_tool("asr", training.asr_commands(self.config(), params))
        list_path = training.asr_list_output(params.opt_dir, params.inp)
        if list_path.is_file():
            self.list_input.setText(str(list_path))
            self.wav_input.setText(inp)

    def _run_tool(self, key: str, stages) -> None:
        self._state = {stage.key: "" for stage in stages}
        self._refresh_stages()
        self.runner.start(stages)
        self._set_running(True)

    def _run_readiness(self) -> None:
        exp = self.exp_input.text().strip()
        if not exp:
            self._append(tr("train.error.missing_exp"))
            return
        report = training.readiness_report(gsv_root() / "logs" / exp)
        names = (
            ("text", "train.readiness.text"),
            ("bert", "train.readiness.bert"),
            ("cnhubert", "train.readiness.cnhubert"),
            ("wav32k", "train.readiness.wav32k"),
            ("semantic", "train.readiness.semantic"),
        )
        self._append(i18n_text("train.readiness.header"))
        for key, name_key in names:
            state_key = "train.readiness.ready" if report.get(key) else "train.readiness.missing"
            self._append(f"{i18n_text(name_key)}：{i18n_text(state_key)}")

    def _discover_trained_weights(self) -> tuple[str, str]:
        """扫描实验目录，取最近修改的 GPT(.ckpt) / SoVITS(.pth) 训练产物。"""

        exp = self._last_exp.strip()
        if not exp:
            return "", ""
        opt = gsv_root() / "logs" / exp
        if not opt.is_dir():
            return "", ""

        def newest(pattern: str) -> str:
            candidates = [path for path in opt.rglob(pattern) if path.is_file()]
            return str(max(candidates, key=lambda path: path.stat().st_mtime)) if candidates else ""

        return newest("*.ckpt"), newest("*.pth")

    def _set_running(self, running: bool) -> None:
        for widget in (self.prep_button, self.s2_button, self.s1_button, self.readiness_button, self.slice_button, self.asr_button):
            widget.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _append(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def _drain(self) -> None:
        while True:
            try:
                kind, payload = self.runner.events.get_nowait()
            except queue.Empty:
                break
            if kind == "stage":
                key, state = payload
                self._state[key] = state
                self._refresh_stages()
            elif kind == "log":
                _key, line = payload
                self._append(line)
            elif kind == "done":
                self._set_running(False)
                self._append(tr("train.log.done") if payload else tr("train.log.failed"))
                gpt_path, sovits_path = self._discover_trained_weights()
                if gpt_path or sovits_path:
                    self.weights_discovered.emit(gpt_path, sovits_path)
                    self._append(tr("train.log.weights_found", gpt=gpt_path, sovits=sovits_path))

    def _refresh_stages(self) -> None:
        for key, label in self.stage_labels.items():
            state = self._state.get(key, "")
            title = i18n_text(STAGE_LABEL_KEYS[key])
            label.setText(f"{title}：{i18n_text(STATE_LABEL_KEYS[state]) if state else i18n_text('train.state.idle')}")

    def can_navigate_away(self) -> bool:
        return not self.runner.is_running

    def retranslate(self) -> None:
        self.hint.setText(i18n_text("train.hint"))
        self.dataset_group.setTitle(i18n_text("train.group.dataset"))
        self.hyper_group.setTitle(i18n_text("train.group.hyper"))
        self.exp_input.setPlaceholderText(i18n_text("train.field.exp_hint"))
        self.half_input.setText(i18n_text("train.field.half"))
        for button, key in (
            (self.prep_button, "train.action.prep"),
            (self.s2_button, "train.action.s2"),
            (self.s1_button, "train.action.s1"),
            (self.stop_button, "train.action.stop"),
        ):
            button.setText(i18n_text(key))
        self.log_view.setPlaceholderText(i18n_text("train.log.placeholder"))
        self._refresh_stages()


def _path_row(form: QFormLayout, label_key: str, browse) -> QLineEdit:
    """一行"输入框 + 浏览"（返回输入框本身）。"""

    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    field = QLineEdit()
    button = QPushButton(i18n_text("train.action.browse"))
    button.setFixedWidth(64)
    button.clicked.connect(browse)
    layout.addWidget(field, 1)
    layout.addWidget(button)
    form.addRow(QLabel(i18n_text(label_key)), holder)
    return field


def _spin(form: QFormLayout, label_key: str, minimum: int, maximum: int, value: int) -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    form.addRow(QLabel(i18n_text(label_key)), box)
    return box
