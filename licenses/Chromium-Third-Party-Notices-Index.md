# Qt WebEngine / Chromium 捆绑第三方组件声明索引

**本文件是索引与边界声明，不是全量名录。** Chromium 内含大量第三方组件（上游 `about:credits` 逐项列举，数量随版本变化），
其许可声明**不**收录在本文件里，也不由本项目重新声明归属；本文件只登记
「哪些部分由谁授权、到上游哪里去找完整名录、本项目的分发边界在哪里」。

## 1. 组件与版本（本机实测证据）

| 组件 | 版本 | 证据 |
|------|------|------|
| PySide6 / Qt | 6.7.3 | `requirements.txt` 第 1 行 `PySide6==6.7.3` |
| Qt WebEngine | 6.7.3 | `PySide6\Qt6WebEngineCore.dll`（149,048,984 字节）等文件存在于 `.venv\Lib\site-packages\PySide6\`；应用侧使用见 `app\pages\api_channel_page.py` 第 118–140 行、`app\services\hub_scheme.py` 第 24–52 行 |
| Chromium（由 Qt WebEngine 6.7.3 携带） | **118.0.5993.220** | ① 本机 `PySide6\Qt6WebEngineCore.dll` 内二进制串扫描只出现一个 UUID 型 UA 版本串 `Chrome/118.0.5993.220`（唯一命中，无其他候选）；② 上游 Qt 官方对照表 <https://wiki.qt.io/QtWebEngine/ChromiumVersions>：`6.7.3 → 118.0.5993.220`（118-based） |

> 版本说明：上游对照表中 6.7.0–6.7.3 各行的 Chromium 版本列均为 `118.0.5993.220`、分支列均为 `118-based`，
> 因此本索引中的版本号可以按「118-based」理解；若日后升级 PySide6，须重新抓取本表并按新版本更新。

## 2. Chromium 本体的许可（本项目已落盘）

Chromium 本体按 **BSD-3-Clause** 授权，正文（含 `// Copyright 2015 The Chromium Authors` 版权行）
见 `licenses/Chromium-BSD-3-Clause.txt`，为逐字上游原文（1,536 字节，LF 归一
sha256 = `368cca1106be99d39ecd32a38d8305585d802a475effb66380b91ffc9bcf709b`，
经 jsdelivr、ghproxy 与 `118.0.5993.220` 版本 tag 三路抓取比对一致）。

## 3. 捆绑第三方组件的声明在哪里（上游入口）

- 上游源码目录：<https://chromium.googlesource.com/chromium/src/+/main/third_party/>
  （本次出网环境下**未能抓取**：直连超时、经 `http://127.0.0.1:26561` 代理返回 502；此处仅登记入口，未实测内容。）
- 上游运行时声明页：Chromium 内建的 `chrome://credits` / `about:credits` 页面，
  逐项列举其捆绑第三方组件与许可文本，内容随 Chromium 版本变化（体量数 MB）。
  本机未实测 Qt WebEngine 是否对外暴露该页面。
- Qt / PySide6 侧：Qt WebEngine 的第三方组件声明按 Qt 的授权路径随上游分发。
  **本机事实**：`.venv\Lib\site-packages\PySide6` 树下按 `LICENSE*`/`LICENCE*`/`COPYING*`/`NOTICE*`
  检索只命中 3 个 Qt 商业许可标记文件（`PySide6*6.7.3.dist-info\LicenseRef-Qt-Commercial.txt`），
  **未发现** `LICENSE.Chromium` 一类随 wheel 分发的第三方名录文件。

## 4. 本项目的边界

