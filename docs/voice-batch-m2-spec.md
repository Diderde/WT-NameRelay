# 语音批量 · M2 规范（vtcore 与 .vt 容器）

> 状态：**M2 冻结候选**（待用户拍板 §12 的未决项后冻结）。
> 上游：`docs/voice-batch-spec.md`（M1，已交付）。**M1 的规范字节是 M2 的不可变基准**，
> 本文件只在其上叠加容器、签名、信任与打包层，不改动 M1 的行/表规范字节语义。
> 权威实现：Rust `vtcore`（PyO3）；M1 的 Python 实现降级为**交叉验证用参考实现**。

## 0 · 范围与对应关系

| M2 交付 | 对应冻结决策（HANDOFF-M1.md §四） |
| --- | --- |
| §2–§3 `.vt` 二进制容器 | 决策 2（magic `VTBL` + 版本 + chunk TLV + 长度前缀 UTF-8 + 固定小端） |
| §4 规范字节与 vtcore 单点 | 决策 4（spec_hash 由 vtcore 单点计算，与 M1 逐字节一致） |
| §5 签名与算法编号表 | 决策 1（Ed25519 最小集 + 算法编号表，禁 `none`，RSA 不做，ML-DSA 预留） |
| §6 信任模型（TOFU） | 决策 1（TOFU 信任库） |
| §7 密钥存储 | 决策 1（OS 凭据库存主包装钥 + 项目私钥 AEAD） |
| §8 只读锁 | 决策 5（M1 不做 → M2 交付） |
| §9 manifest 与整包验证 | 决策 5（`.vtmanifest` / manifest 整包验证） |
| §10 工程格式 | 决策 7（`.vt` 为唯一工程格式：未签名可编辑、已签名只读；JSON 工程读写已移除） |

## 1 · 通用字节约定

1. **字节序**：所有多字节整数**固定小端**（little-endian），与运行平台无关。
2. **字符串**：UTF-8（不带 BOM）；落盘长度前缀写作 `u32` 字节长度 + 原始字节。
3. **记录式编码**：**复用 M1 §4.1**（`键名=字节长度:值` + `LF`，键名按 UTF-8 字节序升序，同键保持定义顺序）。
   vtcore 只需实现这一个编码器，行/表/签名/manifest 四处共用。
4. **对齐**：不做填充对齐，紧凑布局。
5. **保留字段**：写入方必须写 0；读取方必须忽略其内容。
6. **未知数据**：非关键未知 chunk 必须**原样保留**（读→写回不得丢弃）；关键未识别项必须拒绝（见 §3.3）。
7. **禁止**：禁止前导零（除数值 0 本身）、禁止科学计数法、禁止在记录值中出现 `LF`。

## 2 · `.vt` 容器布局

```
┌──────────────────────────── 文件头（16 字节） ────────────────────────────┐
│ 0  │ 4  │ magic = "VTBL"（56 54 42 4C）                                   │
│ 4  │ 2  │ format_version：u16 = 1（本规范版本）                            │
│ 6  │ 2  │ flags：u16（bit0 已签名 / bit1 含 manifest 引用 / bit2 只读建议； │
│    │    │              其余位保留 = 0）                                    │
│ 8  │ 4  │ chunk_count：u32                                                │
│ 12 │ 4  │ reserved：u32 = 0                                               │
└──────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────── chunk（重复 chunk_count 次） ────────────────┐
│ +0 │ 4  │ chunk_type：4 字节 ASCII（§3 登记表）                            │
│ +4 │ 2  │ chunk_flags：u16（bit0 = critical；其余保留 = 0）                 │
│ +6 │ 4  │ payload_len：u32                                                │
│ +10│ N  │ payload：payload_len 字节                                        │
│ +10+N│32│ chunk_hash = SHA-256(payload)                                   │
└──────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────── 尾部（36 字节） ─────────────────────────────┐
│ 0  │ 4  │ magic = "VTBE"                                                  │
│ 4  │ 32 │ file_hash = SHA-256(文件起始 → 尾部 magic 之前的全部字节)         │
└──────────────────────────────────────────────────────────────────────────┘
```

- 单个 chunk 固定开销 = `4 + 2 + 4 + 32 = 42` 字节。
- `file_hash` 覆盖文件头、全部 chunk 头与 payload 及各自 `chunk_hash` → **任一字节篡改或截断都会被检出**；
  尾部 magic 用于快速识别截断。
