// Copyright (C) 2026 Diderde
// SPDX-License-Identifier: GPL-3.0-only
//! vtcore：语音批量规范字节的权威实现（PyO3 绑定）。
//!
//! 规范见 `docs/voice-batch-spec.md` §4（M1，逐字节基准）与 `docs/voice-batch-m2-spec.md`（M2）。
//! 本模块只做「薄胶水」：把 Python 传入的行/表结构翻译成 [`canonical`] 的纯 Rust 类型。

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use sha2::{Digest, Sha256};

pub mod canonical;
pub mod container;
pub mod hex;
pub mod keystore;
pub mod manifest;
pub mod sign;

use canonical::{RowFields, SPEC_VERSION};
use hex::hex_lower;

/// 取字典里的字符串字段（缺失或 None → None）。
fn opt_str(row: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match row.get_item(key)? {
        Some(value) if !value.is_none() => Ok(Some(value.extract::<String>()?)),
        _ => Ok(None),
    }
}

/// 取字典里的整数字段（缺失或 None → None）。
fn opt_int(row: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<i64>> {
    match row.get_item(key)? {
        Some(value) if !value.is_none() => Ok(Some(value.extract::<i64>()?)),
        _ => Ok(None),
    }
}

/// 把 Python 行字典翻译为 [`RowFields`]（缺省值语义与 Python 参考实现一致）。
fn row_from_dict(row: &Bound<'_, PyDict>) -> PyResult<RowFields> {
    let extra = match row.get_item("extra")? {
        Some(value) if !value.is_none() => value.extract::<HashMap<String, String>>()?,
        _ => HashMap::new(),
    };
    let mut extra_pairs: Vec<(String, String)> = extra.into_iter().collect();
    extra_pairs.sort_by(|left, right| left.0.as_bytes().cmp(right.0.as_bytes()));

    Ok(RowFields {
        row_id: opt_str(row, "row_id")?.unwrap_or_default(),
        name: opt_str(row, "name")?.unwrap_or_default(),
        text: opt_str(row, "text")?.unwrap_or_default(),
        language: opt_str(row, "language")?,
        voice: opt_str(row, "voice")?,
        emotion: opt_str(row, "emotion")?,
        speed: opt_int(row, "speed")?,
        pitch: opt_int(row, "pitch")?,
        volume: opt_int(row, "volume")?,
        seed: opt_int(row, "seed")?,
        extra: extra_pairs,
    })
}

/// 行哈希对的严格解析：每项必须是 `(row_id, spec_hash_row)` 二元组。
fn parse_row_hashes(row_hashes: &[(String, String)]) -> PyResult<Vec<(String, String)>> {
    for (row_id, digest) in row_hashes {
        if row_id.is_empty() {
            return Err(PyValueError::new_err("row_hash 条目的 row_id 不得为空"));
        }
        if digest.len() != 64 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(PyValueError::new_err(
                "row_hash 条目的 spec_hash_row 必须是 64 位十六进制",
            ));
        }
    }
    Ok(row_hashes.to_vec())
}

fn parse_spec_version(spec_version: i64) -> PyResult<i64> {
    if spec_version < 1 {
        return Err(PyValueError::new_err("spec_version 必须 >= 1"));
    }
    Ok(spec_version)
}

/// 单行规范字节（§4.2）→ `bytes`。
#[pyfunction]
#[pyo3(signature = (row, key_id = ""))]
fn canonical_row_bytes<'py>(
    py: Python<'py>,
    row: &Bound<'py, PyDict>,
    key_id: &str,
) -> PyResult<Bound<'py, PyBytes>> {
    let fields = row_from_dict(row)?;
    Ok(PyBytes::new(py, &canonical::canonical_row_bytes(&fields, key_id)))
}

