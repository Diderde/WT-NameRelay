// Copyright (C) 2026 Diderde
// SPDX-License-Identifier: GPL-3.0-only
//! 十六进制编解码（文本层统一小写，`m2-spec` §1）。

/// 字节 → 小写十六进制。
pub fn hex_lower(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(DIGITS[(byte >> 4) as usize] as char);
        out.push(DIGITS[(byte & 0x0f) as usize] as char);
    }
    out
}

/// 十六进制 → 字节（长度必须为偶数，且全部为十六进制字符）。
pub fn parse_hex(text: &str) -> Option<Vec<u8>> {
    if text.len() % 2 != 0 || !text.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    (0..text.len() / 2)
        .map(|index| u8::from_str_radix(&text[index * 2..index * 2 + 2], 16).ok())
        .collect()
}

/// 十六进制 → 32 字节定长。
pub fn parse_hex32(text: &str) -> Option<[u8; 32]> {
    let raw = parse_hex(text)?;
    raw.try_into().ok()
}
