# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""许可清单一致性校验器：THIRD_PARTY_LICENSES.md ↔ licenses/ ↔ 许可对话框 ↔ resources.qrc。

背景：清单（`THIRD_PARTY_LICENSES.md` 的「随包许可证文件」一节）、许可查看器
（`app/widgets/license_dialog.py` 的 `_PAGES`）与打包面（`app/resources/resources.qrc`
及其编译产物 `app/resources/resources_rc.py`）三处各自维护同一份文件集合，此前没有任何
自动核对 —— `app/resources/icons/bootstrap-icons-LICENSE.txt` 就是因为三处都没有入口而
在审计中被漏掉。本脚本把这三处互相钉住。

用法：
    .venv/Scripts/python.exe tools/verify_license_catalog.py              # 校验（含子校验脚本）
    .venv/Scripts/python.exe tools/verify_license_catalog.py --json       # 机器可读（纯 ASCII）
    .venv/Scripts/python.exe tools/verify_license_catalog.py --root DIR   # 校验另一棵树（负面自检用）
    .venv/Scripts/python.exe tools/verify_license_catalog.py --no-subprocess
退出码：0 = 没有失败项；1 = 有失败项（`[SKIP]` / `[NOTE]` 不算失败）。
输出一律带 ASCII 标记（`[FAIL]` / `[SKIP]` / `[NOTE]`），断言不必依赖非 ASCII 文案：失败项 id
与文件路径都是 ASCII，判定只看退出码与标记。stdout 在 main() 里改成 UTF-8，否则 Windows
控制台默认的 GBK 会把中文详情打成乱码；`--json` 是纯 ASCII，最稳妥。

失败项 id（ASCII，供测试与 checklist 引用）：
    catalog-doc-missing / catalog-section-missing / licenses-dir-missing
    named-path-missing / named-app-resource-missing / license-file-not-named
    qrc-parse-error / qrc-source-missing / license-dialog-missing / pages-unparsable
    page-resource-not-in-qrc / page-source-missing / qrc-resource-not-in-pages
    compiled-resource-unreadable / compiled-resource-stale / compiled-resource-extra
    bootstrap-icons-license-file-missing / bootstrap-icons-license-not-in-qrc
    ffmpeg-manifest-missing / ffmpeg-verifier-failed
    rust-manifest-missing / rust-verifier-failed
    licenses-manifest-invalid-json / licenses-manifest-entry-missing

非失败项（仅提示，不影响退出码）：
    [SKIP] ffmpeg-verifier-script-missing / rust-verifier-script-missing / subprocess-disabled
    [NOTE] licenses-subdir-not-mentioned / app-resource-not-in-qrc
    [NOTE] bootstrap-icons-via-licenses-dir / bootstrap-icons-via-spec（图标许可走的是哪条入包路线）
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CATALOG_DOC = "THIRD_PARTY_LICENSES.md"
DIALOG = "app/widgets/license_dialog.py"
QRC = "app/resources/resources.qrc"
COMPILED_QRC = "app/resources/resources_rc.py"
ICON_LICENSE = "app/resources/icons/bootstrap-icons-LICENSE.txt"
FFMPEG_MANIFEST = "licenses/ffmpeg/manifest.json"
RUST_MANIFEST = "licenses/rust/manifest.json"
FFMPEG_VERIFIER = "tools/verify_ffmpeg_licenses.py"
RUST_VERIFIER = "tools/collect_rust_binary_licenses.py"
LICENSES_MANIFEST = "licenses/manifest.json"

FAULT_IDS = (
    "catalog-doc-missing",
    "catalog-section-missing",
    "licenses-dir-missing",
    "named-path-missing",
    "named-app-resource-missing",
    "license-file-not-named",
    "qrc-parse-error",
    "qrc-source-missing",
    "license-dialog-missing",
    "pages-unparsable",
    "page-resource-not-in-qrc",
    "page-source-missing",
    "qrc-resource-not-in-pages",
    "compiled-resource-unreadable",
    "compiled-resource-stale",
    "compiled-resource-extra",
    "bootstrap-icons-license-file-missing",
    "bootstrap-icons-license-not-in-qrc",
    "ffmpeg-manifest-missing",
    "ffmpeg-verifier-failed",
    "rust-manifest-missing",
    "rust-verifier-failed",
    "licenses-manifest-invalid-json",
    "licenses-manifest-entry-missing",
)

