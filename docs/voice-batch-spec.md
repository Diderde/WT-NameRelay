# 语音批量生成 · M1 规范（Voice Batch Spec）

> 状态：M1（Python 临时实现）；**权威解释器为 M2 的 Rust `vtcore`（PyO3）**。
> 本文件定义行模型语义、身份三分离、`spec_hash` 规范字节、旁车文件 schema 与文件名规则引用。
> 任何实现（Python 临时版 / Rust vtcore）必须与本文件的**规范字节**逐字节一致，否则 hash 不可互换。

## 1. 术语与身份三分离

| 名称 | 类型 | 生命周期 | 说明 |
| --- | --- | --- | --- |
| `table_id` | 随机 UUIDv4（小写带连字符） | **永久**，随表格生灭 | 一张语音批处理表（一次作业）的身份；旁车 `.vt.state` 用它关联 |
| `key_id` | `SHA-256(公钥)` 的 64 位小写 hex | 可轮换（M2 引入签名后） | 签名者密钥身份；**M1 恒为空**（不签名） |
| `row_id` | 随机 UUIDv4（小写带连字符） | **永久**，与行同生灭 | 行的唯一身份：改文案、改模型、重排、重命名都**不改** `row_id` |

约束：
1. `row_id` 一经分配永不复用、永不重排后重新生成——排序只影响展示与编码顺序，不改变身份。
2. 复制行 = 新 `row_id`；粘贴覆盖 = 保留目标行 `row_id`，仅替换内容字段。
3. 删除行 = 从表中移除；旁车文件中该行状态可保留（孤儿状态按 `table_id` 关联，可被清理）。

## 2. 行模型字段（VoiceRow）

创作内容字段（进入 `spec_hash`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `row_id` | str(UUID) | ✔ | 永久身份 |
| `name` | str | ✔ | 目标文件名（**不含扩展名**），受 ValidatorProfile 校验 |
| `text` | str | ✔ | 待合成文本（UTF-8，允许空串表示仅做占位） |
| `language` | str | ✔ | 语言标签，WT_DEFAULT 下为 `zh` / `en` |
| `voice` | str | ○ | 音色/说话人标识（后端相关：GPT-SoVITS 参考音频键、CosyVoice 音色名） |
| `emotion` | str | ○ | 情绪/风格标识 |
| `speed` | int | ○ | 语速，**千分比整数**（1000 = 1.0×），避免浮点进入 hash |
| `pitch` | int | ○ | 音高，**音分整数**（0 = 原调） |
| `volume` | int | ○ | 音量，**千分比整数**（1000 = 原音量） |
| `seed` | int | ○ | 采样种子；`0` 表示由后端随机 |
| `extra` | map[str,str] | ○ | 后端扩展参数；键值均为字符串，按规范字节参与 hash |

非内容字段（**不进入** `spec_hash`）：
`JobState` / `ArtifactState` / `output_hash` / `audio_path` / `duration_ms` / 生成时间 / 错误信息 / UI 状态（选中、滚动、焦点）。

> 判据：**只影响"要生成什么声音"的字段进 hash；只影响"生成得怎么样/存在哪"的字段不进 hash。**

## 3. 状态双轴与 UI 三态

| 轴 | 取值 | 含义 |
| --- | --- | --- |
| `JobState` | `idle` / `queued` / `generating` / `failed` / `cancelled` | 本次生成作业的进展（瞬时，不持久化语义依赖） |
| `ArtifactState` | `missing` / `current` / `stale` / `modified` | 产物与当前创作内容的一致性 |

`ArtifactState` 判定（实现须完全按此顺序）：

1. 音频文件不存在 → `missing`
2. 文件存在，但记录 `output_hash` 与**当前文件实际 SHA-256** 不一致 → `modified`（外部改动过产物）
3. 文件存在且 hash 一致，但记录 `spec_hash` ≠ 该行当前 `spec_hash` → `stale`（**"需要重新生成"**）
4. 否则 → `current`

UI 三态由两轴合成（仅展示用，不入库）：

| UI 状态 | 合成条件 |
| --- | --- |
| 未完成 | `ArtifactState = missing` 或 `JobState ∈ {failed, cancelled}` |
| 正在生成 | `JobState ∈ {queued, generating}` |
| 已完成 | `ArtifactState ∈ {current, stale, modified}`；其中 `stale` 额外显示"需要重新生成"徽章 |

## 4. `spec_hash` 规范字节（**逐字节规范**）

### 4.1 编码总则

1. 字符编码 **UTF-8，不带 BOM**；行分隔符固定 `LF`（`\n`）；文件末尾**保留**最后一个 `LF`。
2. 所有"键=值"记录写作：`键名=字节长度:值字节`，其中长度是 **UTF-8 字节数**的十进制 ASCII（无前导零，`0` 合法）。
3. 记录按**键名升序**（按 UTF-8 字节序 / 等价于码点序）排列；**不写空格**、不写引号、不做转义。
4. 整数一律十进制 ASCII（负号仅在允许负值处出现）；**禁止**科学计数法、禁止前导零（`0` 本身除外）。
5. 布尔写作 `0` / `1`。
6. 未知键（前向兼容）：一并参与排序与编码；解释器须原样保留。

### 4.2 单行规范字节

```
row\n
key_id=64:<hex64 或 空>\n        # M1 恒为空串（长度 0）
language=2:zh\n
name=5:radio\n
row_id=36:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n
text=5:你好\n
...（其余内容字段按 key 升序插入；可选字段缺省则**不写该记录**）
```

