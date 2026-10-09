# licenses/rust —— vtcore 预编译 wheel 内 Rust crate 许可正文清单

本目录的文本均为**上游逐字原文**（LF 归一后与 crate 包内文件逐字节一致），
由 `licenses/rust/manifest.json` 记录 sha256；校验：`python tools/collect_rust_binary_licenses.py`。
重新生成：`python tools/collect_rust_binary_licenses.py --write`。

## 范围与权威口径

- 范围：`vtcore/wheels/vtcore-0.1.0-cp312-abi3-win_amd64.whl 内实际链入的第三方 crate`。
- 组件集合取自该 wheel 内的 CycloneDX SBOM `vtcore-0.1.0.dist-info/sboms/vtcore.cyclonedx.json`，共 **45** 个组件。
- **不要**用 `vtcore/Cargo.lock` 的第三方 crate 数（**53** 个）当范围：
  该锁文件共 54 个 `[[package]]`，扣除根包 `vtcore-0.1.0` 后为 53 个第三方 crate，
  其中多出的组件属于 dev-only 的 serde_json 链，未链入 `vtcore.pyd`。

## 统计

| crate 数（SBOM 组件） | 45 |
| 许可正文文件数 | 91 |
| 上游未随包携带正文的 crate 数 | 1 |

## 哈希与行尾口径

- 哈希：`sha256 按 LF 归一后的内容计算（content_digest），与工作区 CRLF 无关（同 licenses/ffmpeg/manifest.json 口径）`
- 与 `tools/verify_ffmpeg_licenses.py::content_digest` 实现**完全同口径**
  （`sha256(read_bytes().replace(b"\r\n", b"\n"))`），因此可与上游逐字比对。
- 工作区行尾：`.gitattributes` 的 `* text=auto eol=crlf` 生效，本目录文本以 CRLF 落盘；
  这**不影响** `content_digest`，故清单中的 sha256 仍是 LF 归一后的值。
- 采集文件的文件名模式（大小写不敏感）：`LICENSE*`、`LICENCE*`、`COPYING*`、`NOTICE*`、`UNLICENSE*`、`COPYRIGHT*`；嵌套深度上限 1 层
  （用于覆盖 `pyo3` 随包携带的 `pyo3-runtime/LICENSE-*`）。
- 采集来源（离线，未联网）：优先已解包的本机 cargo `registry/src` 目录；
  目录不存在时回退到本机 cargo `registry/cache/*.crate` 压缩包（纯标准库 `tarfile` 读取）。  具体绝对路径不入公开清单（`manifest.json` 的 `source_path` 亦只保留相对两段）。
  本次按来源统计：`registry-src` 45 个、`registry-cache-crate` 0 个。
  每个 crate 的实际来源见 `manifest.json` 的 `crates[].source_kind` / `source_path`。

## 许可正文一览