# 清单目录里允许“只列路径、不逐字点名”的子目录（各自另有 manifest.json 守着）
MANIFEST_SUBDIRS = ("ffmpeg", "rust")

LICENSE_SUFFIXES = (".txt", ".md", ".pdf")

# 上游许可正文里的裸文件名（无目录前缀）也当作清单条目
BARE_NAME_RE = re.compile(r"[A-Za-z0-9._+\-]+\.(?:txt|md|pdf|json)\Z")
REFERENCE_PATH_RE = re.compile(r"(?:licenses|app/resources)/[^\s`)\]\"'()〔〕【】，。；、]+")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
MD_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
RESOURCE_NAME_TOKEN_RE = re.compile(r"[A-Za-z0-9._+\-]{3,}")
RESOURCE_FILE_TOKEN_RE = re.compile(r"[A-Za-z0-9._+\-]+\.(?:txt|md|json|png|ico|svg|qml|pdf)\Z")
NAME_EXTENSIONLESS_OK = ("data", "licenses", "icons", "ffmpeg", "rust")


# --------------------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    id: str
    status: str  # "fail" | "skip" | "note"
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "status": self.status, "detail": self.detail}


@dataclass
class Report:
    root: Path
    findings: list[Finding] = field(default_factory=list)

    def fail(self, id: str, detail: str) -> None:
        self.findings.append(Finding(id, "fail", detail))

    def skip(self, id: str, detail: str) -> None:
        self.findings.append(Finding(id, "skip", detail))

    def note(self, id: str, detail: str) -> None:
        self.findings.append(Finding(id, "note", detail))

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "fail"]

    @property
    def skips(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "skip"]

    @property
    def notes(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "note"]

    @property
    def ok(self) -> bool:
        return not self.failures

    def ids(self, status: str = "fail") -> list[str]:
        return sorted({f.id for f in self.findings if f.status == status})

    def has(self, finding_id: str) -> bool:
        return any(f.id == finding_id for f in self.findings)

    def details(self, finding_id: str) -> list[str]:
        return [f.detail for f in self.findings if f.id == finding_id]

    def as_dict(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "summary": {
                "fail": len(self.failures),
                "skip": len(self.skips),
                "note": len(self.notes),
                "result": "OK" if self.ok else "FAIL",
            },
            "failure_ids": self.ids("fail"),
            "findings": [f.as_dict() for f in self.findings],
        }


@dataclass(frozen=True)
class Page:
    title: str
    resource: str
    is_markdown: bool


@dataclass(frozen=True)
class QrcEntry:
    prefix: str
    alias: str
    source: str
    resolved: Path

    @property
    def resource(self) -> str:
        return f"{self.prefix}/{self.alias}"


# --------------------------------------------------------------------------------------
# 解析辅助（纯标准库；文件缺失一律转成明确失败项，不抛异常）
# --------------------------------------------------------------------------------------


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None


def split_sections(text: str) -> list[tuple[str, str]]:
    """按 `## ` 二级标题切分（返回 [(标题, 正文)]，正文不含标题行）。"""
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    heading = ""
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append((heading, current))
            heading = line[3:].strip()
            current = []
        elif current is not None:
            current.append(line)
    if current is not None:
        sections.append((heading, current))
    return [(h, "\n".join(b)) for h, b in sections]


def find_catalog_section(text: str) -> tuple[str, str] | None:
    """定位逐项点名 `licenses/**` 的那一节（容错：标题措辞可能被改）。"""
    for heading, body in split_sections(text):
        if "许可证文件" in heading and "已知" not in heading:
            return heading, body
    for heading, body in split_sections(text):
        if "许可" in heading and ("随包" in heading or "分发" in heading) and "注意事项" not in heading:
            return heading, body
    return None


def find_art_sections(text: str) -> list[tuple[str, str]]:
    return [(h, b) for h, b in split_sections(text) if any(k in h for k in ("美术", "图标", "字体"))]


