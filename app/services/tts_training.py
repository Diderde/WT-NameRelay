# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""GPT-SoVITS 微调链路：数据准备（prep 三阶段）与 s1/s2 两段训练。

本模块**只驱动上游脚本原样运行**，不改上游代码；编排忠实复刻官方 `webui.py`：

- prep 三阶段**没有命令行参数**，全部以环境变量传参（脚本顶部 `os.environ.get`）；
- 1A/1C 需要把各 GPU part 的产物合并成单文件，1B 不需要（各 part 直接写入 `opt_dir`）；
- 训练阶段吃"现场改写模板"生成的配置：s2 是 JSON、s1 是 YAML。

契约来源：`TTS model/GPT-SoVITS/webui.py` 的 open1a/open1b/open1c/open1Ba/open1Bb，
以及 `GPT_SoVITS/prepare_datasets/*.py` 顶部读取的环境变量。

必须遵守的上游约束（照抄 webui 之外容易踩空）：

1. 子进程 **CWD 必须是 GPT-SoVITS 仓库根** —— 脚本用 `os.getcwd()` 拼路径并 `import tools.*`；
2. `is_half` 会被上游 `eval()`，只能传 `"True"`/`"False"`；
3. 全局 `version` 环境变量是 s1/s2 的**导入期依赖**（符号表选择），必须在 env 里显式给出；
4. s1 另外需要 `hz=25hz` 与 `_CUDA_VISIBLE_DEVICES`；s2 **不看**该变量，GPU 由配置字段决定；
5. 合并假设每个 part 文件都存在，缺一个就抛 `FileNotFoundError`；
6. 上游**不看退出码**，成功与否要靠产物存在性与 stdout 判断；
7. s1 的 YAML 配置模板很小，`pretrained_s1` 等键是 webui 追加的 —— 本模块同样按需追加。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# —— 版本矩阵（与 config.py:12-28、webui.py:507-544/604-606 对齐） ——
#: 上游 UI 可选版本（v3 在这个 vendored 版本里不可选，故不列入）
VERSIONS = ("v1", "v2", "v4", "v2Pro", "v2ProPlus")
PRO_VERSIONS = frozenset({"v2Pro", "v2ProPlus"})
LORA_VERSIONS = frozenset({"v3", "v4"})

PRETRAINED_S2G = {
    "v1": "GPT_SoVITS/pretrained_models/s2G488k.pth",
    "v2": "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth",
    "v3": "GPT_SoVITS/pretrained_models/s2Gv3.pth",
    "v4": "GPT_SoVITS/pretrained_models/gsv-v4-pretrained/s2Gv4.pth",
    "v2Pro": "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth",
    "v2ProPlus": "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth",
}
PRETRAINED_S1 = {
    "v1": "GPT_SoVITS/pretrained_models/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt",
    "v2": "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
    "v3": "GPT_SoVITS/pretrained_models/s1v3.ckpt",
    "v4": "GPT_SoVITS/pretrained_models/s1v3.ckpt",
    "v2Pro": "GPT_SoVITS/pretrained_models/s1v3.ckpt",
    "v2ProPlus": "GPT_SoVITS/pretrained_models/s1v3.ckpt",
}
SOVITS_WEIGHT_DIR = {
    "v1": "SoVITS_weights",
    "v2": "SoVITS_weights_v2",
    "v3": "SoVITS_weights_v3",
    "v4": "SoVITS_weights_v4",
    "v2Pro": "SoVITS_weights_v2Pro",
    "v2ProPlus": "SoVITS_weights_v2ProPlus",
}
GPT_WEIGHT_DIR = {version: dirname.replace("SoVITS", "GPT") for version, dirname in SOVITS_WEIGHT_DIR.items()}

#: 实验根目录（config.py:137 `exp_root = "logs"`，相对仓库根）
EXP_ROOT = "logs"
#: 上游在仓库根下自建的临时目录（webui.py:21），生成的配置写在这里
TEMP_DIR = "TEMP"

BERT_PRETRAINED_DIR = "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
CNHUBERT_PRETRAINED_DIR = "GPT_SoVITS/pretrained_models/chinese-hubert-base"
SV_PRETRAINED_PATH = "GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt"