/// 表级规范字节（§4.3）→ `bytes`。
#[pyfunction]
#[pyo3(signature = (row_hashes, table_id, key_id = "", spec_version = SPEC_VERSION))]
fn canonical_table_bytes<'py>(
    py: Python<'py>,
    row_hashes: Vec<(String, String)>,
    table_id: &str,
    key_id: &str,
    spec_version: i64,
) -> PyResult<Bound<'py, PyBytes>> {
    let pairs = parse_row_hashes(&row_hashes)?;
    let version = parse_spec_version(spec_version)?;
    Ok(PyBytes::new(
        py,
        &canonical::canonical_table_bytes(&pairs, table_id, key_id, version),
    ))
}

/// 任意字节的 SHA-256（64 位小写 hex）。
#[pyfunction]
fn spec_hash_bytes(data: &[u8]) -> String {
    hex_lower(&Sha256::digest(data))
}

/// 行 `spec_hash`（§4.2）。
#[pyfunction]
#[pyo3(signature = (row, key_id = ""))]
fn spec_hash_row(row: &Bound<'_, PyDict>, key_id: &str) -> PyResult<String> {
    let fields = row_from_dict(row)?;
    Ok(hex_lower(&Sha256::digest(canonical::canonical_row_bytes(
        &fields, key_id,
    ))))
}

/// 表级 `spec_hash`（§4.3）。
#[pyfunction]
#[pyo3(signature = (row_hashes, table_id, key_id = "", spec_version = SPEC_VERSION))]
fn spec_hash_table(
    row_hashes: Vec<(String, String)>,
    table_id: &str,
    key_id: &str,
    spec_version: i64,
) -> PyResult<String> {
    let pairs = parse_row_hashes(&row_hashes)?;
    let version = parse_spec_version(spec_version)?;
    Ok(hex_lower(&Sha256::digest(canonical::canonical_table_bytes(
        &pairs, table_id, key_id, version,
    ))))
}

/// 版本探针（供 Python 侧确认绑定已就绪）。
#[pyfunction]
fn version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

/// 签名失败 → `ValueError("错误码: 说明")`（错误码见 m2-spec §5.5）。
fn sig_value_error(error: sign::SigError) -> PyErr {
    PyValueError::new_err(format!("{}: {}", error.code(), error.message()))
}

/// 当前 Unix 秒（`signed_at`）。
fn now_unix() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|value| value.as_secs())
        .unwrap_or(0)
}

/// 生成 Ed25519 密钥对 → `{"seed": hex, "public_key": hex, "key_id": hex}`。
#[pyfunction]
fn generate_keypair(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let seed = sign::generate_seed().map_err(sig_value_error)?;
    let public_key = sign::public_key_of(&seed);
    let key_id = sign::key_id_of(&public_key);
    let out = PyDict::new(py);
    out.set_item("seed", sign::hex_lower(&seed))?;
    out.set_item("public_key", sign::hex_lower(&public_key))?;
    out.set_item("key_id", sign::hex_lower(&key_id))?;
    Ok(out.unbind())
}

/// 由种子推出公钥 hex。
#[pyfunction]
fn public_key_from_seed(seed_hex: &str) -> PyResult<String> {
    let seed = sign::parse_hex32(seed_hex).map_err(sig_value_error)?;
    Ok(sign::hex_lower(&sign::public_key_of(&seed)))
}

/// `key_id = SHA-256(公钥)` 的 hex（§5.4）。
#[pyfunction]
fn key_id_from_public_key(public_key_hex: &str) -> PyResult<String> {
    let public_key = sign::parse_hex32(public_key_hex).map_err(sig_value_error)?;
    Ok(sign::hex_lower(&sign::key_id_of(&public_key)))
}

/// 算法编号 → 名称（`none` / `ed25519` / 未知则报错）。
#[pyfunction]
fn algorithm_name(alg: u16) -> PyResult<String> {
    sign::check_alg(alg).map_err(sig_value_error)?;
    Ok("ed25519".to_string())
}