def catalog_references(body: str) -> list[str]:
    """从一节正文里抽出候选路径：行内代码、Markdown 链接、裸路径。"""
    raw_tokens: list[str] = []
    raw_tokens += [m.group(1) for m in INLINE_CODE_RE.finditer(body)]
    raw_tokens += [m.group(1) for m in MD_LINK_RE.finditer(body)]
    raw_tokens += [m.group(0) for m in REFERENCE_PATH_RE.finditer(body)]

    out: list[str] = []
    for raw in raw_tokens:
        token = raw.strip().strip("\"'").rstrip(".,;:、，。；")
        token = token.split("#", 1)[0]
        if not token or any(ch in token for ch in "*…<>[]`"):
            continue
        if token.startswith(("licenses/", "app/resources/")) or "/" not in token and BARE_NAME_RE.fullmatch(token):
            candidate = token
        else:
            continue
        if candidate not in out:
            out.append(candidate)
    return out


def resolve_reference(root: Path, token: str) -> Path | None:
    """把清单里的引用解析到磁盘上。裸文件名允许落在仓库根、licenses/ 或其一层子目录里。"""
    rel = token.replace("\\", "/").strip("/")
    if "/" in rel:
        candidate = root / rel
        return candidate if candidate.exists() else None
    for candidate in (root / rel, root / "licenses" / rel):
        if candidate.exists():
            return candidate
    licenses_dir = root / "licenses"
    if licenses_dir.is_dir():
        for sub in sorted(p for p in licenses_dir.iterdir() if p.is_dir()):
            candidate = sub / rel
            if candidate.exists():
                return candidate
    return None


def content_digest(path: Path) -> str:
    """与 tools/verify_ffmpeg_licenses.py::content_digest 同口径（LF 归一后 sha256）。"""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def parse_pages(root: Path, report: Report) -> tuple[list[Page], str | None]:
    """用 ast 解析 `_PAGES`（不导入模块，避免依赖 PySide6）。"""
    dialog = root / DIALOG
    source = read_text(dialog)
    if source is None:
        report.fail("license-dialog-missing", f"{DIALOG} not found or unreadable")
        return [], None
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        report.fail("license-dialog-missing", f"{DIALOG} cannot be parsed: {exc}")
        return [], None
    node_value = None
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "_PAGES":
                node_value = node.value
    if node_value is None:
        report.fail(
            "pages-unparsable",
            f"_PAGES assignment not found in {DIALOG}; the verifier expects "
            "_PAGES = ((title, ':/licenses/<alias>', is_markdown), ...)",
        )
        return [], source
    try:
        raw = ast.literal_eval(node_value)
    except (ValueError, SyntaxError, TypeError) as exc:
        report.fail("pages-unparsable", f"_PAGES is not a literal tuple in {DIALOG}: {exc}")
        return [], source
    pages: list[Page] = []
    for item in raw if isinstance(raw, (tuple, list)) else []:
        if isinstance(item, (tuple, list)) and len(item) >= 2 and isinstance(item[1], str):
            pages.append(Page(str(item[0]), item[1], bool(item[2]) if len(item) > 2 else False))
    if not pages:
        report.fail("pages-unparsable", f"_PAGES in {DIALOG} yielded no (title, resource) entries")
        return [], source
    return pages, source


def parse_qrc(root: Path, report: Report) -> list[QrcEntry]:
    qrc = root / QRC
    text = read_text(qrc)
    if text is None:
        report.fail("qrc-parse-error", f"{QRC} not found or unreadable")
        return []
    try:
        tree = ET.fromstring(text)
    except ET.ParseError as exc:
        report.fail("qrc-parse-error", f"{QRC} is not valid XML: {exc}")
        return []
    entries: list[QrcEntry] = []
    for qresource in tree.iter("qresource"):
        prefix = (qresource.get("prefix") or "").rstrip("/")
        for file_node in qresource.findall("file"):
            source = (file_node.text or "").strip()
            if not source:
                continue
            alias = file_node.get("alias") or Path(source).name
            resolved = Path(os.path.normpath(str(qrc.parent / source)))
            entries.append(QrcEntry(prefix, alias, source, resolved))
    if not entries:
        report.fail("qrc-parse-error", f"{QRC} contains no <file> entries")
    return entries


