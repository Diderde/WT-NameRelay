# vtcore（Rust / PyO3）

WT-NameRelay 语音批量**规范字节的权威实现**（M2）。

- 规范：`docs/voice-batch-spec.md` §4（M1 逐字节基准，不得改动）、`docs/voice-batch-m2-spec.md`（M2 容器 / 签名）
- 分工：Python 侧 `app/models/voice_table.py` 保留为**参考实现**（仅交叉验证用）；
  生产路径以本 crate 为准（M2-W5 接入）。
- 纯 Rust 核心在 `src/canonical.rs`（不依赖 pyo3），`src/lib.rs` 只是薄胶水。

## 构建（开发）

```powershell
# 前置：Rust 工具链（rustup）+ maturin（已列入 requirements-dev.txt）
cd vtcore
..\.venv\Scripts\python.exe -m maturin develop --release
```

构建后 `import vtcore` 即可用；未构建时应用仍可正常运行，但签名 / `.vt` 容器 /
整包校验不可用（「关于与许可」页会显式提示）。

## 预编译扩展（随源码附带）

`wheels/vtcore-0.1.0-cp312-abi3-win_amd64.whl` 是同一份源码的 **abi3 官方构建**（跨 CPython 3.12+
通用）。仓库直接附带，`start.bat` 会自动安装它 —— **使用者不需要 Rust 工具链，也不需要联网**；
本地件缺失时才会回退到 Release 下载。

> 自行构建可分发 wheel 时必须带路径重映射（`--remap-path-prefix`），否则依赖 crate 的 panic
> 位置字符串会把构建机用户名与 `.cargo` 路径写进 `.pyd`；maturin 的 SBOM 还会带项目绝对路径，
> 需用 `tools/sanitize_wheel.py` 中和（用法：`python tools/sanitize_wheel.py <源.whl> <输出.whl>`）。

## 验证

规范字节以 `docs/voice-batch-spec.md` §4 的固定向量为基准：Python 侧参考实现与本 crate
对同一批向量逐字节对拍，构建后自动生效。

## 暴露的接口

### 规范字节（M2-W1）

| 函数 | 说明 |
| --- | --- |
| `canonical_row_bytes(row: dict, key_id: str = "") -> bytes` | 单行规范字节（§4.2） |
| `canonical_table_bytes(row_hashes, table_id, key_id="", spec_version=1) -> bytes` | 表级规范字节（§4.3） |
| `spec_hash_row(row, key_id="") -> str` | 行 `spec_hash`（64 位小写 hex） |
| `spec_hash_table(row_hashes, table_id, key_id="", spec_version=1) -> str` | 表级 `spec_hash` |
| `spec_hash_bytes(data: bytes) -> str` | 任意字节 SHA-256 |
| `version() -> str` | 绑定版本探针 |

### 签名（M2-W2，`m2-spec` §5）

| 函数 / 常量 | 说明 |
| --- | --- |
| `generate_keypair() -> dict` | 生成 Ed25519 密钥对：`{seed, public_key, key_id}`（均 hex） |
| `public_key_from_seed(seed_hex) -> str` | 由种子推导公钥 |
| `key_id_from_public_key(public_key_hex) -> str` | `key_id = SHA-256(公钥)` 的 hex |
| `algorithm_name(alg) -> str` | 算法编号 → 名称；`none` / 未知编号报错 |
| `signing_message_hex(alg, key_id, object, object_hash) -> str` | 签名消息规范字节（§5.3）的 hex |
| `sign_object(seed_hex, object, object_bytes, signed_at=0) -> dict` | 生成签名块；`signed_at=0` 表示取当前时间 |
| `verify_object(object, object_bytes, signature) -> None` | 验签；失败抛 `ValueError("错误码: 说明")` |
| `ALG_NONE` / `ALG_ED25519` / `SIG_VERSION` | 常量：`0` / `1` / `1`（`none` 保留且禁止） |