#: 阶段键（顺序即执行顺序）
STAGE_PREP_TEXT = "prep_text"
STAGE_PREP_SSL = "prep_ssl"
STAGE_PREP_SEMANTIC = "prep_semantic"
STAGE_TRAIN_S2 = "train_s2"
STAGE_TRAIN_S1 = "train_s1"
STAGE_ORDER = (STAGE_PREP_TEXT, STAGE_PREP_SSL, STAGE_PREP_SEMANTIC, STAGE_TRAIN_S2, STAGE_TRAIN_S1)

STAGE_RUNNING = "running"
STAGE_DONE = "done"
STAGE_FAILED = "failed"


def s2_template(version: str) -> str:
    """s2 配置模板（webui.py:507-511）：Pro 系用专属模板，其余共用 s2.json。"""

    return f"GPT_SoVITS/configs/s2{version}.json" if version in PRO_VERSIONS else "GPT_SoVITS/configs/s2.json"


def s1_template(version: str) -> str:
    """s1 配置模板（webui.py:604-606）：v1 用 s1longer.yaml，其余用 s1longer-v2.yaml。"""

    return "GPT_SoVITS/configs/s1longer.yaml" if version == "v1" else "GPT_SoVITS/configs/s1longer-v2.yaml"


def s2_train_script(version: str) -> str:
    """v3/v4 走 LoRA 训练脚本，其余走 s2_train.py（webui.py:541-544）。"""

    return "GPT_SoVITS/s2_train_v3_lora.py" if version in LORA_VERSIONS else "GPT_SoVITS/s2_train.py"


def s2_checkpoint_dir(config: TrainConfig) -> Path:
    """s2 权重落点：v3/v4 的 LoRA 训练写 `logs_s2_<version>_lora_<rank>`（webui 预建的
    `logs_s2_<version>` 反而是空目录）。"""

    if config.version in LORA_VERSIONS:
        return config.opt_dir / f"logs_s2_{config.version}_lora_{config.s2_lora_rank}"
    return config.opt_dir / f"logs_s2_{config.version}"


@dataclass(slots=True)
class TrainConfig:
    """一次微调的输入与超参。路径型字段应为绝对路径。"""

    repo: Path
    inp_text: Path
    inp_wav_dir: Path
    exp_name: str
    version: str = "v2ProPlus"
    gpu_numbers: str = "0"
    is_half: bool = True
    python_exec: str = ""
    #: SSL（cnhubert）与 BERT 预训练目录；留空取仓库内默认
    ssl_pretrained_dir: str = ""
    bert_pretrained_dir: str = ""
    #: s2 超参
    s2_epochs: int = 8
    s2_batch_size: int = 6
    s2_save_every_epoch: int = 4
    s2_text_low_lr_rate: float = 0.4
    s2_lora_rank: int = 32
    s2_grad_ckpt: bool = False
    #: s1 超参
    s1_epochs: int = 15
    s1_batch_size: int = 6
    s1_save_every_epoch: int = 5
    s1_if_dpo: bool = False

    @property
    def opt_dir(self) -> Path:
        """实验输出目录 `logs/<exp_name>`（webui.py:788）。"""

        return self.repo / EXP_ROOT / self.exp_name

    def gpu_parts(self) -> tuple[str, ...]:
        """`0-1` 形式的 GPU 串拆成各 part（webui.py:796-797）。"""

        return tuple(part for part in self.gpu_numbers.split("-") if part != "") or ("0",)

    def resolve_python(self) -> str:
        """训练解释器：必须是有 torch 的那套环境，不能用本应用的 venv。"""

        return self.python_exec or "python"


@dataclass(frozen=True, slots=True)
class Command:
    argv: tuple[str, ...]
    env: Mapping[str, str]
    cwd: Path


# —— 数据集工具（0b 切片 / 0c ASR；argv 契约与 webui.py 一致）——

SLICE_SCRIPT = "tools/slice_audio.py"