| crate | 版本 | SPDX（取自 SBOM） | 正文文件 | sha256 前 12 位 |
| --- | --- | --- | --- | --- |
| `aead` | 0.6.1 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `b1cf9a3333ca`<br>`33b32a251d44` |
| `block-buffer` | 0.12.1 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`98181e7249d0` |
| `cfg-if` | 1.0.5 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a60eea817514`<br>`378f5840b258` |
| `chacha20` | 0.10.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`b8c6939380a4` |
| `chacha20poly1305` | 0.11.0 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`b8c6939380a4` |
| `cipher` | 0.5.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`950d712c518a` |
| `cmov` | 0.5.4 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `cfc7749b96f6`<br>`70c9d40f1f95` |
| `const-oid` | 0.10.2 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`73b9dc2e79c7` |
| `cpufeatures` | 0.3.1 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`73b9dc2e79c7` |
| `crypto-common` | 0.2.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`d2e7ec5355c9` |
| `ctutils` | 0.4.2 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `cfc7749b96f6`<br>`91585c36e4fb` |
| `curve25519-dalek` | 5.0.0 | `BSD-3-Clause` | `LICENSE` | `403c53069750` |
| `curve25519-dalek-derive` | 0.1.1 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a60eea817514`<br>`23f18e03dc49` |
| `digest` | 0.11.3 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`af59cea35d7f` |
| `ed25519` | 3.0.0 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `78779d420019`<br>`9aa4f92bfcde` |
| `ed25519-dalek` | 3.0.0 | `BSD-3-Clause` | `LICENSE` | `7a313964a6e0` |
| `fiat-crypto` | 0.3.0 | `MIT OR Apache-2.0 OR BSD-1-Clause` | `COPYRIGHT`<br>`LICENSE-APACHE`<br>`LICENSE-BSD-1`<br>`LICENSE-MIT` | `6c935d087a29`<br>`9eacbcb81be6`<br>`0c1240e29b4a`<br>`0034712d5e97` |
| `getrandom` | 0.4.3 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `aaff376532ea`<br>`523a42c25d24` |
| `heck` | 0.5.0 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a60eea817514`<br>`7b63ecd5f190` |
| `hybrid-array` | 0.4.15 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`70c9d40f1f95` |
| `inout` | 0.2.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`a07fcacc3c60` |
| `libc` | 0.2.189 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `62c7a1e35f56`<br>`123a331b5dbf` |
| `once_cell` | 1.21.4 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a60eea817514`<br>`23f18e03dc49` |
| `poly1305` | 0.9.1 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`b67acfaaf787` |
| `portable-atomic` | 1.15.0 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `0d542e0c8804`<br>`23f18e03dc49` |
| `proc-macro2` | 1.0.107 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `62c7a1e35f56`<br>`23f18e03dc49` |
| `pyo3` | 0.29.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT`<br>`pyo3-runtime/LICENSE-APACHE`<br>`pyo3-runtime/LICENSE-MIT` | `32c76dbe0e73`<br>`afcbe3b2e6b3`<br>`32c76dbe0e73`<br>`afcbe3b2e6b3` |
| `pyo3-build-config` | 0.29.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `32c76dbe0e73`<br>`afcbe3b2e6b3` |
| `pyo3-ffi` | 0.29.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `32c76dbe0e73`<br>`afcbe3b2e6b3` |
| `pyo3-macros` | 0.29.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `32c76dbe0e73`<br>`afcbe3b2e6b3` |
| `pyo3-macros-backend` | 0.29.2 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `32c76dbe0e73`<br>`afcbe3b2e6b3` |
| `quote` | 1.0.47 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `62c7a1e35f56`<br>`23f18e03dc49` |
| `r-efi` | 6.0.0 | `MIT OR Apache-2.0 OR LGPL-2.1-or-later` | **（上游未随包携带任何许可正文）** | — |
| `rand_core` | 0.10.1 | `MIT OR Apache-2.0` | `COPYRIGHT`<br>`LICENSE-APACHE`<br>`LICENSE-MIT` | `92b81db30f7a`<br>`6df43f6f4b5d`<br>`8b6e9feec03e` |
| `rustc_version` | 0.4.1 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a60eea817514`<br>`c9a75f18b9ab` |
| `semver` | 1.0.28 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `62c7a1e35f56`<br>`23f18e03dc49` |
| `sha2` | 0.11.0 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`831e0f43ad0b` |
| `signature` | 3.0.0 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`9aa4f92bfcde` |
| `subtle` | 2.6.1 | `BSD-3-Clause` | `LICENSE` | `d1fc1bc0d155` |
| `syn` | 2.0.119 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `62c7a1e35f56`<br>`23f18e03dc49` |
| `target-lexicon` | 0.13.5 | `Apache-2.0 WITH LLVM-exception` | `LICENSE` | `268872b9816f` |
| `typenum` | 1.20.1 | `MIT OR Apache-2.0` | `LICENSE`<br>`LICENSE-APACHE`<br>`LICENSE-MIT` | `db11fec99467`<br>`516b24e051bf`<br>`a825bd853ab7` |
| `unicode-ident` | 1.0.26 | `(MIT OR Apache-2.0) AND Unicode-3.0` | `LICENSE-APACHE`<br>`LICENSE-MIT`<br>`LICENSE-UNICODE` | `62c7a1e35f56`<br>`23f18e03dc49`<br>`f7db81051789` |
| `universal-hash` | 0.6.1 | `MIT OR Apache-2.0` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `a9040321c371`<br>`efa52eb70a77` |
| `zeroize` | 1.9.0 | `Apache-2.0 OR MIT` | `LICENSE-APACHE`<br>`LICENSE-MIT` | `cfc7749b96f6`<br>`8c7516d4b27b` |