/// 签名消息规范字节（§5.3）→ hex（便于字节级核对）。
#[pyfunction]
fn signing_message_hex(alg: u16, key_id_hex: &str, object: &str, object_hash_hex: &str) -> PyResult<String> {
    sign::check_alg(alg).map_err(sig_value_error)?;
    Ok(sign::hex_lower(&sign::signing_message(
        alg,
        key_id_hex,
        object,
        object_hash_hex,
    )))
}

/// 对被签对象的规范字节签名 → 签名块字典（`m2-spec` §5.2 的字段，hex 文本层）。
#[pyfunction]
#[pyo3(signature = (seed_hex, object, object_bytes, signed_at = 0))]
fn sign_object(
    py: Python<'_>,
    seed_hex: &str,
    object: &str,
    object_bytes: &[u8],
    signed_at: u64,
) -> PyResult<Py<PyDict>> {
    let seed = sign::parse_hex32(seed_hex).map_err(sig_value_error)?;
    let stamp = if signed_at == 0 { now_unix() } else { signed_at };
    let block = sign::sign_object(&seed, object, object_bytes, stamp);
    let out = PyDict::new(py);
    out.set_item("alg", block.alg)?;
    out.set_item("key_id", sign::hex_lower(&block.key_id))?;
    out.set_item("public_key", sign::hex_lower(&block.public_key))?;
    out.set_item("signature", sign::hex_lower(&block.signature))?;
    out.set_item("signed_at", block.signed_at)?;
    Ok(out.unbind())
}

/// 签名块字典 → `SignatureBlock`。
fn signature_block_from_dict(signature: &Bound<'_, PyDict>) -> PyResult<sign::SignatureBlock> {
    let alg: u16 = signature
        .get_item("alg")?
        .ok_or_else(|| PyValueError::new_err("sig_bad_block: 缺少 alg"))?
        .extract()?;
    let key_id_hex: String = signature
        .get_item("key_id")?
        .ok_or_else(|| PyValueError::new_err("sig_bad_block: 缺少 key_id"))?
        .extract()?;
    let public_key_hex: String = signature
        .get_item("public_key")?
        .ok_or_else(|| PyValueError::new_err("sig_bad_block: 缺少 public_key"))?
        .extract()?;
    let signature_hex: String = signature
        .get_item("signature")?
        .ok_or_else(|| PyValueError::new_err("sig_bad_block: 缺少 signature"))?
        .extract()?;
    let signed_at: u64 = match signature.get_item("signed_at")? {
        Some(value) if !value.is_none() => value.extract()?,
        _ => 0,
    };
    let raw_signature = sign::parse_hex(&signature_hex).map_err(sig_value_error)?;
    let signature_bytes: [u8; 64] = raw_signature
        .try_into()
        .map_err(|_| sig_value_error(sign::SigError::BadLength))?;
    Ok(sign::SignatureBlock {
        alg,
        key_id: sign::parse_hex32(&key_id_hex).map_err(sig_value_error)?,
        public_key: sign::parse_hex32(&public_key_hex).map_err(sig_value_error)?,
        signature: signature_bytes,
        signed_at,
    })
}

/// `SignatureBlock` → Python 字典（hex 文本层）。
fn signature_block_to_dict(py: Python<'_>, block: &sign::SignatureBlock) -> PyResult<Py<PyDict>> {
    let out = PyDict::new(py);
    out.set_item("alg", block.alg)?;
    out.set_item("key_id", sign::hex_lower(&block.key_id))?;
    out.set_item("public_key", sign::hex_lower(&block.public_key))?;
    out.set_item("signature", sign::hex_lower(&block.signature))?;
    out.set_item("signed_at", block.signed_at)?;
    Ok(out.unbind())
}

/// 校验签名块字典；通过返回 `None`，失败抛 `ValueError("错误码: 说明")`。
#[pyfunction]
#[pyo3(signature = (object, object_bytes, signature))]
fn verify_object(object: &str, object_bytes: &[u8], signature: &Bound<'_, PyDict>) -> PyResult<()> {
    let block = signature_block_from_dict(signature)?;
    sign::verify_object(object, object_bytes, &block).map_err(sig_value_error)
}