#: 与上游 ``tools/asr/config.py`` 的 asr_dict 逐项对齐：语言/规模/精度约束随识别方式联动
ASR_BACKENDS: dict[str, dict[str, object]] = {
    "Fun-ASR-Nano (31语种+方言, 推荐)": {
        "langs": ("zh", "en", "ja", "ko", "yue", "auto"),
        "sizes": ("large",),
        "precisions": ("float32",),
        "script": "tools/asr/funasr_asr.py",
    },
    "SenseVoice (极速, 5语种)": {
        "langs": ("zh", "en", "ja", "ko", "yue", "auto"),
        "sizes": ("large",),
        "precisions": ("float32",),
        "script": "tools/asr/funasr_asr.py",
    },
    "达摩 ASR (中文经典)": {
        "langs": ("zh", "yue"),
        "sizes": ("large",),
        "precisions": ("float32",),
        "script": "tools/asr/funasr_asr.py",
    },
    "Faster Whisper (多语种)": {
        "langs": ("auto", "en", "ja", "ko"),
        "sizes": ("medium", "medium.en", "large-v2", "large-v3", "large-v3-turbo"),
        "precisions": ("float32", "float16", "int8"),
        "script": "tools/asr/fasterwhisper_asr.py",
    },
}
DEFAULT_ASR_BACKEND = "Fun-ASR-Nano (31语种+方言, 推荐)"


@dataclass(frozen=True, slots=True)
class SliceParams:
    inp: Path
    opt_root: Path
    threshold: str = "-34"
    min_length: str = "4000"
    min_interval: str = "300"
    hop_size: str = "10"
    max_sil_kept: str = "500"
    max_norm: str = "0.9"
    alpha_mix: str = "0.25"


@dataclass(frozen=True, slots=True)
class AsrParams:
    inp: Path
    opt_dir: Path
    backend: str = DEFAULT_ASR_BACKEND
    model_size: str = "large-v3"
    language: str = "zh"
    precision: str = "float32"


def slice_commands(config: TrainConfig, params: SliceParams) -> tuple[Command, ...]:
    """0b 语音切分（webui.py:713 同款 argv；v1 单进程，n_parts=1）。"""

    return (
        Command(
            argv=(
                config.resolve_python(),
                "-s",
                SLICE_SCRIPT,
                str(params.inp),
                str(params.opt_root),
                params.threshold,
                params.min_length,
                params.min_interval,
                params.hop_size,
                params.max_sil_kept,
                params.max_norm,
                params.alpha_mix,
                "0",
                "1",
            ),
            env=_base_env(config),
            cwd=config.repo,
        ),
    )


def asr_command(config: TrainConfig, params: AsrParams) -> Command:
    """0c 语音识别 → 生成 `.list`（webui.py:371 同款 argv）。"""

    meta = ASR_BACKENDS.get(params.backend, ASR_BACKENDS[DEFAULT_ASR_BACKEND])
    return Command(
        argv=(
            config.resolve_python(),
            "-s",
            str(meta["script"]),
            "-i",
            str(params.inp),
            "-o",
            str(params.opt_dir),
            "-s",
            params.model_size,
            "-l",
            params.language,
            "-p",
            params.precision,
        ),
        env=_base_env(config),
        cwd=config.repo,
    )


def asr_list_output(opt_dir: Path, inp_dir: Path) -> Path:
    """识别产物 `.list`：`<输出目录>/<输入目录名>.list`（webui 同款命名）。"""

    return Path(opt_dir) / f"{Path(inp_dir).name}.list"


@dataclass(frozen=True, slots=True)
class StagePlan:
    key: str
    commands: tuple[Command, ...]
    merge: Callable[[], None] | None = None
    outputs: tuple[Path, ...] = field(default_factory=tuple)


# —— 环境与命令组装 ——
def _base_env(config: TrainConfig) -> dict[str, str]:
    env = dict(os.environ)
    # 上游把 `version` 当全局开关（s1/s2 导入期读取），必须显式给出
    env["version"] = config.version
    env["is_half"] = "True" if config.is_half else "False"
    return env


def _prep_commands(config: TrainConfig, script: str, extra: Mapping[str, str]) -> tuple[Command, ...]:
    """prep 阶段：按 GPU part 各起一个进程，参数全走环境变量。"""

    parts = config.gpu_parts()
    commands: list[Command] = []
    for index in range(len(parts)):
        env = _base_env(config)
        env.update(
            {
                "inp_text": str(config.inp_text),
                "inp_wav_dir": str(config.inp_wav_dir),
                "exp_name": config.exp_name,
                "opt_dir": str(config.opt_dir),
                "i_part": str(index),
                "all_parts": str(len(parts)),
                "_CUDA_VISIBLE_DEVICES": parts[index],
            }
        )
        env.update(extra)
        commands.append(
            Command(
                argv=(config.resolve_python(), "-s", script),
                env=env,
                cwd=config.repo,
            )
        )
    return tuple(commands)