- 按现有声明文件 `licenses/QtWebEngine-Chromium-Notice.md` 的口径：本项目**不打包、不分发、不修改**
  Qt WebEngine / Chromium 的二进制，该组件由使用者经 `pip` 自行安装 PySide6 6.7.3
  （见 `requirements.txt`），可自行替换为修改版。**注意**：本次核对发现三个 spec
  （`WT-NameRelay.spec` / `WT-NameRelay-onedir.spec` / `WT-NameRelay-debug.spec`）第 26 行的
  `excludes` 均只有 `pyqtgraph.opengl`、`OpenGL`，未排除 PySide6，onedir / EXE 产物是否真的不含
  Qt / Chromium 二进制应以发布目录实测为准，见第 5 节第 4 条。
- 内嵌渲染只加载本机可信内容（`hub://` 协议，见 `app\services\hub_scheme.py`），不创建对外网络连接。
- 使用方式与 LGPL-3.0 授权路径的说明见 `licenses/QtWebEngine-Chromium-Notice.md`
  （该文件讲「怎么用、按什么授权」；本文件讲「Chromium 捆绑第三方名录的边界」，两者不重复）。

## 5. 已知边界 / 待办（合规提示）

1. 本仓库**没有**归档上游 `about:credits` 的全量文本，也没有归档 `third_party` 逐目录清单。
   若发布合规要求「随发布物提供 Chromium 完整第三方声明」，需要另行从上游按当前
   Chromium 版本提取（数 MB 级），本索引不替代它。
2. 本机 PySide6 6.7.3 wheel 内未见 Chromium 第三方名录文件，因此**不能**以
   「上游已经随组件分发」当作本项目已履行声明义务的证明；实际义务归属取决于分发方式
   （本项目不分发该二进制）。
3. 本文件未逐项核对 Chromium 内部各第三方组件的具体许可标识（依赖上游声明），
   也未对 Chromium 的专利/商标条款作任何判断。
4. **待复核（本次新发现，未下结论）**：三个 spec（`WT-NameRelay.spec`、`WT-NameRelay-onedir.spec`、
   `WT-NameRelay-debug.spec`）第 26 行的 `excludes` 都只有 `pyqtgraph.opengl`、`OpenGL`，未排除 PySide6。
   若 PyInstaller 的 PySide6 hook 把 Qt WebEngine / Chromium 二进制（含约 149 MB 的
   `Qt6WebEngineCore.dll`）收进产物，则 `licenses/QtWebEngine-Chromium-Notice.md` 中
   「不打包、不分发该二进制」的表述与实际发布物不符，Chromium 第三方声明的义务范围也会随之变化。
   本文件不作判断，仅登记该复核点。

5. 本文件是索引，不构成法律意见。

## 6. 取证记录

| 项 | 结果 |
|----|------|
| `requirements.txt` → `PySide6==6.7.3` | 已读，第 1 行 |
| `PySide6\Qt6WebEngineCore.dll` 内 `Chrome/<ver>` 串扫描 | 唯一命中 `Chrome/118.0.5993.220` |
| <https://wiki.qt.io/QtWebEngine/ChromiumVersions> | HTTP 200，49,838 字节；表中 6.7.3 行 = `118.0.5993.220` |
| Chromium 根 `LICENSE`（jsdelivr / ghproxy / 118 tag 三路） | 均 HTTP 200，sha256(LF) 三者一致 = `368cca11…cf709b` |
| 同上：表格行解析（82 行中筛 6.7/6.8） | `6.7.3 \| 118.0.5993.220 \| 129.0.6668.58 \| 6.7.3 \| 118-based`；6.7.0–6.7.3 的 Chromium 列均为 `118.0.5993.220` |
| 三个 `.spec` 的 `excludes` | 均仅 `pyqtgraph.opengl`、`OpenGL`（第 26 行），未排除 PySide6 |
| <https://chromium.googlesource.com/chromium/src/+/main/third_party/> | **抓取失败**（直连超时 / 代理 502），未实测 |
| `.venv\Lib\site-packages\PySide6` 下许可类文件检索 | 仅 3 个 `LicenseRef-Qt-Commercial.txt`，无 Chromium 名录 |
