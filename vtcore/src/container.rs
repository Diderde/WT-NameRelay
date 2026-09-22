// Copyright (C) 2026 Diderde
// SPDX-License-Identifier: GPL-3.0-only
//! `.vt` 二进制容器（`docs/voice-batch-m2-spec.md` §2–§3）。
//!
//! ```text
//! 文件头 16B：magic "VTBL" | format_version u16 | flags u16 | chunk_count u32 | reserved u32
//! chunk   ：type[4] | flags u16 | payload_len u32 | payload | SHA-256(payload)[32]   （开销 42B）
//! 尾部   36B：magic "VTBE" | SHA-256(文件起始 → 尾部 magic 之前)[32]
//! ```
//!
//! - 双层完整性：逐 chunk 哈希（可跳读校验）+ 整文件哈希（可检出截断与任意改动）；
//! - 未知 **非关键** chunk 原样保留；未知 **关键** chunk 直接拒绝（不降级）；
//! - 容器内 `ROWS` 直接内嵌 M1 §4.2 单行规范字节，故行哈希可免重编码复算；
//! - 被签对象是**表级规范字节**（不是容器字节），重打包容器不破坏签名。

use sha2::{Digest, Sha256};

use crate::canonical::{canonical_table_bytes, encode_records, find_record, parse_records};
use crate::hex::hex_lower;
use crate::sign::{verify_object, SigError, SignatureBlock};

pub const MAGIC_HEADER: &[u8; 4] = b"VTBL";
pub const MAGIC_TRAILER: &[u8; 4] = b"VTBE";
pub const FORMAT_VERSION: u16 = 1;
pub const HEADER_LEN: usize = 16;
pub const TRAILER_LEN: usize = 36;
pub const CHUNK_OVERHEAD: usize = 42;
pub const SIGN_PAYLOAD_LEN: usize = 138;

pub const CHUNK_META: &[u8; 4] = b"META";
pub const CHUNK_ROWS: &[u8; 4] = b"ROWS";
pub const CHUNK_TABH: &[u8; 4] = b"TABH";
pub const CHUNK_SIGN: &[u8; 4] = b"SIGN";

/// chunk 标记为关键：实现不认识时必须拒绝。
pub const CHUNK_CRITICAL: u16 = 0b0001;
/// 文件 flags：已签名。
pub const FLAG_SIGNED: u16 = 0b0001;
/// 文件 flags：含 manifest 引用。
pub const FLAG_HAS_MANIFEST: u16 = 0b0010;
/// 文件 flags：建议只读。
pub const FLAG_READONLY_HINT: u16 = 0b0100;

/// 容器错误（稳定错误码见 `m2-spec` §2/§3）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VtError {
    BadHeaderMagic,
    UnsupportedVersion,
    BadTrailerMagic,
    Truncated,
    FileHashMismatch,
    ChunkHashMismatch,
    UnknownCriticalChunk,
    MissingChunk,
    DuplicateChunk,
    BadRecord,
    TableHashMismatch,
    RowCountMismatch,
    SignatureBlockInvalid,
    SignatureMissing,
    DuplicateRowId,
    BadHex,
    Sig(SigError),
}

