// Copyright (C) 2026 Diderde
// SPDX-License-Identifier: GPL-3.0-only
//! M1 规范字节的权威实现（`docs/voice-batch-spec.md` §4）。
//!
//! 本模块**不依赖 pyo3**，因此可被独立单元/集成测试直接覆盖；
//! Python 侧只经 `lib.rs` 的薄胶水调用它。
//!
//! 逐字节规则（与 M1 规范一致，不得改动）：
//! 1. 记录 = `键名` 的 UTF-8 字节 + `=` + 值字节数的十进制 ASCII + `:` + 值 UTF-8 字节 + `LF`；
//! 2. 记录按键名 **UTF-8 字节序**升序，同键保持传入顺序；
//! 3. 首行域分隔：行 = `row`，表 = `table`。

/// 默认值：与 Python 参考实现 `app/models/voice_table.py` 一致。
pub const DEFAULT_LANGUAGE: &str = "zh";
pub const DEFAULT_SPEED: i64 = 1000;
pub const DEFAULT_VOLUME: i64 = 1000;
pub const SPEC_VERSION: i64 = 1;

/// 一行语音制作项的内容字段（可选字段用 `None` 表示缺省）。
#[derive(Debug, Clone, Default)]
pub struct RowFields {
    pub row_id: String,
    pub name: String,
    pub text: String,
    pub language: Option<String>,
    pub voice: Option<String>,
    pub emotion: Option<String>,
    pub speed: Option<i64>,
    pub pitch: Option<i64>,
    pub volume: Option<i64>,
    pub seed: Option<i64>,
    pub extra: Vec<(String, String)>,
}

impl RowFields {
    /// 按 §2 收集内容字段：必填四项恒写；可选字段等于默认值时不写记录。
    pub fn content_pairs(&self) -> Vec<(String, String)> {
        let language = self
            .language
            .clone()
            .unwrap_or_else(|| DEFAULT_LANGUAGE.to_string());
        let mut pairs: Vec<(String, String)> = vec![
            ("language".to_string(), language),
            ("name".to_string(), self.name.clone()),
            ("row_id".to_string(), self.row_id.clone()),
            ("text".to_string(), self.text.clone()),
        ];
        if let Some(voice) = self.voice.as_ref().filter(|value| !value.is_empty()) {
            pairs.push(("voice".to_string(), voice.clone()));
        }
        if let Some(emotion) = self.emotion.as_ref().filter(|value| !value.is_empty()) {
            pairs.push(("emotion".to_string(), emotion.clone()));
        }
        if let Some(speed) = self.speed.filter(|value| *value != DEFAULT_SPEED) {
            pairs.push(("speed".to_string(), speed.to_string()));
        }
        if let Some(pitch) = self.pitch.filter(|value| *value != 0) {
            pairs.push(("pitch".to_string(), pitch.to_string()));
        }
        if let Some(volume) = self.volume.filter(|value| *value != DEFAULT_VOLUME) {
            pairs.push(("volume".to_string(), volume.to_string()));
        }
        if let Some(seed) = self.seed.filter(|value| *value != 0) {
            pairs.push(("seed".to_string(), seed.to_string()));
        }
        for (key, value) in &self.extra {
            pairs.push((format!("extra.{key}"), value.clone()));
        }
        pairs
    }
}

/// 单条规范记录（§4.1.2）。
pub fn record(key: &str, value: &str) -> Vec<u8> {
    let raw = value.as_bytes();
    let mut out = Vec::with_capacity(key.len() + raw.len() + 8);
    out.extend_from_slice(key.as_bytes());
    out.push(b'=');
    out.extend_from_slice(raw.len().to_string().as_bytes());
    out.push(b':');
    out.extend_from_slice(raw);
    out.push(b'\n');
    out
}

/// 按键名 UTF-8 字节序编码全部记录（§4.1.3；同键保持传入顺序）。
pub fn encode_records(pairs: &[(String, String)]) -> Vec<u8> {
    let mut indexed: Vec<(usize, &(String, String))> = pairs.iter().enumerate().collect();
    indexed.sort_by(|left, right| {
        left.1
             .0
            .as_bytes()
            .cmp(right.1 .0.as_bytes())
            .then(left.0.cmp(&right.0))
    });
    let mut out = Vec::new();
    for (_, (key, value)) in indexed {
        out.extend_from_slice(&record(key, value));
    }
    out
}

/// 单行规范字节（§4.2）。`key_id` 恒写入（M2 语义见 m2-spec §4.4）。
pub fn canonical_row_bytes(row: &RowFields, key_id: &str) -> Vec<u8> {    let mut pairs = row.content_pairs();
    pairs.push(("key_id".to_string(), key_id.to_string()));
    let mut out = b"row\n".to_vec();
    out.extend_from_slice(&encode_records(&pairs));
    out
}

/// 表级规范字节（§4.3）。`row_hashes` 为 `(row_id, spec_hash_row)`。
pub fn canonical_table_bytes(
    row_hashes: &[(String, String)],
    table_id: &str,
    key_id: &str,
    spec_version: i64,
) -> Vec<u8> {
    let mut sorted: Vec<&(String, String)> = row_hashes.iter().collect();
    sorted.sort_by(|left, right| left.0.as_bytes().cmp(right.0.as_bytes()));

    let mut pairs: Vec<(String, String)> = vec![
        ("key_id".to_string(), key_id.to_string()),
        ("row_count".to_string(), row_hashes.len().to_string()),
    ];
    for (_, row_hash) in sorted {
        pairs.push(("row_hash".to_string(), row_hash.clone()));
    }
    pairs.push(("spec_version".to_string(), spec_version.to_string()));
    pairs.push(("table_id".to_string(), table_id.to_string()));

    let mut out = b"table\n".to_vec();
    out.extend_from_slice(&encode_records(&pairs));
    out
}

