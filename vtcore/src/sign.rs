// Copyright (C) 2026 Diderde
// SPDX-License-Identifier: GPL-3.0-only
//! 签名层（`docs/voice-batch-m2-spec.md` §5）：算法编号表、签名消息规范字节、Ed25519 sign/verify。
//!
//! 与 [`crate::canonical`] 一样不依赖 pyo3，便于独立测试。
//! 被签对象是**逻辑规范字节**（表级规范字节 / manifest 规范字节），不是容器字节。

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use sha2::{Digest, Sha256};

use crate::canonical::encode_records;

/// 算法编号：`none` 保留且禁止使用（读取即拒绝）。
pub const ALG_NONE: u16 = 0x0000;
/// 算法编号：Ed25519（M2 唯一实现）。
pub const ALG_ED25519: u16 = 0x0001;
/// 签名消息版本。
pub const SIG_VERSION: i64 = 1;

/// 验签失败码（`m2-spec` §5.5）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SigError {
    /// 算法编号为 `none`（禁止）。
    AlgForbidden,
    /// 算法编号未知或未实现。
    AlgUnsupported,
    /// `key_id` 与公钥不符。
    KeyIdMismatch,
    /// 被签对象字节与签名消息中的 `object_hash` 不一致。
    ObjectHashMismatch,
    /// Ed25519 验签不通过。
    SigInvalid,
    /// 公钥 / 签名长度非法。
    BadLength,
    /// 取系统随机数失败。
    Randomness,
}

impl SigError {
    /// 稳定错误码（供 UI / 日志使用）。
    pub fn code(self) -> &'static str {
        match self {
            SigError::AlgForbidden => "sig_alg_forbidden",
            SigError::AlgUnsupported => "sig_alg_unsupported",
            SigError::KeyIdMismatch => "key_id_mismatch",
            SigError::ObjectHashMismatch => "object_hash_mismatch",
            SigError::SigInvalid => "sig_invalid",
            SigError::BadLength => "sig_bad_length",
            SigError::Randomness => "sig_randomness",
        }
    }

    /// 人类可读说明（中文，与仓库其余文案一致）。
    pub fn message(self) -> &'static str {
        match self {
            SigError::AlgForbidden => "算法编号 none 被禁止使用",
            SigError::AlgUnsupported => "算法编号未知或未实现",
            SigError::KeyIdMismatch => "key_id 与公钥不匹配",
            SigError::ObjectHashMismatch => "被签对象字节与签名不一致",
            SigError::SigInvalid => "Ed25519 验签不通过",
            SigError::BadLength => "公钥或签名长度非法",
            SigError::Randomness => "系统随机数不可用",
        }
    }
}

/// 签名块（对应 `m2-spec` §5.2 的 `SIGN` chunk payload）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SignatureBlock {
    pub alg: u16,
    pub key_id: [u8; 32],
    pub public_key: [u8; 32],
    pub signature: [u8; 64],
    pub signed_at: u64,
}

/// 算法编号是否可用（§5.1）。
pub fn check_alg(alg: u16) -> Result<(), SigError> {
    match alg {
        ALG_NONE => Err(SigError::AlgForbidden),
        ALG_ED25519 => Ok(()),
        _ => Err(SigError::AlgUnsupported),
    }
}

/// `key_id = SHA-256(公钥原始字节)`（§5.4）。
pub fn key_id_of(public_key: &[u8; 32]) -> [u8; 32] {
    Sha256::digest(public_key).into()
}

/// 公钥的十六进制形式（小写）；统一复用 [`crate::hex`]。
pub use crate::hex::hex_lower;

/// 解析 64 位十六进制（公钥 / key_id / 哈希）。
pub fn parse_hex32(text: &str) -> Result<[u8; 32], SigError> {
    crate::hex::parse_hex32(text).ok_or(SigError::BadLength)
}

/// 解析任意长度十六进制字符串。
pub fn parse_hex(text: &str) -> Result<Vec<u8>, SigError> {
    crate::hex::parse_hex(text).ok_or(SigError::BadLength)
}

/// 签名消息规范字节（§5.3）：`sig` 域分隔 + 记录式（键名升序）。
pub fn signing_message(alg: u16, key_id_hex: &str, object: &str, object_hash_hex: &str) -> Vec<u8> {
    let pairs: Vec<(String, String)> = vec![
        ("alg".to_string(), alg.to_string()),
        ("key_id".to_string(), key_id_hex.to_string()),
        ("object".to_string(), object.to_string()),
        ("object_hash".to_string(), object_hash_hex.to_string()),
        ("sig_version".to_string(), SIG_VERSION.to_string()),
    ];
    let mut out = b"sig\n".to_vec();
    out.extend_from_slice(&encode_records(&pairs));
    out
}

/// 由 32 字节种子推出 Ed25519 公钥。
pub fn public_key_of(seed: &[u8; 32]) -> [u8; 32] {
    SigningKey::from_bytes(seed).verifying_key().to_bytes()
}

/// 生成 32 字节随机种子（系统随机源）。
pub fn generate_seed() -> Result<[u8; 32], SigError> {
    let mut seed = [0u8; 32];
    getrandom::fill(&mut seed).map_err(|_| SigError::Randomness)?;
    Ok(seed)
}

/// 用种子对消息签名（Ed25519 确定性签名）。
pub fn sign_bytes(seed: &[u8; 32], message: &[u8]) -> [u8; 64] {
    SigningKey::from_bytes(seed).sign(message).to_bytes()
}

/// 验签（公钥 + 消息 + 签名）。
pub fn verify_bytes(public_key: &[u8; 32], message: &[u8], signature: &[u8; 64]) -> bool {
    let Ok(key) = VerifyingKey::from_bytes(public_key) else {
        return false;
    };
    let sig = Signature::from_bytes(signature);
    key.verify(message, &sig).is_ok()
}

/// 对被签对象的规范字节签名，产出完整签名块。
pub fn sign_object(seed: &[u8; 32], object: &str, object_bytes: &[u8], signed_at: u64) -> SignatureBlock {
    let public_key = public_key_of(seed);
    let key_id = key_id_of(&public_key);
    let object_hash = hex_lower(&Sha256::digest(object_bytes));
    let message = signing_message(ALG_ED25519, &hex_lower(&key_id), object, &object_hash);
    SignatureBlock {
        alg: ALG_ED25519,
        key_id,
        public_key,
        signature: sign_bytes(seed, &message),
        signed_at,
    }
}

/// 验签一块签名（§5.5 的 1–5 步；第 6 步信任判定由调用方负责）。
pub fn verify_object(object: &str, object_bytes: &[u8], block: &SignatureBlock) -> Result<(), SigError> {
    check_alg(block.alg)?;
    if key_id_of(&block.public_key) != block.key_id {
        return Err(SigError::KeyIdMismatch);
    }
    let object_hash = hex_lower(&Sha256::digest(object_bytes));
    let message = signing_message(block.alg, &hex_lower(&block.key_id), object, &object_hash);
    if verify_bytes(&block.public_key, &message, &block.signature) {
        Ok(())
    } else {
        Err(SigError::SigInvalid)
    }
}