def merge_text_parts(opt_dir: Path, all_parts: int) -> None:
    """合并 1A 的各 part 文本（webui.py:819-827）：无表头，拼接后删除分片。"""

    merged: list[str] = []
    for index in range(all_parts):
        part = opt_dir / f"2-name2text-{index}.txt"
        merged += part.read_text(encoding="utf8").strip("\n").split("\n")
        part.unlink()
    (opt_dir / "2-name2text.txt").write_text("\n".join(merged) + "\n", encoding="utf8")


def merge_semantic_parts(opt_dir: Path, all_parts: int) -> None:
    """合并 1C 的各 part 语义（webui.py:1003-1011）：**带表头**，拼接后删除分片。"""

    merged: list[str] = ["item_name\tsemantic_audio"]
    for index in range(all_parts):
        part = opt_dir / f"6-name2semantic-{index}.tsv"
        merged += part.read_text(encoding="utf8").strip("\n").split("\n")
        part.unlink()
    (opt_dir / "6-name2semantic.tsv").write_text("\n".join(merged) + "\n", encoding="utf8")


def write_s2_config(config: TrainConfig) -> Path:
    """按 webui.py:507-540 改写 s2 配置并落到 `TEMP/tmp_s2.json`，返回其路径。"""

    template_path = config.repo / s2_template(config.version)
    data = json.loads(template_path.read_text(encoding="utf8"))
    batch_size = config.s2_batch_size
    if not config.is_half:
        data["train"]["fp16_run"] = False
        batch_size = max(1, batch_size // 2)
    data["train"].update(
        {
            "batch_size": batch_size,
            "epochs": config.s2_epochs,
            "text_low_lr_rate": config.s2_text_low_lr_rate,
            "pretrained_s2G": PRETRAINED_S2G[config.version],
            "pretrained_s2D": PRETRAINED_S2G[config.version].replace("s2G", "s2D"),
            "if_save_latest": True,
            "if_save_every_weights": True,
            "save_every_epoch": config.s2_save_every_epoch,
            "gpu_numbers": config.gpu_numbers,
            "grad_ckpt": config.s2_grad_ckpt,
            "lora_rank": config.s2_lora_rank,
        }
    )
    data["model"]["version"] = config.version
    data["data"]["exp_dir"] = data["s2_ckpt_dir"] = str(config.opt_dir)
    data["save_weight_dir"] = SOVITS_WEIGHT_DIR[config.version]
    data["name"] = config.exp_name
    data["version"] = config.version

    target = config.repo / TEMP_DIR / "tmp_s2.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data), encoding="utf8")
    return target


def dump_simple_yaml(root_scalars: Mapping[str, object], sections: Mapping[str, Mapping[str, object]]) -> str:
    """极简 YAML 输出：顶层标量 + 一层嵌套。

    本应用**不引入 PyYAML**（上游那套环境才有）；s1 模板结构简单，且所有追加项都是
    标量，因此这里自写输出。字符串一律单引号包裹，避免 Windows 路径里的反斜杠与冒号
    被 YAML 误读（单引号标量除 `''` 外不做转义处理）。
    """

    def scalar(value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            text = repr(value)
            # YAML 1.1（PyYAML）的浮点正则要求带小数点：`1e-05` 会被解析成**字符串**，
            # 而上游用 yaml.full_load 读这份配置。指数写法一律摊成普通小数。
            if "e" in text or "E" in text:
                text = format(value, "f")
            return text if "." in text else text + ".0"
        if value is None:
            return "null"
        return "'" + str(value).replace("'", "''") + "'"

    lines = [f"{key}: {scalar(value)}" for key, value in root_scalars.items()]
    for section, values in sections.items():
        lines.append(f"{section}:")
        lines.extend(f"  {key}: {scalar(value)}" for key, value in values.items())
    return "\n".join(lines) + "\n"


def parse_simple_yaml(text: str) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """解析 `dump_simple_yaml` 能产出的那类 YAML（够用来读上游 s1 模板）。

    只认 `key: value` 与 `section:`+两空格缩进；行内 `#` 注释与空行忽略。
    解析不了的行直接跳过，保证上游模板若有微调也不会让界面崩掉。
    """

    root: dict[str, object] = {}
    sections: dict[str, dict[str, object]] = {}
    current: dict[str, object] | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            if line.endswith(":"):
                current = sections.setdefault(line[:-1].strip(), {})
                continue
            current = None
            key, _, value = line.partition(":")
            root[key.strip()] = _coerce_yaml_scalar(value.strip())
            continue
        if current is None:
            continue
        key, _, value = line.strip().partition(":")
        current[key.strip()] = _coerce_yaml_scalar(value.strip())
    return root, sections


def _coerce_yaml_scalar(text: str) -> object:
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def write_s1_config(config: TrainConfig) -> Path:
    """按 webui.py:604-634 改写 s1 配置并落到 `TEMP/tmp_s1.yaml`，返回其路径。"""

    template_path = config.repo / s1_template(config.version)
    root, sections = parse_simple_yaml(template_path.read_text(encoding="utf8"))
    train = dict(sections.get("train", {}))
    batch_size = config.s1_batch_size
    if not config.is_half:
        train["precision"] = "32"
        batch_size = max(1, batch_size // 2)
    train.update(
        {
            "batch_size": batch_size,
            "epochs": config.s1_epochs,
            "save_every_n_epoch": config.s1_save_every_epoch,
            "if_save_every_weights": True,
            "if_save_latest": True,
            "if_dpo": config.s1_if_dpo,
            "half_weights_save_dir": GPT_WEIGHT_DIR[config.version],
            "exp_name": config.exp_name,
        }
    )
    sections["train"] = train
    root.update(
        {
            "pretrained_s1": PRETRAINED_S1[config.version],
            "train_semantic_path": str(config.opt_dir / "6-name2semantic.tsv"),
            "train_phoneme_path": str(config.opt_dir / "2-name2text.txt"),
            "output_dir": str(config.opt_dir / f"logs_s1_{config.version}"),
        }
    )
    # 顶层标量排在节之前，保持与上游 dump 一致的可读顺序
    ordered_root = {key: value for key, value in root.items() if not isinstance(value, dict)}
    target = config.repo / TEMP_DIR / "tmp_s1.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_simple_yaml(ordered_root, sections), encoding="utf8")
    return target


def ensure_weight_dirs(config: TrainConfig) -> None:
    """建好产出目录（上游在 import 时做，见 webui.py:200-201；本模块必须自建）。"""

    for dirname in (SOVITS_WEIGHT_DIR[config.version], GPT_WEIGHT_DIR[config.version]):
        (config.repo / dirname).mkdir(parents=True, exist_ok=True)
    config.opt_dir.mkdir(parents=True, exist_ok=True)


def build_stages(config: TrainConfig) -> tuple[StagePlan, ...]:
    """装配五个阶段的执行计划（顺序固定：1A → 1B → 1C → s2 → s1）。"""

    ensure_weight_dirs(config)
    parts = len(config.gpu_parts())
    opt_dir = config.opt_dir
    ssl_dir = config.ssl_pretrained_dir or CNHUBERT_PRETRAINED_DIR
    bert_dir = config.bert_pretrained_dir or BERT_PRETRAINED_DIR
    python = config.resolve_python()

    prep_text = _prep_commands(
        config,
        "GPT_SoVITS/prepare_datasets/1-get-text.py",
        {"bert_pretrained_dir": bert_dir},
    )
    prep_ssl = _prep_commands(
        config,
        "GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py",
        {"cnhubert_base_dir": ssl_dir, "sv_path": SV_PRETRAINED_PATH},
    )
    commands_ssl = list(prep_ssl)
    if config.version in PRO_VERSIONS:
        # Pro 系额外提说话人向量（webui.py:910-926）
        commands_ssl += list(_prep_commands(config, "GPT_SoVITS/prepare_datasets/2-get-sv.py", {"sv_path": SV_PRETRAINED_PATH}))
    prep_semantic = _prep_commands(
        config,
        "GPT_SoVITS/prepare_datasets/3-get-semantic.py",
        {
            "pretrained_s2G": PRETRAINED_S2G[config.version],
            "s2config_path": s2_template(config.version),
        },
    )

    def s2_command() -> Command:
        s2_config = write_s2_config(config)
        return Command(argv=(python, "-s", s2_train_script(config.version), "--config", str(s2_config)), env=_base_env(config), cwd=config.repo)

    def s1_command() -> Command:
        s1_config = write_s1_config(config)
        env = _base_env(config)
        # s1 走 Lightning：GPU 从 `_CUDA_VISIBLE_DEVICES` 取，且需要 hz（AR/data/dataset.py:91）
        env["_CUDA_VISIBLE_DEVICES"] = config.gpu_numbers.replace("-", ",")
        env["hz"] = "25hz"
        return Command(argv=(python, "-s", "GPT_SoVITS/s1_train.py", "--config_file", str(s1_config)), env=env, cwd=config.repo)

    return (
        StagePlan(
            key=STAGE_PREP_TEXT,
            commands=prep_text,
            merge=lambda: merge_text_parts(opt_dir, parts),
            outputs=(opt_dir / "2-name2text.txt",),
        ),
        StagePlan(
            key=STAGE_PREP_SSL,
            commands=tuple(commands_ssl),
            outputs=(opt_dir / "4-cnhubert", opt_dir / "5-wav32k"),
        ),
        StagePlan(
            key=STAGE_PREP_SEMANTIC,
            commands=prep_semantic,
            merge=lambda: merge_semantic_parts(opt_dir, parts),
            outputs=(opt_dir / "6-name2semantic.tsv",),
        ),
        StagePlan(key=STAGE_TRAIN_S2, commands=(s2_command(),), outputs=(s2_checkpoint_dir(config),)),
        StagePlan(key=STAGE_TRAIN_S1, commands=(s1_command(),), outputs=(opt_dir / f"logs_s1_{config.version}",)),
    )


def readiness_report(opt_dir: Path) -> dict[str, bool]:
    """训练前置检查（对应上游 check_details(..., is_train=True) 的四项产物）。"""

    def non_empty_dir(path: Path) -> bool:
        return path.is_dir() and any(path.iterdir())

    text = opt_dir / "2-name2text.txt"
    semantic = opt_dir / "6-name2semantic.tsv"
    return {
        "text": text.is_file() and text.stat().st_size > 0,
        "bert": non_empty_dir(opt_dir / "3-bert"),
        "cnhubert": non_empty_dir(opt_dir / "4-cnhubert"),
        "wav32k": non_empty_dir(opt_dir / "5-wav32k"),
        "semantic": semantic.is_file() and semantic.stat().st_size > 27,  # 只有表头 = 27 字节
    }


@dataclass(slots=True)
class TrainingResult:
    stage: str
    ok: bool
    detail: str = ""


class TrainingRunner:
    """在后台线程按顺序执行阶段：逐条起子进程、日志落盘、可中断。

    事件经线程安全队列回主线程（与工作台既有做法一致）：
    ``("stage", (stage_key, state))`` / ``("log", (stage_key, line))`` / ``("done", ok)``。
    """

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[str] | None = None
        self._cancel = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, stages: Sequence[StagePlan]) -> bool:
        if self.is_running:
            return False
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(tuple(stages),), name="tts-train", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """请求中断：先杀当前子进程，再让线程在阶段边界退出。"""

        self._cancel.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    def _run(self, stages: Sequence[StagePlan]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        ok = True
        for stage in stages:
            if self._cancel.is_set():
                ok = False
                break
            self.events.put(("stage", (stage.key, STAGE_RUNNING)))
            stage_ok, detail = self._run_stage(stage)
            state = STAGE_DONE if stage_ok else STAGE_FAILED
            self.events.put(("stage", (stage.key, state)))
            if not stage_ok:
                self.events.put(("log", (stage.key, f"[failed] {detail}")))
                ok = False
                break
        self.events.put(("done", ok))

    def _run_command(self, command: Command, log, stage_key: str) -> int:
        try:
            process = subprocess.Popen(
                list(command.argv),
                cwd=str(command.cwd),
                env=dict(command.env),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as error:
            log.write(f"[spawn failed] {error}\n")
            return -1
        self._process = process
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            self.events.put(("log", (stage_key, line.rstrip("\n"))))
            if self._cancel.is_set() and process.poll() is None:
                process.terminate()
        code = process.wait()
        self._process = None
        return code

    def _run_stage(self, stage: StagePlan) -> tuple[bool, str]:
        log_path = self.log_dir / f"{stage.key}.log"
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            for command in stage.commands:
                if self._cancel.is_set():
                    return False, "已中断"
                code = self._run_command(command, log, stage.key)
                if code != 0:
                    # 上游自己不看退出码；这里仍以非零为失败，便于尽早暴露环境问题
                    return False, f"退出码 {code}"
            if stage.merge is not None:
                try:
                    stage.merge()
                except OSError as error:
                    return False, f"产物合并失败：{error}"
        return True, ""