- 读取顺序：校验尾部 magic → 校验 `file_hash` → 逐 chunk 校验 `chunk_hash` → 解析 payload。
  任一失败即拒绝打开（错误码见 §5.5）。

### 2.4 容器错误码（`vt_*`）

读取方在任一检查失败时**拒绝打开**，并给出稳定错误码：

| 错误码 | 含义 |
| --- | --- |
| `vt_bad_magic` | 文件头 magic 不是 `VTBL` |
| `vt_unsupported_version` | `format_version` 非本规范版本 |
| `vt_bad_trailer` | 缺少 `VTBE` 尾部（多为截断） |
| `vt_truncated` | 长度不足或 chunk 越界 |
| `vt_file_hash_mismatch` | 整文件哈希不符（被改动或损坏） |
| `vt_chunk_hash_mismatch` | 单个 chunk 哈希不符 |
| `vt_unknown_critical_chunk` | 出现无法识别的关键 chunk（不得降级忽略） |
| `vt_missing_chunk` / `vt_duplicate_chunk` | 必需 chunk 缺失 / 重复出现 |
| `vt_bad_record` | 规范记录损坏（长度前缀、分隔符、UTF-8、缺 `LF`） |
| `vt_table_hash_mismatch` | `TABH.spec_hash` 与由行数据重算的表级哈希不一致 |
| `vt_row_count_mismatch` | `TABH.row_count` 与实际行数不一致 |
| `vt_signature_block_invalid` | `SIGN` chunk 长度或内容非法 |
| `vt_signature_missing` | 声明已签名但缺 `SIGN`；或对未签名文件调用验签 |
| `vt_duplicate_row_id` | 同一表内出现重复 `row_id`（编码时即拒绝） |

**命名约定**：容器层错误码统一 `vt_` 前缀；签名算法层（§5.5）使用 `sig_` 前缀。
两层可组合出现（例：`vt_signature_missing` 表示"没有签名可验"，`sig_invalid` 表示"有签名但验不过"）。

## 3 · chunk 类型登记表

### 3.1 已定义类型

| 类型 | critical | 必需 | payload 编码 | 内容 |
| --- | --- | --- | --- | --- |
| `META` | 1 | ✔ | 记录式 | `created_at` / `generator` / `key_id` / `spec_version` / `table_id` |
| `ROWS` | 1 | ✔ | 记录式（行块拼接） | 每行 = **M1 §4.2 单行规范字节原样内嵌**，按 `row_id` 升序 |
| `TABH` | 1 | ✔ | 记录式 | `row_count` / `spec_hash` / `spec_version` / `table_id` |
| `SIGN` | 1 | ○ | 定长二进制（§5.2） | 签名块；`flags.bit0=1` 时必须存在 |
| `STAT` | 0 | ✖ | 记录式 | **保留未启用**（M2 不写；状态仍走旁车，见 §8.3） |
| `EXT ` | 0 | ✖ | 自由 | 扩展位（未知键与未来特性），读取方原样保留 |

### 3.2 `ROWS` 与 M1 的关系（关键）

`ROWS` 的 payload 就是若干行规范字节的**顺序拼接**，因此：

- 每行字节与 M1 §4.2 完全一致 → `spec_hash_row` 可由块字节直接算出，无需重新编码；
- `row_id` 升序即拼接顺序（与 M1 §4.3 表级排序规则一致）；
- 未签名容器（`flags.bit0=0`）可被 M1 Python 实现无损读出并重算同一 hash。

### 3.3 未知 chunk 的处理

- `chunk_flags.bit0 = 0`：**必须原样保留**（连同 `chunk_type` / `chunk_flags` / `chunk_hash`），并在写回时置于登记表类型的后面；
- `chunk_flags.bit0 = 1`：本实现不懂则**拒绝打开**（错误码 `unknown_critical_chunk`），不得降级忽略。

## 4 · 规范字节与 vtcore 单点

1. 行级（M1 §4.2）、表级（M1 §4.3）规范字节**逐字节不变**。
2. `spec_hash_row` / `spec_hash_table` = `SHA-256(对应规范字节)`，64 位小写 hex。
3. M2 起 **vtcore 是唯一权威计算者**；Python 侧 `canonical_row_bytes` / `canonical_table_bytes`
   保留为参考实现，仅用于交叉验证（同一批黄金向量同时供 Rust 侧读取）。
