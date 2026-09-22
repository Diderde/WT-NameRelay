// Copyright (C) 2026 Diderde
// SPDX-License-Identifier: GPL-3.0-only
//! 项目私钥的 AEAD 封装（`docs/voice-batch-m2-spec.md` §7）。
//!
//! ```text
//! +0  magic "VTKY" | +4 version u16=1 | +6 aead u16=1(XChaCha20-Poly1305)
//! +8  nonce[24] | +32 ciphertext(32) | +64 tag(16)        → 共 80 字节
//! ```
//!
//! - **AAD = key_id 的 ASCII hex（64 字节）** → 换文件/换名即解密失败，防混淆；
//! - 明文恒为 32 字节 Ed25519 种子；本模块**只做封装**，主包装钥的获取（系统凭据库 / DPAPI）
//!   由调用方负责，密钥材料不落日志。

use chacha20poly1305::aead::{Aead, KeyInit, Payload};
use chacha20poly1305::{Key, XChaCha20Poly1305, XNonce};

pub const KEY_BLOB_MAGIC: &[u8; 4] = b"VTKY";
pub const KEY_BLOB_VERSION: u16 = 1;
pub const AEAD_XCHACHA20_POLY1305: u16 = 1;
pub const NONCE_LEN: usize = 24;
pub const SEED_LEN: usize = 32;
pub const TAG_LEN: usize = 16;
pub const KEY_ID_HEX_LEN: usize = 64;
/// 头部：magic(4) + version(2) + aead(2) + nonce(24)
pub const KEY_BLOB_HEADER_LEN: usize = 32;
/// 完整长度：头部 + 密文(32) + 认证标签(16)
pub const KEY_BLOB_LEN: usize = KEY_BLOB_HEADER_LEN + SEED_LEN + TAG_LEN;

/// 密钥封装错误（稳定错误码）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeyError {
    BadMagic,
    UnsupportedVersion,
    UnsupportedAead,
    BadLength,
    BadKeyId,
    BadMasterKey,
    DecryptFailed,
    Randomness,
}

impl KeyError {
    pub fn code(self) -> &'static str {
        match self {
            KeyError::BadMagic => "key_bad_magic",
            KeyError::UnsupportedVersion => "key_unsupported_version",
            KeyError::UnsupportedAead => "key_unsupported_aead",
            KeyError::BadLength => "key_bad_length",
            KeyError::BadKeyId => "key_bad_key_id",
            KeyError::BadMasterKey => "key_bad_master_key",
            KeyError::DecryptFailed => "key_decrypt_failed",
            KeyError::Randomness => "key_randomness",
        }
    }

    pub fn message(self) -> &'static str {
        match self {
            KeyError::BadMagic => "密钥文件头不是 VTKY",
            KeyError::UnsupportedVersion => "密钥文件版本不受支持",
            KeyError::UnsupportedAead => "密钥封装算法编号不受支持",
            KeyError::BadLength => "密钥文件长度非法",
            KeyError::BadKeyId => "key_id 必须是 64 位十六进制",
            KeyError::BadMasterKey => "主包装钥必须是 32 字节",
            KeyError::DecryptFailed => "解密失败（主包装钥不符、key_id 不符或文件被改动）",
            KeyError::Randomness => "系统随机数不可用",
        }
    }
}

/// 主包装钥 32 字节。
pub type MasterKey = [u8; 32];

fn check_key_id(key_id_hex: &str) -> Result<(), KeyError> {
    if key_id_hex.len() != KEY_ID_HEX_LEN || !key_id_hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(KeyError::BadKeyId);
    }
    Ok(())
}

/// 用主包装钥加密 32 字节种子，产出密钥文件字节（每次调用使用新的随机 nonce）。
pub fn wrap_seed(master: &MasterKey, key_id_hex: &str, seed: &[u8; SEED_LEN]) -> Result<Vec<u8>, KeyError> {
    check_key_id(key_id_hex)?;
    let mut nonce_bytes = [0u8; NONCE_LEN];
    getrandom::fill(&mut nonce_bytes).map_err(|_| KeyError::Randomness)?;

    let key = Key::try_from(master.as_slice()).map_err(|_| KeyError::BadMasterKey)?;
    let cipher = XChaCha20Poly1305::new(&key);
    let nonce = XNonce::try_from(nonce_bytes.as_slice()).map_err(|_| KeyError::Randomness)?;
    let ciphertext = cipher
        .encrypt(
            &nonce,
            Payload {
                msg: seed,
                aad: key_id_hex.as_bytes(),
            },
        )
        .map_err(|_| KeyError::DecryptFailed)?;

    let mut out = Vec::with_capacity(KEY_BLOB_LEN);
    out.extend_from_slice(KEY_BLOB_MAGIC);
    out.extend_from_slice(&KEY_BLOB_VERSION.to_le_bytes());
    out.extend_from_slice(&AEAD_XCHACHA20_POLY1305.to_le_bytes());
    out.extend_from_slice(&nonce_bytes);
    out.extend_from_slice(&ciphertext);
    Ok(out)
}

/// 解出 32 字节种子；任何不符（magic/版本/长度/AAD/标签）都返回错误，不返回部分结果。
pub fn unwrap_seed(master: &MasterKey, key_id_hex: &str, blob: &[u8]) -> Result<[u8; SEED_LEN], KeyError> {
    check_key_id(key_id_hex)?;
    if blob.len() != KEY_BLOB_LEN {
        return Err(KeyError::BadLength);
    }
    if &blob[..4] != KEY_BLOB_MAGIC {
        return Err(KeyError::BadMagic);
    }
    let version = u16::from_le_bytes([blob[4], blob[5]]);
    if version != KEY_BLOB_VERSION {
        return Err(KeyError::UnsupportedVersion);
    }
    let aead = u16::from_le_bytes([blob[6], blob[7]]);
    if aead != AEAD_XCHACHA20_POLY1305 {
        return Err(KeyError::UnsupportedAead);
    }
    let nonce = XNonce::try_from(&blob[8..8 + NONCE_LEN]).map_err(|_| KeyError::BadLength)?;
    let key = Key::try_from(master.as_slice()).map_err(|_| KeyError::BadMasterKey)?;
    let cipher = XChaCha20Poly1305::new(&key);
    let plaintext = cipher
        .decrypt(
            &nonce,
            Payload {
                msg: &blob[KEY_BLOB_HEADER_LEN..],
                aad: key_id_hex.as_bytes(),
            },
        )
        .map_err(|_| KeyError::DecryptFailed)?;
    let seed: [u8; SEED_LEN] = plaintext.try_into().map_err(|_| KeyError::BadLength)?;
    Ok(seed)
}

/// 密钥文件版本探针（供 Python 侧核对格式常量）。
pub fn blob_version() -> u16 {
    KEY_BLOB_VERSION
}