impl VtError {
    pub fn code(self) -> &'static str {
        match self {
            VtError::BadHeaderMagic => "vt_bad_magic",
            VtError::UnsupportedVersion => "vt_unsupported_version",
            VtError::BadTrailerMagic => "vt_bad_trailer",
            VtError::Truncated => "vt_truncated",
            VtError::FileHashMismatch => "vt_file_hash_mismatch",
            VtError::ChunkHashMismatch => "vt_chunk_hash_mismatch",
            VtError::UnknownCriticalChunk => "vt_unknown_critical_chunk",
            VtError::MissingChunk => "vt_missing_chunk",
            VtError::DuplicateChunk => "vt_duplicate_chunk",
            VtError::BadRecord => "vt_bad_record",
            VtError::TableHashMismatch => "vt_table_hash_mismatch",
            VtError::RowCountMismatch => "vt_row_count_mismatch",
            VtError::SignatureBlockInvalid => "vt_signature_block_invalid",
            VtError::SignatureMissing => "vt_signature_missing",
            VtError::DuplicateRowId => "vt_duplicate_row_id",
            VtError::BadHex => "vt_bad_hex",
            VtError::Sig(inner) => inner.code(),
        }
    }

    pub fn message(self) -> &'static str {
        match self {
            VtError::BadHeaderMagic => "文件头 magic 不是 VTBL",
            VtError::UnsupportedVersion => "容器格式版本不受支持",
            VtError::BadTrailerMagic => "缺少 VTBE 尾部（文件可能被截断）",
            VtError::Truncated => "容器长度不足或 chunk 越界",
            VtError::FileHashMismatch => "整文件哈希不符（被改动或损坏）",
            VtError::ChunkHashMismatch => "chunk 哈希不符（被改动或损坏）",
            VtError::UnknownCriticalChunk => "存在无法识别的关键 chunk",
            VtError::MissingChunk => "缺少必需 chunk",
            VtError::DuplicateChunk => "必需 chunk 重复出现",
            VtError::BadRecord => "规范记录损坏",
            VtError::TableHashMismatch => "表级 spec_hash 与行数据不一致",
            VtError::RowCountMismatch => "row_count 与实际行数不一致",
            VtError::SignatureBlockInvalid => "签名块长度或内容非法",
            VtError::SignatureMissing => "文件声明已签名但缺少 SIGN chunk",
            VtError::DuplicateRowId => "同一表内存在重复 row_id",
            VtError::BadHex => "十六进制字段非法",
            VtError::Sig(inner) => inner.message(),
        }
    }
}

impl From<SigError> for VtError {
    fn from(error: SigError) -> Self {
        VtError::Sig(error)
    }
}

/// 原样保留的 chunk（未知非关键类型）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawChunk {
    pub kind: [u8; 4],
    pub flags: u16,
    pub payload: Vec<u8>,
}

/// 一份 `.vt` 文档。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VtDocument {
    pub flags: u16,
    pub table_id: String,
    pub spec_version: i64,
    /// M1 语义下恒为空串（`m2-spec` §4.4）。
    pub key_id: String,
    pub created_at: String,
    pub generator: String,
    /// 每行 = M1 §4.2 单行规范字节（原样内嵌）。
    pub rows: Vec<Vec<u8>>,
    pub table_hash: String,
    pub signature: Option<SignatureBlock>,
    pub extras: Vec<RawChunk>,
}

impl VtDocument {
    /// 新建空文档（未签名）。
    pub fn new(table_id: &str, created_at: &str, generator: &str) -> Self {
        VtDocument {
            flags: 0,
            table_id: table_id.to_string(),
            spec_version: 1,
            key_id: String::new(),
            created_at: created_at.to_string(),
            generator: generator.to_string(),
            rows: Vec::new(),
            table_hash: String::new(),
            signature: None,
            extras: Vec::new(),
        }
    }

    /// 表级规范字节（行按 `row_id` 升序）——容器自洽校验与签名校验都用它。
    pub fn table_canonical_bytes(&self) -> Result<Vec<u8>, VtError> {
        let row_hashes = self.row_hashes()?;
        Ok(canonical_table_bytes(
            &row_hashes,
            &self.table_id,
            &self.key_id,
            self.spec_version,
        ))
    }

    /// `(row_id, SHA-256(行规范字节))` 列表，行内 `row_id` 从记录中解析。
    pub fn row_hashes(&self) -> Result<Vec<(String, String)>, VtError> {
        let mut seen: Vec<String> = Vec::with_capacity(self.rows.len());
        let mut out: Vec<(String, String)> = Vec::with_capacity(self.rows.len());
        for block in &self.rows {
            let row_id = row_id_of(block)?;
            if seen.contains(&row_id) {
                return Err(VtError::DuplicateRowId);
            }
            seen.push(row_id.clone());
            out.push((row_id, hex_lower(&Sha256::digest(block))));
        }
        Ok(out)
    }

    /// 重算表级 `spec_hash`。
    pub fn compute_table_hash(&self) -> Result<String, VtError> {
        Ok(hex_lower(&Sha256::digest(self.table_canonical_bytes()?)))
    }

    /// 校验签名（若存在）：被签对象为表级规范字节。
    pub fn verify_signature(&self) -> Result<(), VtError> {
        let Some(block) = self.signature.as_ref() else {
            return Err(VtError::SignatureMissing);
        };
        let payload = self.table_canonical_bytes()?;
        verify_object("table", &payload, block).map_err(VtError::from)
    }