4. **`key_id` 的语义（见 §12 未决项 c）**：
   - 规范字节中的 `key_id` 记录**始终写入**（M1 规则不变）；
   - 本规范**推荐**：M2 起该值仍恒为空串，签名者身份走 §5 的签名消息与 `SIGN` chunk，
     使 `spec_hash` 跨"未签名 ↔ 已签名"**保持稳定**（避免签名动作让全部产物变为 `stale`）；
   - 若采纳"填真值"方案，则**签名会改变所有行/表 hash**，`.vt.state` 中已有 `spec_hash` 全部失效 ——
     该后果必须在 UI 上明确提示。

## 5 · 签名

### 5.1 算法编号表

| 编号 | 名称 | M2 状态 |
| --- | --- | --- |
| `0x0000` | `none` | **保留且禁止使用**：读取即拒绝（`sig_alg_forbidden`） |
| `0x0001` | `Ed25519` | M2 唯一实现 |
| `0x0002–0x00FF` | 预留（含 ML-DSA 家族等 PQC） | 未实现 → 拒绝（`sig_alg_unsupported`） |
| `0x0100–0xFFFF` | 私有 / 实验 | 拒绝 |
| —— | RSA（任意长度） | **不分配编号，明确不做** |

- 未知编号**一律拒绝，不得降级**（无"尽力验证"路径）。
- 未来新增算法只占用预留区间，不得改动 `0x0001` 的字节语义。

### 5.2 `SIGN` chunk payload（定长 138 字节）

```
+0   │ 2  │ sig_alg   ：u16（§5.1 编号）
+2   │ 32 │ key_id    ：SHA-256(公钥原始字节)，原始字节形式
+34  │ 32 │ pubkey    ：Ed25519 公钥原始 32 字节
+66  │ 64 │ signature ：Ed25519 签名原始 64 字节
+130 │ 8  │ signed_at ：u64（Unix 秒；0 = 未记录）
```

强制约束：`key_id == SHA-256(pubkey)`，不符即拒绝（`key_id_mismatch`）。

### 5.3 签名消息规范字节

复用 §1.3 记录式，域分隔首行固定 `sig`：

```
sig\n
alg=1:1\n                    # 算法编号的十进制 ASCII（本例为 1）
key_id=64:<hex64>\n          # 公钥 hash 的十六进制小写
object=5:table\n             # table | manifest
object_hash=64:<hex64>\n     # = SHA-256(被签对象的规范字节)
sig_version=1:1\n
```

- 键名升序即 `alg < key_id < object < object_hash < sig_version`（`object` 为 `object_hash` 前缀，短者在前）。
- **被签对象**：
  - `object=table` → `object_hash = SHA-256(M1 §4.3 表级规范字节)`；
  - `object=manifest` → `object_hash = SHA-256(§9.2 manifest 规范字节)`。
- 被签对象是**逻辑规范字节**而非容器字节 → 重新打包容器（改 chunk 顺序、加非关键 chunk）**不破坏签名**。

### 5.4 key_id 与轮换

- `key_id = SHA-256(公钥原始 32 字节)` 的小写 hex（64 字符）；文本层用 hex，容器内用 32 字节原始值。
- 轮换：新密钥签一条 `object=rotation` 的消息（`object_hash = SHA-256(rotation 规范字节)`），
  内容含 `from_key_id` / `to_key_id` / `rotated_at`；旧私钥必须能签该消息，否则不构成有效轮换。

### 5.5 验签流程与失败码

顺序执行，首个失败即返回：

| 顺序 | 检查 | 失败码 |
| --- | --- | --- |
| 1 | `flags.bit0=1` 时 `SIGN` 必须存在 | `sig_missing` |
| 2 | `sig_alg` 已知且非 `0x0000` | `sig_alg_unsupported` / `sig_alg_forbidden` |
| 3 | `key_id == SHA-256(pubkey)` | `key_id_mismatch` |
| 4 | 表规范字节重算的 `object_hash` 与签名消息一致 | `object_hash_mismatch` |
| 5 | Ed25519 验签通过 | `sig_invalid` |
| 6 | 信任状态允许（§6） | `key_untrusted` / `key_revoked` / `key_rotated_unknown` |

## 6 · 信任模型（TOFU）

1. 首次遇到未知 `key_id`：状态 = `unverified`，**不自动信任**；UI 三选一：
   「信任并记住」/「仅本次打开」/「拒绝」。