## 上游未随包携带许可正文的 crate

以下 crate 在其 crate 包内**没有任何**许可/声明文件——已按 SBOM 的 SPDX 表达式登记，
但**未臆造正文**（也未去网上另抓一份来冒充「上游随包文本」）：

- `r-efi-6.0.0` —— SPDX `MIT OR Apache-2.0 OR LGPL-2.1-or-later`；来源 `registry-src`（相对路径 `index.crates.io-1949cf8c6b5b557f/r-efi-6.0.0`）。

> `r-efi` 的补充证据：**两处来源都已核对过，均无许可正文** ——
> (1) 已解包的源码目录 `registry/src/…/r-efi-6.0.0/`（70 个文件）：
>     名字命中 `LICENSE*`/`LICENCE*`/`COPYING*`/`NOTICE*`/`UNLICENSE*`/`COPYRIGHT*` 的文件数 = **0**
>     （唯一的法律相关文件是 `AUTHORS`，署名名单，按口径不采集）；
> (2) `.crate` 压缩包 `registry/cache/…/r-efi-6.0.0.crate`（65,303 B、69 个成员）：
>     同样只有 `r-efi-6.0.0/AUTHORS` 一个名字命中，**没有**许可正文。
> 上游自述：`Cargo.toml` 第 39 行 `license = "MIT OR Apache-2.0 OR LGPL-2.1-or-later"`，
> 但 `README.md` 第 96–99 行的 License 节只写「See AUTHORS file for details」，包内并无 `LICENSE*`。
> 三选一授权中的 MIT / Apache-2.0 均为宽松许可，可**选择**其一；
> 本清单保留 `license_file: null`，**不代上游补正文，也不另抓一份冒充「随包原文」**。

## 已知边界

- 本清单只证明「已随包收齐各 crate 上游自带的许可/声明正文，且与上游逐字一致」，
  **不构成法律意见**，也不代表全部许可义务已履行；
  也不证明「该二进制真的只含这些组件」（见下一条）。
- SBOM 是**依赖图**快照（cargo-cyclonedx 按依赖图生成，**不是链接闭包**），**不等于**「与 `vtcore.pyd` 实际链接的符号集合」。
  实测一例：`r-efi` 只被 `getrandom` 的 **UEFI target** 使用 —— `getrandom-0.4.3/Cargo.toml` 第 103 行
  `[target.'cfg(all(target_os = "uefi", getrandom_backend = "efi_rng"))'.dependencies.r-efi]`；
  **Windows x64 下它不会链入 `vtcore.pyd`**，出现在 SBOM 里纯属依赖图口径。
  因此 45 是**上界**；要证明下界需要 `cargo auditable` / 链接映射级别的证据。
  **但不要因此把它从清单里删掉**：本清单的 crate 集合与 `THIRD_PARTY_LICENSES.md` 的「Cargo.lock 53 个第三方 crate」是**两种口径并存**，宁多勿少。
- `pyo3-0.29.2` 额外随包携带 `pyo3-runtime/LICENSE-APACHE` 与 `pyo3-runtime/LICENSE-MIT`
  （与根目录两份逐字节相同），脚本按「镜像 crate 包内布局」一并收下。
- `typenum-1.20.1/LICENSE` 是 17 字节的 SPDX 指针（内容仅 `MIT OR Apache-2.0`），
  不是许可正文；该 crate 的正文在同目录 `LICENSE-APACHE` / `LICENSE-MIT`。
- 采集的文件名模式是任务口径的**保守超集**：除 `LICENSE*`/`LICENCE*`/`COPYING*`/`NOTICE*`/`UNLICENSE*` 外还收 `COPYRIGHT*`
  （`fiat-crypto-0.3.0/COPYRIGHT`、`rand_core-0.10.1/COPYRIGHT`）。
  去掉这两份后文件数为 89；本次为 91。`AUTHORS` 未采集（署名名单，非许可文本）。
- 目录名 `licenses/rust/` 下的 crate 集合、版本号、SPDX 表达式均以 SBOM 为准，
  脚本不擅自增删组件；SPDX 一律取自 SBOM，不手改。
