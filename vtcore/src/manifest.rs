// Copyright (C) 2026 Diderde
// SPDX-License-Identifier: GPL-3.0-only
//! `.vtmanifest` 的规范字节（`docs/voice-batch-m2-spec.md` §9）。
//!
//! 记录式（复用 §4.1），域分隔首行固定 `manifest`；`file` 记录按路径升序：
//!
//! ```text
//! manifest
//! created_at=<len>:<ISO8601>
//! file=<len>:<hex64 sha256>|<十进制字节数>|<POSIX 相对路径>
//! file_count=<len>:<十进制文件数>
//! key_id=64:<hex64 或 空>
//! manifest_version=1:1
//! table_spec_hash=64:<hex64>
//! ```
//!
//! 约束：路径必须是**相对路径 + POSIX 分隔符**，且不含 `|` 与 `LF`；`file_count` 必须等于记录条数。

use crate::canonical::encode_records;
use crate::hex::hex_lower;
use sha2::{Digest, Sha256};

pub const MANIFEST_VERSION: i64 = 1;

/// manifest 规范字节的构造错误。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ManifestError {
    BadPath,
    BadHash,
    DuplicatePath,
    EmptyTableHash,
}

impl ManifestError {
    pub fn code(self) -> &'static str {
        match self {
            ManifestError::BadPath => "manifest_bad_path",
            ManifestError::BadHash => "manifest_bad_hash",
            ManifestError::DuplicatePath => "manifest_duplicate_path",
            ManifestError::EmptyTableHash => "manifest_bad_table_hash",
        }
    }

    pub fn message(self) -> &'static str {
        match self {
            ManifestError::BadPath => "清单路径必须是相对 POSIX 路径，且不含 | 与换行",
            ManifestError::BadHash => "清单里的文件哈希必须是 64 位十六进制",
            ManifestError::DuplicatePath => "清单里出现重复路径",
            ManifestError::EmptyTableHash => "清单必须携带 64 位十六进制的表级 spec_hash",
        }
    }
}

/// 一个被打包文件：相对路径 + SHA-256 + 字节数。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ManifestFile {
    pub path: String,
    pub sha256: String,
    pub size: u64,
}

fn check_path(path: &str) -> Result<(), ManifestError> {
    if path.is_empty() || path.contains('|') || path.contains('\n') || path.contains('\r') {
        return Err(ManifestError::BadPath);
    }
    if path.starts_with('/') || path.contains(':') || path.split('/').any(|part| part == "..") {
        return Err(ManifestError::BadPath);
    }
    Ok(())
}

fn check_hash(digest: &str) -> Result<(), ManifestError> {
    if digest.len() != 64 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(ManifestError::BadHash);
    }
    Ok(())
}

/// 生成 manifest 规范字节（供签名与验签使用）。
pub fn manifest_canonical_bytes(
    created_at: &str,
    key_id: &str,
    table_spec_hash: &str,
    files: &[ManifestFile],
) -> Result<Vec<u8>, ManifestError> {
    check_hash(table_spec_hash).map_err(|_| ManifestError::EmptyTableHash)?;
    if !key_id.is_empty() {
        check_hash(key_id)?;
    }

    let mut ordered: Vec<&ManifestFile> = files.iter().collect();
    for item in &ordered {
        check_path(&item.path)?;
        check_hash(&item.sha256)?;
    }
    ordered.sort_by(|left, right| left.path.as_bytes().cmp(right.path.as_bytes()));
    for pair in ordered.windows(2) {
        if pair[0].path == pair[1].path {
            return Err(ManifestError::DuplicatePath);
        }
    }

    let mut pairs: Vec<(String, String)> = vec![("created_at".to_string(), created_at.to_string())];
    for item in &ordered {
        pairs.push((
            "file".to_string(),
            format!("{}|{}|{}", item.sha256.to_lowercase(), item.size, item.path),
        ));
    }
    pairs.push(("file_count".to_string(), ordered.len().to_string()));
    pairs.push(("key_id".to_string(), key_id.to_string()));
    pairs.push(("manifest_version".to_string(), MANIFEST_VERSION.to_string()));
    pairs.push(("table_spec_hash".to_string(), table_spec_hash.to_lowercase()));

    let mut out = b"manifest\n".to_vec();
    out.extend_from_slice(&encode_records(&pairs));
    Ok(out)
}

/// 文件内容的 SHA-256（hex）—— 与容器/表哈希同一算法，便于调用方统一使用。
pub fn hash_bytes(data: &[u8]) -> String {
    hex_lower(&Sha256::digest(data))
}