def extract_resource_names(root: Path) -> set[str] | None:
    """从编译产物 `resources_rc.py` 的 `qt_resource_name` 里恢复资源名。

    该 blob 是“长度 + UTF-16BE 名字 + 头部字段”的混合体，这里同时按 UTF-16BE 与原始
    ASCII 两种方式扫名字片段，避免绑死某一种 rcc 生成格式。无法解析时返回 None。
    """
    source = read_text(root / COMPILED_QRC)
    if source is None:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    blob: bytes | None = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != "qt_resource_name":
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return None
        if isinstance(value, bytes):
            blob = value
    if blob is None:
        return None
    names: set[str] = set()
    names.update(RESOURCE_NAME_TOKEN_RE.findall(blob.decode("utf-16-be", errors="ignore")))
    names.update(m.group(0).decode("ascii", errors="replace") for m in re.finditer(rb"[\x20-\x7e]{3,}", blob))
    return names


def qrc_references(entries: list[QrcEntry], path: Path) -> bool:
    key = os.path.normcase(str(path))
    return any(os.path.normcase(str(e.resolved)) == key for e in entries)


# --------------------------------------------------------------------------------------
# 检查项
# --------------------------------------------------------------------------------------


def check_catalog_doc(root: Path, report: Report) -> tuple[str, str] | None:
    doc = root / CATALOG_DOC
    text = read_text(doc)
    if text is None:
        report.fail("catalog-doc-missing", f"{CATALOG_DOC} not found or unreadable")
        return None
    section = find_catalog_section(text)
    if section is None:
        report.fail(
            "catalog-section-missing",
            f"{CATALOG_DOC} has no second-level section naming the bundled licence files "
            "(expected a '## …许可证文件…' heading)",
        )
        return None
    return section


def check_named_references(
    root: Path, report: Report, section: tuple[str, str], art_sections: list[tuple[str, str]], entries: list[QrcEntry]
) -> None:
    """a/b：清单点名的 licenses/** 与 app/resources/** 路径必须存在。"""
    scopes: list[tuple[str, str]] = [section, *art_sections]
    for heading, body in scopes:
        for token in catalog_references(body):
            is_app_resource = token.startswith("app/resources/")
            if not is_app_resource and (heading, body) != section:
                continue  # licenses/** 只在「随包许可证文件」一节里点名
            resolved = resolve_reference(root, token)
            if resolved is None:
                report.fail(
                    "named-app-resource-missing" if is_app_resource else "named-path-missing",
                    f"{CATALOG_DOC} section {heading!r} names {token!r} but nothing matches it on disk",
                )
                continue
            if token.endswith("/") and not resolved.is_dir():
                report.fail("named-path-missing", f"{token!r} is referenced as a directory but is a file")
                continue
            if is_app_resource and resolved.is_file() and not qrc_references(entries, resolved):
                report.note(
                    "app-resource-not-in-qrc",
                    f"{token!r} is named in the catalogue but not registered in {QRC}",
                )


def check_reverse_coverage(root: Path, report: Report, section: tuple[str, str]) -> None:
    """a（反向）：licenses/ 顶层的 .txt/.md/.pdf 都必须被该节点名。"""
    licenses_dir = root / "licenses"
    if not licenses_dir.is_dir():
        report.fail("licenses-dir-missing", "licenses/ directory not found")
        return
    body = section[1]
    for path in sorted(p for p in licenses_dir.iterdir() if p.is_file()):
        if path.suffix.lower() not in LICENSE_SUFFIXES:
            continue
        if path.name not in body:
            report.fail(
                "license-file-not-named",
                f"licenses/{path.name} exists but is not named in the "
                f"{CATALOG_DOC} section {section[0]!r}",
            )


def check_manifests_present(root: Path, report: Report, doc_text: str | None) -> None:
    """提示：licenses/ 下每个子目录是否在清单里被提到（仅提示，不算失败）。"""
    licenses_dir = root / "licenses"
    if not licenses_dir.is_dir() or doc_text is None:
        return
    for sub in sorted(p for p in licenses_dir.iterdir() if p.is_dir()):
        marker = f"licenses/{sub.name}"
        if marker not in doc_text:
            report.note(
                "licenses-subdir-not-mentioned",
                f"{marker}/ exists but {CATALOG_DOC} never mentions it",
            )