/// 容器错误 → `ValueError("错误码: 说明")`。
fn vt_value_error(error: container::VtError) -> PyErr {
    PyValueError::new_err(format!("{}: {}", error.code(), error.message()))
}

fn read_bytes_list(value: &Bound<'_, PyAny>) -> PyResult<Vec<Vec<u8>>> {
    let mut out: Vec<Vec<u8>> = Vec::new();
    for item in value.try_iter()? {
        out.push(item?.extract::<Vec<u8>>()?);
    }
    Ok(out)
}

/// 编码 `.vt` 容器 → `bytes`（文档字典见 `vtcore/README.md`）。
#[pyfunction]
fn encode_container(py: Python<'_>, document: &Bound<'_, PyDict>) -> PyResult<Py<PyBytes>> {
    let mut doc = container::VtDocument::new(
        &opt_str(document, "table_id")?.unwrap_or_default(),
        &opt_str(document, "created_at")?.unwrap_or_default(),
        &opt_str(document, "generator")?.unwrap_or_default(),
    );
    doc.spec_version = opt_int(document, "spec_version")?.unwrap_or(1);
    doc.key_id = opt_str(document, "key_id")?.unwrap_or_default();
    if let Some(rows) = document.get_item("rows")? {
        if !rows.is_none() {
            doc.rows = read_bytes_list(&rows)?;
        }
    }
    if let Some(signature) = document.get_item("signature")? {
        if !signature.is_none() {
            let dict = signature.cast::<PyDict>()?;
            doc.signature = Some(signature_block_from_dict(dict)?);
        }
    }
    if let Some(extras) = document.get_item("extras")? {
        if !extras.is_none() {
            for item in extras.try_iter()? {
                let entry = item?.cast::<PyDict>()?.clone();
                let kind_text = opt_str(&entry, "kind")?.unwrap_or_default();
                let kind_bytes = kind_text.as_bytes();
                if kind_bytes.len() != 4 {
                    return Err(PyValueError::new_err("vt_bad_chunk_kind: chunk 类型必须是 4 字节 ASCII"));
                }
                doc.extras.push(container::RawChunk {
                    kind: [kind_bytes[0], kind_bytes[1], kind_bytes[2], kind_bytes[3]],
                    flags: opt_int(&entry, "flags")?.unwrap_or(0) as u16,
                    payload: match entry.get_item("payload")? {
                        Some(value) if !value.is_none() => value.extract::<Vec<u8>>()?,
                        _ => Vec::new(),
                    },
                });
            }
        }
    }
    let bytes = container::encode(&doc).map_err(vt_value_error)?;
    Ok(PyBytes::new(py, &bytes).unbind())
}

/// 解析 `.vt` 容器 → 文档字典（结构 + 自洽校验；信任判定由调用方负责）。
#[pyfunction]
fn parse_container(py: Python<'_>, data: &[u8]) -> PyResult<Py<PyDict>> {
    let doc = container::decode(data).map_err(vt_value_error)?;
    let out = PyDict::new(py);
    out.set_item("flags", doc.flags)?;
    out.set_item("table_id", doc.table_id.clone())?;
    out.set_item("spec_version", doc.spec_version)?;
    out.set_item("key_id", doc.key_id.clone())?;
    out.set_item("created_at", doc.created_at.clone())?;
    out.set_item("generator", doc.generator.clone())?;
    out.set_item("table_hash", doc.table_hash.clone())?;
    out.set_item("is_signed", doc.is_signed())?;
    let rows: Vec<Py<PyBytes>> = doc
        .rows
        .iter()
        .map(|block| PyBytes::new(py, block).unbind())
        .collect();
    out.set_item("rows", rows)?;
    match doc.signature.as_ref() {
        Some(block) => out.set_item("signature", signature_block_to_dict(py, block)?)?,
        None => out.set_item("signature", py.None())?,
    }
    let extras = pyo3::types::PyList::empty(py);
    for extra in &doc.extras {
        let entry = PyDict::new(py);
        entry.set_item("kind", String::from_utf8_lossy(&extra.kind).to_string())?;
        entry.set_item("flags", extra.flags)?;
        entry.set_item("payload", PyBytes::new(py, &extra.payload))?;
        extras.append(entry)?;
    }
    out.set_item("extras", extras)?;
    Ok(out.unbind())
}