2. 信任库：`config/vt_trust.json`（项目内 `config/` 已 gitignore；不随工程文件分发）。

```json
{
  "trust_version": 1,
  "keys": {
    "<key_id hex64>": {
      "public_key": "<64 hex>",
      "alg": 1,
      "status": "trusted",
      "label": "用户可读名",
      "first_seen": "2026-09-21T19:00:00+08:00",
      "last_seen": "2026-09-21T19:00:00+08:00",
      "note": ""
    }
  },
  "rotations": [
    {
      "table_id": "<uuid>",
      "from_key_id": "<hex64>",
      "to_key_id": "<hex64>",
      "rotated_at": "2026-09-21T19:00:00+08:00",
      "chain_sig": "<128 hex>"
    }
  ],
  "tables": { "<table_id>": "<该表当前已确认的签名者 key_id hex64>" }
}
```

3. 信任库缺失或损坏 → 视为**空库**（全部 `unverified`），不静默信任、不静默拒绝。
4. 同一 `table_id` 出现新的 `key_id` 且无对应轮换记录 → `key_rotated_unknown`（警告 + 要求明确确认）；
   在确认之前**不更新** `tables` 中该表的签名者，因此告警会持续出现，不会被一次点击掩盖。
5. 信任库**不参与**任何 hash 与签名（纯本机状态）。

## 7 · 密钥存储

1. **主包装钥**（32 字节随机）：由 **Windows DPAPI（用户范围）** 保护后落盘 `config/vt_master.key`
   （保护层留抽象接口 `MasterKeyProtector`，将来可接 Keychain / Secret Service）；
   DPAPI 密文与明文密钥不同——文件本身泄露不足以还原密钥（受当前用户凭据保护）。
2. **项目私钥**：Ed25519 只存 32 字节 seed，经主包装钥 AEAD 加密后落盘 `config/vt_keys/<key_id>.vtkey`：

```
+0  │ 4  │ magic = "VTKY"
+4  │ 2  │ version：u16 = 1
+6  │ 2  │ aead：u16 = 1（XChaCha20-Poly1305）
+8  │ 24 │ nonce（每次写入重新随机）
+32 │ 32 │ ciphertext（32 字节 seed）
+64 │ 16 │ tag
```

- **AAD = key_id 的 ASCII hex（64 字节）** → 换文件/换名即解密失败，防混淆。
- 私钥**永不**进入工程文件、容器、日志、错误消息；导出私钥需显式二次确认（M2 仅提供"备份"入口，不做恢复流程）。
3. 主包装钥丢失 → 已加密私钥不可恢复（M2 明确不做密钥托管与恢复）。

## 8 · 只读锁

1. **语义**：**已签名**（`flags.bit0=1`）的 `.vt` 本体**不可被工具改写**；任何修改都必须产出
   **新文件 + 新签名**，或在显式解锁后写回未签名工作文件（§10）。未签名容器即工作文件，可原地保存。
2. **双重实现**：
   - 文件系统层：写入完成后置 Windows 只读属性（防手滑）；
   - 应用层：写路径守卫，目标已上锁时拒绝覆盖（`vt_project.save_container` / `save_table`）。
3. **旁车不受锁影响**：状态写在工程文件旁的独立文件中（§5 规则不变），命名为
   **剥掉尾部 `.vt` 后追加 `.vt.state`**（例：`song.vt` → `song.vt.state`）；
   旧的机械追加写法（`song.vt.vt.state`）在工作格式改为 `.vt` 后会产生无意义重复，故一并纠正。
4. 解锁是显式动作（去除只读属性 + 明确提示"本文件将变为未签名"）；界面提供「解锁以编辑」入口。

## 9 · manifest 与整包验证（`.vtmanifest`）

### 9.1 包形态

采用**目录形态**（不引入 zip，避免重复造轮子）：

```
<包名>/
├── project.vt              # 容器（通常已签名）
├── <产物>.wav              # 生成的音频产物
└── project.vtmanifest      # 本文件（JSON，人可读、可 diff）
```

### 9.2 manifest 规范字节（供签名用）

```
manifest\n
created_at=<len>:<ISO8601>\n
file=<len>:<hex64 sha256>|<十进制字节数>|<POSIX 相对路径>\n   ← 同键多条，按路径升序
file_count=<len>:<十进制文件数>\n
key_id=64:<hex64>\n
manifest_version=1:1\n
table_spec_hash=64:<hex64>\n
```