def check_qrc_sources(root: Path, report: Report, entries: list[QrcEntry]) -> None:
    for entry in entries:
        if not entry.resolved.is_file():
            report.fail(
                "qrc-source-missing",
                f"{QRC} registers {entry.resource!r} -> {entry.source!r} but "
                f"{entry.resolved.relative_to(root) if entry.resolved.is_relative_to(root) else entry.resolved} "
                "does not exist",
            )


def check_pages_vs_qrc(root: Path, report: Report, pages: list[Page], entries: list[QrcEntry]) -> None:
    """c/d：对话框每一页 ↔ qrc 里 /licenses 前缀的资源，双向覆盖。"""
    licenses_entries = {e.alias: e for e in entries if e.prefix == "/licenses"}
    page_resources = {p.resource for p in pages}

    for page in pages:
        if not page.resource.startswith(":/licenses/"):
            continue
        alias = page.resource[len(":/licenses/") :]
        entry = licenses_entries.get(alias)
        if entry is None:
            report.fail(
                "page-resource-not-in-qrc",
                f"license dialog page {page.title!r} uses {page.resource!r} but {QRC} has no "
                f"<file alias={alias!r}> under prefix '/licenses' "
                "(the dialog would only show the 'resource unavailable' placeholder)",
            )
            continue
        if not entry.resolved.is_file():
            report.fail(
                "page-source-missing",
                f"license dialog page {page.title!r} -> {entry.resource!r} -> {entry.source!r} "
                "does not exist on disk",
            )

    for alias in sorted(licenses_entries):
        resource = f":/licenses/{alias}"
        if resource not in page_resources:
            report.fail(
                "qrc-resource-not-in-pages",
                f"{QRC} registers {resource!r} but no _PAGES entry shows it "
                "(the file is packaged yet unreachable in the licence viewer)",
            )


def check_compiled_qrc(root: Path, report: Report, entries: list[QrcEntry], run: bool = True) -> None:
    """g：resources.qrc 与编译产物 resources_rc.py 是否同步（改 qrc 忘重编译 = 运行期缺页）。"""
    if not run:
        report.skip("compiled-resource-check", "compiled resource check disabled")
        return
    compiled_path = root / COMPILED_QRC
    if not compiled_path.is_file():
        report.skip("compiled-resource-missing", f"{COMPILED_QRC} not found; staleness check skipped")
        return
    names = extract_resource_names(root)
    if not names:
        report.fail(
            "compiled-resource-unreadable",
            f"{COMPILED_QRC} exists but no resource names could be recovered from "
            "qt_resource_name (regenerate it with pyside6-rcc)",
        )
        return
    aliases = {e.alias for e in entries}
    for alias in sorted(aliases):
        if alias not in names:
            report.fail(
                "compiled-resource-stale",
                f"{QRC} registers alias {alias!r} but {COMPILED_QRC} does not embed it; "
                "regenerate with pyside6-rcc (otherwise that page shows only the placeholder)",
            )
    for name in sorted(names):
        if RESOURCE_FILE_TOKEN_RE.fullmatch(name) and name not in aliases:
            report.fail(
                "compiled-resource-extra",
                f"{COMPILED_QRC} embeds {name!r} which {QRC} no longer registers",
            )


def packaging_collects_icons(root: Path) -> tuple[bool, list[str]]:
    """打包声明里是否收 `app/resources/icons/`（Bootstrap Icons 走文件系统加载，不进 qrc）。

    判定：凡是提到 `app/resources` 的根级 `*.spec` 都必须同时提到 `icons`。
    返回 (是否全部覆盖, 漏收的 spec 文件名列表)；没有任何相关 spec 时返回 (False, [])。
    """
    relevant: list[Path] = []
    for spec in sorted(p for p in root.glob("*.spec") if p.is_file()):
        text = read_text(spec) or ""
        if "app/resources" in text.replace("\\", "/"):
            relevant.append(spec)
    if not relevant:
        return False, []
    missing: list[str] = []
    for spec in relevant:
        text = (read_text(spec) or "").replace("\\", "/")
        if not re.search(r"app/resources/icons|resources['\"]\s*/\s*['\"]icons", text):
            missing.append(spec.name)
    return (not missing), missing