/// 校验容器内签名（解出文档 → 验签）；通过返回 `None`。
#[pyfunction]
fn verify_container_signature(data: &[u8]) -> PyResult<()> {
    let doc = container::decode(data).map_err(vt_value_error)?;
    doc.verify_signature().map_err(vt_value_error)
}

/// 由一行规范字节解析 `row_id`。
#[pyfunction]
fn row_id_of_row_bytes(block: &[u8]) -> PyResult<String> {
    container::row_id_of(block).map_err(vt_value_error)
}

/// 由一行规范字节解析出字段字典（`canonical_row_bytes` 的逆操作；供只读查看 `.vt`）。
#[pyfunction]
fn parse_row_bytes(py: Python<'_>, block: &[u8]) -> PyResult<Py<PyDict>> {
    let row = canonical::parse_row_bytes(block)
        .map_err(|error| PyValueError::new_err(format!("vt_bad_record: {error:?}")))?;
    let out = PyDict::new(py);
    out.set_item("row_id", row.row_id)?;
    out.set_item("name", row.name)?;
    out.set_item("text", row.text)?;
    out.set_item("language", row.language)?;
    out.set_item("voice", row.voice)?;
    out.set_item("emotion", row.emotion)?;
    out.set_item("speed", row.speed)?;
    out.set_item("pitch", row.pitch)?;
    out.set_item("volume", row.volume)?;
    out.set_item("seed", row.seed)?;
    out.set_item("key_id", row.key_id)?;
    let extra = PyDict::new(py);
    for (key, value) in &row.extra {
        extra.set_item(key, value)?;
    }
    out.set_item("extra", extra)?;
    let unknown = PyDict::new(py);
    for (key, value) in &row.unknown {
        unknown.set_item(key, value)?;
    }
    out.set_item("unknown", unknown)?;
    Ok(out.unbind())
}

/// 密钥封装错误 → `ValueError("错误码: 说明")`。
fn key_value_error(error: keystore::KeyError) -> PyErr {
    PyValueError::new_err(format!("{}: {}", error.code(), error.message()))
}

/// 用主包装钥封装 32 字节种子 → 密钥文件字节（`m2-spec` §7）。
#[pyfunction]
fn wrap_project_key<'py>(
    py: Python<'py>,
    master_hex: &str,
    key_id_hex: &str,
    seed_hex: &str,
) -> PyResult<Bound<'py, PyBytes>> {
    let master = sign::parse_hex32(master_hex).map_err(sig_value_error)?;
    let seed = sign::parse_hex32(seed_hex).map_err(sig_value_error)?;
    let blob = keystore::wrap_seed(&master, key_id_hex, &seed).map_err(key_value_error)?;
    Ok(PyBytes::new(py, &blob))
}

/// 解出种子 hex；主包装钥不符 / `key_id` 不符 / 文件被改动都会失败。
#[pyfunction]
fn unwrap_project_key(master_hex: &str, key_id_hex: &str, blob: &[u8]) -> PyResult<String> {
    let master = sign::parse_hex32(master_hex).map_err(sig_value_error)?;
    let seed = keystore::unwrap_seed(&master, key_id_hex, blob).map_err(key_value_error)?;
    Ok(sign::hex_lower(&seed))
}