/// 规范记录解析失败原因（§4.1）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RecordError {
    /// 缺少 `=` 或 `:` 分隔符。
    BadSeparator,
    /// 长度前缀不是合法十进制（空、前导零、非数字）。
    BadLength,
    /// 记录行未以 `LF` 结束。
    MissingNewline,
    /// 值字节数与长度前缀不符。
    LengthMismatch,
    /// 键名或值不是合法 UTF-8。
    Utf8,
    /// 缺少域分隔首行（行块应以 `row` 起头、表块以 `table` 起头）。
    MissingDomain,
    /// 整数字段不是合法十进制。
    BadInteger,
}

/// 解析规范记录（§4.1）—— 容器读取 META / ROWS / TABH 的 payload 时使用。
///
/// 严格模式：长度前缀必须是「无前导零的十进制 ASCII」，值与长度必须严格相符，
/// 尾随 `LF` 必须存在。任何偏差都视为损坏（不猜测、不修复）。
pub fn parse_records(data: &[u8]) -> Result<Vec<(String, String)>, RecordError> {
    let mut out: Vec<(String, String)> = Vec::new();
    let mut rest = data;
    while !rest.is_empty() {
        let line_end = rest
            .iter()
            .position(|byte| *byte == b'\n')
            .ok_or(RecordError::MissingNewline)?;
        let line = &rest[..line_end];
        rest = &rest[line_end + 1..];

        let eq = line
            .iter()
            .position(|byte| *byte == b'=')
            .ok_or(RecordError::BadSeparator)?;
        let key = std::str::from_utf8(&line[..eq]).map_err(|_| RecordError::Utf8)?;

        let after = &line[eq + 1..];
        let colon = after
            .iter()
            .position(|byte| *byte == b':')
            .ok_or(RecordError::BadSeparator)?;
        let len_text = std::str::from_utf8(&after[..colon]).map_err(|_| RecordError::Utf8)?;
        if len_text.is_empty() || (len_text.len() > 1 && len_text.starts_with('0')) {
            return Err(RecordError::BadLength);
        }
        let len: usize = len_text.parse().map_err(|_| RecordError::BadLength)?;

        let value_bytes = &after[colon + 1..];
        if value_bytes.len() != len {
            return Err(RecordError::LengthMismatch);
        }
        let value = std::str::from_utf8(value_bytes).map_err(|_| RecordError::Utf8)?;
        out.push((key.to_string(), value.to_string()));
    }
    Ok(out)
}

/// 在记录集合里取首个同键记录的值。
pub fn find_record<'a>(pairs: &'a [(String, String)], key: &str) -> Option<&'a str> {
    pairs
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value.as_str())
}

/// 由单行规范字节解析出的字段（[`canonical_row_bytes`] 的逆操作）。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ParsedRow {
    pub row_id: String,
    pub name: String,
    pub text: String,
    /// 缺省视为 [`DEFAULT_LANGUAGE`]。
    pub language: String,
    pub voice: String,
    pub emotion: String,
    pub speed: i64,
    pub pitch: i64,
    pub volume: i64,
    pub seed: i64,
    /// `extra.` 前缀键（前缀已剥离），保持记录顺序。
    pub extra: Vec<(String, String)>,
    /// 规范字节里的 `key_id` 记录（M1 恒空）。
    pub key_id: String,
    /// 本实现不认识的键，原样保留，避免查看时静默丢失信息。
    pub unknown: Vec<(String, String)>,
}

fn parse_int(pairs: &[(String, String)], key: &str, default: i64) -> Result<i64, RecordError> {
    match find_record(pairs, key) {
        None => Ok(default),
        Some(value) => value.parse::<i64>().map_err(|_| RecordError::BadInteger),
    }
}

/// 解析单行规范字节（§4.2）为字段结构；严格模式，任何格式偏差都报错。
pub fn parse_row_bytes(block: &[u8]) -> Result<ParsedRow, RecordError> {
    let body = block.strip_prefix(b"row\n").ok_or(RecordError::MissingDomain)?;
    let pairs = parse_records(body)?;

    let mut row = ParsedRow {
        row_id: find_record(&pairs, "row_id").unwrap_or_default().to_string(),
        name: find_record(&pairs, "name").unwrap_or_default().to_string(),
        text: find_record(&pairs, "text").unwrap_or_default().to_string(),
        language: find_record(&pairs, "language")
            .unwrap_or(DEFAULT_LANGUAGE)
            .to_string(),
        voice: find_record(&pairs, "voice").unwrap_or_default().to_string(),
        emotion: find_record(&pairs, "emotion").unwrap_or_default().to_string(),
        speed: parse_int(&pairs, "speed", DEFAULT_SPEED)?,
        pitch: parse_int(&pairs, "pitch", 0)?,
        volume: parse_int(&pairs, "volume", DEFAULT_VOLUME)?,
        seed: parse_int(&pairs, "seed", 0)?,
        key_id: find_record(&pairs, "key_id").unwrap_or_default().to_string(),
        ..ParsedRow::default()
    };

    for (key, value) in &pairs {
        if let Some(suffix) = key.strip_prefix("extra.") {
            row.extra.push((suffix.to_string(), value.clone()));
            continue;
        }
        if matches!(
            key.as_str(),
            "row_id" | "name" | "text" | "language" | "voice" | "emotion" | "speed" | "pitch" | "volume" | "seed" | "key_id"
        ) {
            continue;
        }
        row.unknown.push((key.clone(), value.clone()));
    }
    Ok(row)
}