def check_bootstrap_icons(
    root: Path, report: Report, entries: list[QrcEntry], section: tuple[str, str] | None
) -> None:
    """f：Bootstrap Icons 的许可正文必须真的进打包面（本次审计漏掉的那一项）。

    三条同样合规的路线，任一成立即可：
      1) qrc 直接注册 `app/resources/icons/bootstrap-icons-LICENSE.txt`；
      2) 同一份正文收进 `licenses/`（`*ootstrap*`）并在清单里点名、且进了 qrc；
      3) 图标走文件系统加载，因此所有收 `app/resources` 的 `.spec` 都一并收 `app/resources/icons/`。
    """
    icon_path = root / ICON_LICENSE
    if not icon_path.is_file():
        report.fail("bootstrap-icons-license-file-missing", f"{ICON_LICENSE} not found")
        return
    if qrc_references(entries, icon_path):
        return

    alternatives = [
        e
        for e in entries
        if e.resolved.is_file()
        and e.resolved.parent == (root / "licenses")
        and "ootstrap" in e.resolved.name.lower()
    ]
    registered = [e for e in alternatives if section is not None and e.resolved.name in section[1]]
    if registered:
        report.note(
            "bootstrap-icons-via-licenses-dir",
            f"{ICON_LICENSE} is not registered in {QRC}, but the icon licence is covered by "
            + ", ".join(sorted(e.resolved.name for e in registered)),
        )
        return

    spec_ok, spec_missing = packaging_collects_icons(root)
    if spec_ok:
        report.note(
            "bootstrap-icons-via-spec",
            f"{ICON_LICENSE} ships from the filesystem (nav_rail.py loads it by path) and every "
            "app/resources .spec collects app/resources/icons/",
        )
        return

    detail = (
        f"{ICON_LICENSE} exists on disk but no packaging route reaches it: "
        f"(1) {QRC} has no entry for it; (2) no licenses/*ootstrap* file is both registered in "
        f"{QRC} and named in the catalogue; (3) "
    )
    if spec_missing:
        detail += "these .spec files collect app/resources but not app/resources/icons/: " + ", ".join(spec_missing)
    else:
        detail += "no root-level .spec collects app/resources/icons/ (and none packages app/resources)"
    report.fail("bootstrap-icons-license-not-in-qrc", detail)


def _tail(text: str, limit: int = 400) -> str:
    text = " ".join(text.split())
    return text[-limit:]


def run_bundled_verifier(
    root: Path, report: Report, script_rel: str, check_prefix: str, run_subprocess: bool, timeout: int = 900
) -> None:
    """e：复用别的脚本的校验逻辑，只按退出码判定；脚本不存在＝跳过并提示。"""
    if not run_subprocess:
        report.skip(f"{check_prefix}-verifier-skipped", "subprocess checks disabled (--no-subprocess)")
        return
    script = root / script_rel
    if not script.is_file():
        report.skip(
            f"{check_prefix}-verifier-script-missing",
            f"{script_rel} not found; manifest re-verification skipped (NOT counted as a failure)",
        )
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        report.fail(f"{check_prefix}-verifier-failed", f"{script_rel} timed out after {timeout}s")
        return
    except OSError as exc:
        report.fail(f"{check_prefix}-verifier-failed", f"{script_rel} could not be started: {exc}")
        return
    if proc.returncode != 0:
        report.fail(
            f"{check_prefix}-verifier-failed",
            f"{script_rel} exit={proc.returncode}; stdout tail: {_tail(proc.stdout)} | "
            f"stderr tail: {_tail(proc.stderr, 200)}",
        )


def check_manifests(root: Path, report: Report, run_subprocess: bool) -> None:
    if not (root / FFMPEG_MANIFEST).is_file():
        report.fail(
            "ffmpeg-manifest-missing",
            f"{FFMPEG_MANIFEST} not found; the bundled FFmpeg licence texts have no machine-checkable manifest",
        )
    else:
        run_bundled_verifier(root, report, FFMPEG_VERIFIER, "ffmpeg", run_subprocess)

    if not (root / RUST_MANIFEST).is_file():
        report.fail(
            "rust-manifest-missing",
            f"{RUST_MANIFEST} not found; the Rust crate licence texts shipped with the vtcore "
            "binary have no machine-checkable manifest",
        )
    else:
        run_bundled_verifier(root, report, RUST_VERIFIER, "rust", run_subprocess)