/// manifest 规范字节 → `bytes`（`files` 为 `[{path, sha256, size}]`）。
#[pyfunction]
fn manifest_canonical_bytes<'py>(
    py: Python<'py>,
    created_at: &str,
    key_id: &str,
    table_spec_hash: &str,
    files: &Bound<'_, pyo3::types::PyList>,
) -> PyResult<Bound<'py, PyBytes>> {
    let mut entries: Vec<manifest::ManifestFile> = Vec::new();
    for item in files.iter() {
        let entry = item.cast::<PyDict>()?;
        let path = opt_str(entry, "path")?.unwrap_or_default();
        let sha256 = opt_str(entry, "sha256")?.unwrap_or_default();
        let size = opt_int(entry, "size")?.unwrap_or(0);
        if size < 0 {
            return Err(PyValueError::new_err("manifest_bad_size: 文件字节数不得为负"));
        }
        entries.push(manifest::ManifestFile {
            path,
            sha256,
            size: size as u64,
        });
    }
    let raw = manifest::manifest_canonical_bytes(created_at, key_id, table_spec_hash, &entries)
        .map_err(|error| PyValueError::new_err(format!("{}: {}", error.code(), error.message())))?;
    Ok(PyBytes::new(py, &raw))
}

/// 任意字节的 SHA-256（与 `spec_hash_bytes` 同义；manifest 文件哈希也走这里，保持单一实现）。
#[pyfunction]
fn hash_bytes(data: &[u8]) -> String {
    manifest::hash_bytes(data)
}

/// PyO3 模块入口。
#[pymodule]
fn vtcore(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(canonical_row_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(canonical_table_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(spec_hash_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(spec_hash_row, module)?)?;
    module.add_function(wrap_pyfunction!(spec_hash_table, module)?)?;
    module.add_function(wrap_pyfunction!(version, module)?)?;
    module.add_function(wrap_pyfunction!(generate_keypair, module)?)?;
    module.add_function(wrap_pyfunction!(public_key_from_seed, module)?)?;
    module.add_function(wrap_pyfunction!(key_id_from_public_key, module)?)?;
    module.add_function(wrap_pyfunction!(algorithm_name, module)?)?;
    module.add_function(wrap_pyfunction!(signing_message_hex, module)?)?;
    module.add_function(wrap_pyfunction!(sign_object, module)?)?;
    module.add_function(wrap_pyfunction!(verify_object, module)?)?;
    module.add_function(wrap_pyfunction!(encode_container, module)?)?;
    module.add_function(wrap_pyfunction!(parse_container, module)?)?;
    module.add_function(wrap_pyfunction!(verify_container_signature, module)?)?;
    module.add_function(wrap_pyfunction!(row_id_of_row_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(parse_row_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(wrap_project_key, module)?)?;
    module.add_function(wrap_pyfunction!(unwrap_project_key, module)?)?;
    module.add_function(wrap_pyfunction!(manifest_canonical_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(hash_bytes, module)?)?;
    module.add("SPEC_VERSION", SPEC_VERSION)?;
    module.add("ALG_NONE", sign::ALG_NONE)?;
    module.add("ALG_ED25519", sign::ALG_ED25519)?;
    module.add("SIG_VERSION", sign::SIG_VERSION)?;
    module.add("FORMAT_VERSION", container::FORMAT_VERSION)?;
    module.add("FLAG_SIGNED", container::FLAG_SIGNED)?;
    module.add("FLAG_HAS_MANIFEST", container::FLAG_HAS_MANIFEST)?;
    module.add("CHUNK_CRITICAL", container::CHUNK_CRITICAL)?;
    module.add("KEY_BLOB_MAGIC", "VTKY")?;
    module.add("KEY_BLOB_VERSION", keystore::KEY_BLOB_VERSION)?;
    module.add("KEY_BLOB_LEN", keystore::KEY_BLOB_LEN)?;
    module.add("AEAD_XCHACHA20_POLY1305", keystore::AEAD_XCHACHA20_POLY1305)?;
    module.add("MANIFEST_VERSION", manifest::MANIFEST_VERSION)?;
    Ok(())
}