- 首行固定字面量 `row`，用于域分隔（防止跨对象 hash 混淆）。
- `spec_hash_row` = `SHA-256(上述字节)`，输出 64 位小写 hex。

### 4.3 表级规范字节

```
table\n
key_id=64:<hex64 或 空>\n
row_count=<len>:<十进制行数>\n
row_hash=64:<第 1 个 row_id 升序行的 spec_hash_row>\n
row_hash=64:<...>\n
spec_version=1:1\n
table_id=36:<uuid>\n
（示例即**实际顺序**：所有记录按键名升序；`row_hash` 多条同键时保持 row_id 升序的稳定顺序。）
```

- 行按 `row_id`（字符串）升序；**同一键名重复出现是允许且必要的**（`row_hash` 多行）。
- `spec_hash_table` = `SHA-256(上述字节)`。

### 4.4 实现要求

- M1 Python 实现：`app/models/voice_table.py` 的 `canonical_row_bytes()` / `canonical_table_bytes()`，并在函数 docstring 标注
  `# 待 vtcore 替换：规范字节见 docs/voice-batch-spec.md §4`。
- 规范字节稳定性由**固定向量**锁定（给定行字段 → 期望字节串 → 期望 hash 前若干位），
  Python 与 Rust 两侧共用同一批向量。

## 5. 旁车文件 `*.vt.state`（M1）

- 位置：与工程文件同目录，剥掉尾部 `.vt` 后追加 `.vt.state`（例：`project.vt` → `project.vt.state`，
  不会出现 `project.vt.vt.state`）。
- 格式：JSON（UTF-8、LF、`ensure_ascii=false`、缩进 2、键序按写入方稳定输出即可——**不参与任何 hash**）。
- **不签名、可随时删除**；缺失视为全部 `missing`；按 `table_id` 关联，内容与主工程文件解耦。
- 只读约束：任何实现都**不得**把生成状态写回主工程文件（工程文件只存创作内容）。

```json
{
  "state_version": 1,
  "table_id": "3f2b1c4e-....",
  "written_at": "2026-09-21T13:00:00+08:00",
  "rows": {
    "<row_id>": {
      "job": "idle",
      "artifact": "current",
      "spec_hash": "<64 hex>",
      "output_hash": "<64 hex，音频文件字节的 SHA-256>",
      "audio_path": "out/radio.wav",
      "duration_ms": 1830,
      "generator": { "backend": "gpt-sovits", "model": "v2Pro", "params_hash": "<64 hex>" },
      "generated_at": "2026-09-21T12:58:03+08:00"
    },
    "<row_id2>": {
      "job": "failed",
      "artifact": "missing",
      "error": { "code": "backend_timeout", "message": "推理超时" }
    }
  }
}
```

字段说明：`audio_path` 为**相对工程文件目录**的路径（POSIX 分隔符）；`backend` 取 `gpt-sovits` / `cosyvoice3-gguf`；
`params_hash` 为后端参数（与创作内容无关的推理设置）的 SHA-256；`error` 仅在失败时出现。

## 6. 文件名规则（ValidatorProfile）

架构：**可配置 Profile，产品只发布 WT_DEFAULT 一个**。

```
ValidatorProfile:
  profile_id: str          # "wt_default"
  display_name: str
  extension: str           # ".wav"
  stem_pattern: str        # 正则（ASCII）
  ascii_only: bool
  max_stem_bytes: int
  forbidden_chars: str
  case_sensitive: bool
  allow_rename: bool       # 冲突时是否自动追加序号
  collision_suffix: str    # "_%02d"
```

`WT_DEFAULT`（M1 产品内置）：

- 扩展名：`.wav`
- 名称主体：`^[A-Za-z0-9_]+$`（ASCII 字母/数字/下划线），长度 1–64 字节
- 禁止：路径分隔符、`: * ? " < > |`、控制字符、首尾空格与点号、Windows 保留名（`CON`、`PRN`、`AUX`、`NUL`、`COM1..9`、`LPT1..9`）
- 大小写：不敏感查重（比较时 `casefold`），保留原样落盘
- 冲突：默认拒绝并要求改名；`allow_rename=True` 时按 `name_01.wav`、`name_02.wav` 递增

命名素材与既有规则引用：
1. 名称库与分组语义沿用 `app/services/bank_name_repository.py`（内置 JSON、`categories → countries` 结构）与
   `app/services/bank_filename_parser.py`（`_crew_dialogs_(common|ground)_<name>.assets.bank` / `.bank` 的严格解析顺序：
   **先匹配更长后缀 `.assets.bank`，再匹配 `.bank`**）。
2. 需与既有产物同目录共存时，校验器只负责**单文件名合法性 + 目录内冲突**，不改变既有文件的命名。
3. 后续若出现 WT 官方新命名格式，新增 Profile 即可，不改 WT_DEFAULT 行为。

## 7. M1 明确不做（冻结）

签名（Ed25519）、只读锁、TOFU 信任库、`.vt` 二进制容器、`.vtmanifest`、整包 manifest 验证——
全部后置 M2；`key_id` 在 M1 恒为空串，且规范字节中**保留该记录**（长度 0），以便 M2 无痛升级。
M2 的字节级规范（`.vt` 容器 / 签名 / 信任库 / 只读锁 / manifest / 一次性导入）见
`docs/voice-batch-m2-spec.md`。