def resolve_manifest_entry(root: Path, value: str) -> Path | None:
    """容忍三种常见写法：仓库根相对、licenses/ 相对、licenses/ 下某一层子目录相对。"""
    rel = value.replace("\\", "/").lstrip("/")
    for candidate in (root / rel, root / "licenses" / rel):
        if candidate.is_file():
            return candidate
    suffix = "/" + rel
    licenses_dir = root / "licenses"
    if licenses_dir.is_dir():
        for path in licenses_dir.rglob("*"):
            if path.is_file() and path.as_posix().endswith(suffix):
                return path
    return None


def check_licenses_manifest(root: Path, report: Report) -> None:
    """可选：若 lead 生成了 licenses/manifest.json，则核对它点到的文件都存在。"""
    path = root / LICENSES_MANIFEST
    if not path.is_file():
        return
    text = read_text(path)
    try:
        data = json.loads(text or "")
    except (ValueError, TypeError) as exc:
        report.fail("licenses-manifest-invalid-json", f"{LICENSES_MANIFEST} is not valid JSON: {exc}")
        return
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        report.note(
            "licenses-manifest-schema-unrecognized",
            f"{LICENSES_MANIFEST} has no top-level 'files' list; entry existence check skipped",
        )
        return
    for item in files:
        if not isinstance(item, dict):
            continue
        value = item.get("file")
        if not isinstance(value, str) or not value:
            continue
        if resolve_manifest_entry(root, value) is None:
            report.fail(
                "licenses-manifest-entry-missing",
                f"{LICENSES_MANIFEST} lists {value!r} but no such file exists under licenses/",
            )


# --------------------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------------------


def verify_catalog(root: Path, *, run_subprocess: bool = True, check_compiled: bool = True) -> Report:
    root = Path(root).resolve()
    report = Report(root=root)

    section = check_catalog_doc(root, report)
    doc_text = read_text(root / CATALOG_DOC)
    art_sections = find_art_sections(doc_text) if doc_text else []
    entries = parse_qrc(root, report)
    pages, _dialog_source = parse_pages(root, report)

    check_qrc_sources(root, report, entries)
    if section is not None:
        check_named_references(root, report, section, art_sections, entries)
        check_reverse_coverage(root, report, section)
    else:
        licenses_dir = root / "licenses"
        if not licenses_dir.is_dir():
            report.fail("licenses-dir-missing", "licenses/ directory not found")
    check_bootstrap_icons(root, report, entries, section)
    check_manifests_present(root, report, doc_text)
    if pages:
        check_pages_vs_qrc(root, report, pages, entries)
    check_compiled_qrc(root, report, entries, run=check_compiled)
    check_manifests(root, report, run_subprocess)
    check_licenses_manifest(root, report)
    return report


def _p(line: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        print(line.encode(encoding, "backslashreplace").decode(encoding, "replace"))
    except (LookupError, UnicodeDecodeError):
        print(line.encode("ascii", "backslashreplace").decode("ascii", "replace"))


def print_report(report: Report, *, quiet: bool = False) -> None:
    _p(f"license catalog check: {report.root}")
    for finding in report.findings:
        if quiet and finding.status == "note":
            continue
        marker = {"fail": "[FAIL]", "skip": "[SKIP]", "note": "[NOTE]"}[finding.status]
        _p(f"{marker} {finding.id}: {finding.detail}")
    summary = report.as_dict()["summary"]
    _p(
        "summary: fail={fail} skip={skip} note={note} result={result}".format(**summary)  # type: ignore[arg-type]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the licence catalogue stays consistent.")
    parser.add_argument("--root", default=None, help="tree to check (default: this repository)")
    parser.add_argument("--json", action="store_true", help="print an ASCII-only JSON report instead of lines")
    parser.add_argument("--no-subprocess", action="store_true", help="skip the bundled verify_* scripts")
    parser.add_argument("--no-compiled", action="store_true", help="skip the resources_rc.py staleness check")
    parser.add_argument("--quiet", action="store_true", help="suppress [NOTE] lines")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else ROOT
    report = verify_catalog(root, run_subprocess=not args.no_subprocess, check_compiled=not args.no_compiled)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=True, indent=2))
    else:
        print_report(report, quiet=args.quiet)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