- 路径必须为**相对路径 + POSIX 分隔符**，且**不得包含 `|` 与 `LF`**（违规即拒绝签名）。
- `file` 记录按路径升序排列；`file_count` = 记录条数（不含 `project.vtmanifest` 自身）。

### 9.3 验证流程与结果分类

1. 校验 manifest 自身签名（`object=manifest`）；
2. 逐个文件比对 `SHA-256` 与字节数；
3. 输出四类结果：`ok` / `missing`（清单有、磁盘无）/ `extra`（磁盘有、清单无）/ `modified`（hash 或大小不符）；
4. 产物集合**多出文件不算失败**（用户可能新增了素材），但必须在报告中列出。

## 10 · 工程格式（2026-09-22 变更：工作格式取「乙」）

1. **`.vt` 是唯一工程格式**：工作文件与成品是同一个容器。
   - **未签名**：可直接编辑，自动保存**原地写回**该容器（原子替换 + 修订号防旧覆盖新）；
   - **已签名**：写入时自动上锁（§8），打开即只读；改动需显式「解锁以编辑」或另存为新文件。
2. **JSON 工程读写已移除**：不再提供 JSON → `.vt` 的一次性导入，界面遇到 `.json` 只提示不支持。
   旧 M1 JSON 工程请用旧版本先导出 `.vt`，再在本版打开。
3. **Python 侧边界**：生产路径的编码与哈希一律以 vtcore 为准；Python 参考实现只服务测试。

## 11 · 冻结项（M2 明确不做）

RSA 与任何非 Ed25519 公钥算法；证书链 / CA / PKI；CRL / OCSP / 吊销列表；TSA 时间戳服务；
HSM / 智能卡 / 硬件密钥；多签与门限签名；密钥托管、恢复与共享；zip 或自研归档；
网络校验（在线信任服务）；信任库跨机同步；macOS / Linux 密钥库实现（仅留抽象接口）。

## 12 · 未决项（冻结前需拍板）

| # | 未决 | 建议 | 影响 |
| --- | --- | --- | --- |
| a | 是否安装 Rust 工具链（rustup + MSVC） | **安装**（本机 VS 2022 Build Tools + Windows SDK 10.0.26100 已就绪，仅缺 rustup） | 决定 M2-W1 能否开工 |
| b | vtcore 载体：PyO3 扩展 vs 独立 exe | 见下 | 影响发布链（PyInstaller 打包） |
| c | `key_id` 是否进 `spec_hash`（§4.4） | **不进**（签名身份走签名层） | 决定"签名是否让全部产物变 stale" |
| d | TOFU 首次遇到未知密钥的默认行为 | **弹窗确认**（不自动信任） | 决定首开体验与安全默认值 |

**关于 b 的两种形态**：

| | PyO3 扩展（冻结决策原意） | 独立 `vtcore.exe` + 契约 |
| --- | --- | --- |
| 集成 | 直接 `import vtcore`，零 IPC | 子进程 + 文件/stdio 契约（与 ffmpeg、CosyVoice shim 同构） |
| 发布 | 需按 CPython 3.12 / win_amd64 构建 `.pyd`，PyInstaller 需正确收集 | 直接随包附带 exe，无 ABI 耦合 |
| 代价 | 构建链（maturin）+ ABI 绑定 + 打包复杂度 | 进程启动开销（可批量模式摊薄） |
| 与本仓惯例 | 新形态 | **已有两处先例**（ffmpeg 服务、TTS 服务） |

## 13 · M2 验收判据

1. vtcore 与 M1 Python 参考实现在**全部黄金向量**上逐字节一致（含空串 key_id 场景）；
2. 容器往返：写→读→重写字节一致；篡改任一字节 / 截断 / 未知关键 chunk 均被拒绝且错误码正确；
3. 签名：正确验签通过；篡改内容、换公钥、`alg=0x0000`、未知算法编号均被拒绝；
4. TOFU：未知密钥不自动信任；撤销后拒绝；轮换无记录时告警；
5. 私钥落盘为密文；AAD 不符时解密失败；私钥不出现在日志与错误消息中；
6. 只读锁：已签名 `.vt` 被拒写；解锁需显式动作；
7. manifest：四类结果分类正确，manifest 自身被改时验签失败；
8. Python 侧封装（`.vt` 读写 / 只读锁 / 签名 / 信任库 / manifest）与 Rust 实现行为一致，接口可依赖。