被签对象是**逻辑规范字节**（表级规范字节或 manifest 规范字节），不是容器字节：
重新打包容器不会破坏签名。失败码见 `docs/voice-batch-m2-spec.md` §5.5。

### `.vt` 容器（M2-W3，`m2-spec` §2–§3）

| 函数 / 常量 | 说明 |
| --- | --- |
| `encode_container(document: dict) -> bytes` | 编码容器；行会按 `row_id` 升序落盘 |
| `parse_container(data: bytes) -> dict` | 解析容器（结构 + 自洽校验；**不做信任判定**） |
| `verify_container_signature(data: bytes) -> None` | 解出文档并验签；失败抛 `ValueError` |
| `row_id_of_row_bytes(block: bytes) -> str` | 从一行规范字节解析 `row_id` |
| `FORMAT_VERSION` / `FLAG_SIGNED` / `FLAG_HAS_MANIFEST` / `CHUNK_CRITICAL` | 容器常量（`1` / `1` / `2` / `1`） |

`document` 字典（`parse_container` 返回同形，另有 `table_hash`、`is_signed`）：

```python
{
    "table_id": "...", "spec_version": 1, "key_id": "",   # key_id 建议留空（§4.4）
    "created_at": "2026-09-21T19:30:00+08:00", "generator": "WT-NameRelay/0.1",
    "rows": [b"row\nkey_id=0:\\n...", ...],               # 每行 = M1 §4.2 规范字节
    "signature": {...},                                   # 可选，见签名小节
    "extras": [{"kind": "NOTE", "flags": 0, "payload": b"..."}],   # 可选，未知非关键 chunk
}
```

完整性是双层的：每个 chunk 带 `SHA-256(payload)`，尾部再带整文件哈希（覆盖 header 与全部 chunk）；
另外 `TABH.spec_hash` 必须与由行数据重算的表级哈希一致。错误码（`vt_*`）见 `m2-spec` §2.4。

### 密钥封装（M2-W4，`m2-spec` §7）

| 函数 / 常量 | 说明 |
| --- | --- |
| `wrap_project_key(master_hex, key_id_hex, seed_hex) -> bytes` | 用主包装钥封装种子（每次重新随机 nonce） |
| `unwrap_project_key(master_hex, key_id_hex, blob) -> str` | 解出种子 hex；主包装钥 / `key_id` / 文件任一不符即失败 |
| `KEY_BLOB_MAGIC` / `KEY_BLOB_VERSION` / `KEY_BLOB_LEN` / `AEAD_XCHACHA20_POLY1305` | 密钥文件常量（`VTKY` / `1` / `80` / `1`） |

封装格式：`VTKY` + 版本 + AEAD 编号 + 24 字节 nonce + 密文（32 字节 seed）+ 16 字节标签；
**AAD = `key_id` 的 ASCII hex**（换名即解密失败）。主包装钥的获取（DPAPI / 凭据库）与
信任库（TOFU）在 Python 侧：`app/services/vt_key_store.py`、`app/services/vt_trust_store.py`。

### manifest 与工程文件（M2-W5，`m2-spec` §8–§10）

| 函数 / 常量 | 说明 |
| --- | --- |
| `manifest_canonical_bytes(created_at, key_id, table_spec_hash, files) -> bytes` | `.vtmanifest` 规范字节（§9.2）；`files` 为 `[{path, sha256, size}]` |
| `hash_bytes(data) -> str` | 文件内容 SHA-256（与表/行哈希同一实现） |
| `MANIFEST_VERSION` | 清单版本常量（`1`） |

签名与验签复用上面的 `sign_object` / `verify_object`，被签对象类型为 `manifest`。
Python 侧对应封装：`app/services/vt_manifest.py`（整包四类结果验证）、
`app/services/vt_project.py`（`.vt` 读写、只读锁、M1 JSON 一次性导入）。

**M2 已完成**：规范字节 / 签名 / 容器 / 信任库 / 密钥封装 / manifest / 只读锁 / JSON 迁移全部落地。