    /// 是否声明已签名。
    pub fn is_signed(&self) -> bool {
        self.flags & FLAG_SIGNED != 0
    }
}

/// 从行规范字节里解析 `row_id`。
pub fn row_id_of(block: &[u8]) -> Result<String, VtError> {
    let body = block.strip_prefix(b"row\n").ok_or(VtError::BadRecord)?;
    let pairs = parse_records(body).map_err(|_| VtError::BadRecord)?;
    find_record(&pairs, "row_id")
        .map(str::to_string)
        .ok_or(VtError::BadRecord)
}

fn chunk_bytes(kind: &[u8; 4], flags: u16, payload: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(CHUNK_OVERHEAD + payload.len());
    out.extend_from_slice(kind);
    out.extend_from_slice(&flags.to_le_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    out.extend_from_slice(payload);
    out.extend_from_slice(&Sha256::digest(payload));
    out
}

/// 编码为 `.vt` 字节。
pub fn encode(document: &VtDocument) -> Result<Vec<u8>, VtError> {
    let mut doc = document.clone();
    let computed = doc.compute_table_hash()?;
    if !doc.table_hash.is_empty() && doc.table_hash != computed {
        return Err(VtError::TableHashMismatch);
    }
    doc.table_hash = computed;
    if doc.signature.is_some() {
        doc.flags |= FLAG_SIGNED;
    } else {
        doc.flags &= !FLAG_SIGNED;
    }

    let meta_pairs: Vec<(String, String)> = vec![
        ("created_at".to_string(), doc.created_at.clone()),
        ("generator".to_string(), doc.generator.clone()),
        ("key_id".to_string(), doc.key_id.clone()),
        ("spec_version".to_string(), doc.spec_version.to_string()),
        ("table_id".to_string(), doc.table_id.clone()),
    ];
    let meta_payload = encode_records(&meta_pairs);

    // 校验行（记录损坏 / 重复 row_id），并按 row_id 升序拼接
    doc.row_hashes()?;
    let mut ordered: Vec<(String, &Vec<u8>)> = Vec::with_capacity(doc.rows.len());
    for block in &doc.rows {
        ordered.push((row_id_of(block)?, block));
    }
    ordered.sort_by(|left, right| left.0.as_bytes().cmp(right.0.as_bytes()));
    let mut rows_payload: Vec<u8> = Vec::new();
    for (_, block) in ordered {
        rows_payload.extend_from_slice(block);
    }

    let tabh_pairs: Vec<(String, String)> = vec![
        ("row_count".to_string(), doc.rows.len().to_string()),
        ("spec_hash".to_string(), doc.table_hash.clone()),
        ("spec_version".to_string(), doc.spec_version.to_string()),
        ("table_id".to_string(), doc.table_id.clone()),
    ];
    let tabh_payload = encode_records(&tabh_pairs);

    let mut chunks: Vec<Vec<u8>> = Vec::new();
    chunks.push(chunk_bytes(CHUNK_META, CHUNK_CRITICAL, &meta_payload));
    chunks.push(chunk_bytes(CHUNK_ROWS, CHUNK_CRITICAL, &rows_payload));
    chunks.push(chunk_bytes(CHUNK_TABH, CHUNK_CRITICAL, &tabh_payload));
    if let Some(block) = doc.signature.as_ref() {
        chunks.push(chunk_bytes(CHUNK_SIGN, CHUNK_CRITICAL, &sign_payload(block)));
    }
    for extra in &doc.extras {
        chunks.push(chunk_bytes(&extra.kind, extra.flags, &extra.payload));
    }

    let mut out: Vec<u8> = Vec::new();
    out.extend_from_slice(MAGIC_HEADER);
    out.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
    out.extend_from_slice(&doc.flags.to_le_bytes());
    out.extend_from_slice(&(chunks.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for chunk in &chunks {
        out.extend_from_slice(chunk);
    }
    debug_assert_eq!(out.len(), HEADER_LEN + chunks.iter().map(Vec::len).sum::<usize>());
    // 尾部哈希只覆盖「文件起始 → 尾部 magic 之前」
    let file_hash = Sha256::digest(&out);
    out.extend_from_slice(MAGIC_TRAILER);
    out.extend_from_slice(&file_hash);
    Ok(out)
}

fn sign_payload(block: &SignatureBlock) -> Vec<u8> {
    let mut out = Vec::with_capacity(SIGN_PAYLOAD_LEN);
    out.extend_from_slice(&block.alg.to_le_bytes());
    out.extend_from_slice(&block.key_id);
    out.extend_from_slice(&block.public_key);
    out.extend_from_slice(&block.signature);
    out.extend_from_slice(&block.signed_at.to_le_bytes());
    out
}

fn parse_sign_payload(payload: &[u8]) -> Result<SignatureBlock, VtError> {
    if payload.len() != SIGN_PAYLOAD_LEN {
        return Err(VtError::SignatureBlockInvalid);
    }
    let mut key_id = [0u8; 32];
    let mut public_key = [0u8; 32];
    let mut signature = [0u8; 64];
    key_id.copy_from_slice(&payload[2..34]);
    public_key.copy_from_slice(&payload[34..66]);
    signature.copy_from_slice(&payload[66..130]);
    Ok(SignatureBlock {
        alg: u16::from_le_bytes([payload[0], payload[1]]),
        key_id,
        public_key,
        signature,
        signed_at: u64::from_le_bytes(payload[130..138].try_into().unwrap_or([0u8; 8])),
    })
}

/// 解析 `.vt` 字节（结构 + 自洽校验；签名信任判定由调用方负责）。
pub fn decode(data: &[u8]) -> Result<VtDocument, VtError> {
    if data.len() < HEADER_LEN + TRAILER_LEN {
        return Err(VtError::Truncated);
    }
    if &data[..4] != MAGIC_HEADER {
        return Err(VtError::BadHeaderMagic);
    }
    let version = u16::from_le_bytes([data[4], data[5]]);
    if version != FORMAT_VERSION {
        return Err(VtError::UnsupportedVersion);
    }
    let flags = u16::from_le_bytes([data[6], data[7]]);
    let chunk_count = u32::from_le_bytes([data[8], data[9], data[10], data[11]]) as usize;

    let trailer_at = data.len() - TRAILER_LEN;
    if &data[trailer_at..trailer_at + 4] != MAGIC_TRAILER {
        return Err(VtError::BadTrailerMagic);
    }
    let expected_file_hash = Sha256::digest(&data[..trailer_at]);
    if expected_file_hash[..] != data[trailer_at + 4..] {
        return Err(VtError::FileHashMismatch);
    }

    let mut offset = HEADER_LEN;
    let mut meta: Option<Vec<(String, String)>> = None;
    let mut rows: Option<Vec<Vec<u8>>> = None;
    let mut tabh: Option<Vec<(String, String)>> = None;
    let mut signature: Option<SignatureBlock> = None;
    let mut extras: Vec<RawChunk> = Vec::new();

    for _ in 0..chunk_count {
        if offset + CHUNK_OVERHEAD > trailer_at {
            return Err(VtError::Truncated);
        }
        let kind: [u8; 4] = data[offset..offset + 4].try_into().unwrap_or([0u8; 4]);
        let chunk_flags = u16::from_le_bytes([data[offset + 4], data[offset + 5]]);
        let payload_len = u32::from_le_bytes([
            data[offset + 6],
            data[offset + 7],
            data[offset + 8],
            data[offset + 9],
        ]) as usize;
        let payload_at = offset + 10;
        let payload_end = payload_at + payload_len;
        if payload_end + 32 > trailer_at {
            return Err(VtError::Truncated);
        }
        let payload = &data[payload_at..payload_end];
        let stored_hash = &data[payload_end..payload_end + 32];
        if Sha256::digest(payload)[..] != *stored_hash {
            return Err(VtError::ChunkHashMismatch);
        }
        offset = payload_end + 32;

        match &kind {
            k if k == CHUNK_META => {
                if meta.is_some() {
                    return Err(VtError::DuplicateChunk);
                }
                meta = Some(parse_records(payload).map_err(|_| VtError::BadRecord)?);
            }
            k if k == CHUNK_ROWS => {
                if rows.is_some() {
                    return Err(VtError::DuplicateChunk);
                }
                rows = Some(split_rows(payload)?);
            }
            k if k == CHUNK_TABH => {
                if tabh.is_some() {
                    return Err(VtError::DuplicateChunk);
                }
                tabh = Some(parse_records(payload).map_err(|_| VtError::BadRecord)?);
            }
            k if k == CHUNK_SIGN => {
                if signature.is_some() {
                    return Err(VtError::DuplicateChunk);
                }
                signature = Some(parse_sign_payload(payload)?);
            }
            _ => {
                if chunk_flags & CHUNK_CRITICAL != 0 {
                    return Err(VtError::UnknownCriticalChunk);
                }
                extras.push(RawChunk {
                    kind,
                    flags: chunk_flags,
                    payload: payload.to_vec(),
                });
            }
        }
    }

    if offset != trailer_at {
        return Err(VtError::Truncated);
    }

    let meta_pairs = meta.ok_or(VtError::MissingChunk)?;
    let rows = rows.ok_or(VtError::MissingChunk)?;
    let tabh_pairs = tabh.ok_or(VtError::MissingChunk)?;

    let document = VtDocument {
        flags,
        table_id: find_record(&meta_pairs, "table_id").unwrap_or_default().to_string(),
        spec_version: find_record(&meta_pairs, "spec_version")
            .and_then(|value| value.parse::<i64>().ok())
            .ok_or(VtError::BadRecord)?,
        key_id: find_record(&meta_pairs, "key_id").unwrap_or_default().to_string(),
        created_at: find_record(&meta_pairs, "created_at").unwrap_or_default().to_string(),
        generator: find_record(&meta_pairs, "generator").unwrap_or_default().to_string(),
        rows,
        table_hash: find_record(&tabh_pairs, "spec_hash").unwrap_or_default().to_string(),
        signature,
        extras,
    };

    // 自洽校验：row_count / 表级哈希 / 签名声明
    let declared_count: usize = find_record(&tabh_pairs, "row_count")
        .and_then(|value| value.parse().ok())
        .ok_or(VtError::BadRecord)?;
    if declared_count != document.rows.len() {
        return Err(VtError::RowCountMismatch);
    }
    if document.table_hash != document.compute_table_hash()? {
        return Err(VtError::TableHashMismatch);
    }
    if document.is_signed() && document.signature.is_none() {
        return Err(VtError::SignatureMissing);
    }
    Ok(document)
}

/// 把 `ROWS` payload 按行切分：每个块以 `row\n` 起头，块内是规范记录序列。
///
/// 只在**记录边界**上识别下一个块起点，因此即使某个值是字面量 `row\n` 也不会误切。
fn split_rows(payload: &[u8]) -> Result<Vec<Vec<u8>>, VtError> {
    let mut out: Vec<Vec<u8>> = Vec::new();
    let mut cursor = 0usize;
    while cursor < payload.len() {
        if !payload[cursor..].starts_with(b"row\n") {
            return Err(VtError::BadRecord);
        }
        let start = cursor;
        cursor += 4;
        while cursor < payload.len() && !payload[cursor..].starts_with(b"row\n") {
            cursor = next_record_end(payload, cursor)?;
        }
        let block = payload[start..cursor].to_vec();
        row_id_of(&block)?;
        out.push(block);
    }
    Ok(out)
}

/// 从 `start` 处解析一条规范记录，返回其结束偏移（含尾随 `LF`）。
fn next_record_end(payload: &[u8], start: usize) -> Result<usize, VtError> {
    let rest = &payload[start..];
    let eq = rest.iter().position(|byte| *byte == b'=').ok_or(VtError::BadRecord)?;
    let after = &rest[eq + 1..];
    let colon = after.iter().position(|byte| *byte == b':').ok_or(VtError::BadRecord)?;
    let len_text = std::str::from_utf8(&after[..colon]).map_err(|_| VtError::BadRecord)?;
    if len_text.is_empty() || (len_text.len() > 1 && len_text.starts_with('0')) {
        return Err(VtError::BadRecord);
    }
    let len: usize = len_text.parse().map_err(|_| VtError::BadRecord)?;
    let value_end = start + eq + 1 + colon + 1 + len;
    if value_end >= payload.len() || payload[value_end] != b'\n' {
        return Err(VtError::BadRecord);
    }
    Ok(value_end + 1)
}
