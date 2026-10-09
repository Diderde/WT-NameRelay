# Qt WebEngine / Chromium 使用与许可声明

本应用的「API 渠道」页通过 **Qt WebEngine 6.7.3**（随 PySide6-Addons 分发的官方组件）
内嵌渲染 TTS-Hub 管理台页面。

## 使用方式与授权路径

- Qt WebEngine 以 **GNU LGPL-3.0** 授权使用（动态链接；与本项目使用 PySide6 / Qt 的
  授权路径一致）。本应用**不打包、不分发** PySide6 / Qt WebEngine 的二进制——
  该组件由使用者经 `pip` 自行安装（见 `requirements.txt` 的 `PySide6==6.7.3`），
  可自行替换为修改版，满足 LGPL-3.0 对「可替换 / 可逆向 / 提供安装信息」的要求。

> **必须核实的边界（2026-10 标注）**：上句只对**源码分发**成立。若用 `WT-NameRelay*.spec`
> 构建 PyInstaller 产物，Qt / Qt WebEngine / Chromium 的**二进制会被一并打包**（三份 spec 的
> `excludes` 只排了 `pyqtgraph.opengl` 与 `OpenGL`，都没有排 PySide6）。因此二进制分发路径下，
> LGPL 的源码可得与安装信息义务、以及 Chromium 的第三方声明义务都必须单独履行 —— 见
> `THIRD_PARTY_LICENSES.md`「随包许可证文件」与
> `licenses/Chromium-Third-Party-Notices-Index.md`。
> 该打包结果**尚未实测验证**：本机未安装 PyInstaller，且 PyInstaller 各版本对
> QtWebEngine 的收集策略不同，必须以真实产物清单为准。
- 页面内嵌渲染的 **Chromium** 部分由 Qt WebEngine 携带，按
  **BSD-3-Clause** 及其捆绑第三方组件的各自许可授权（Chromium 内含大量第三方组件，
  其许可声明由 Qt / Chromium 上游随组件分发，本项目不修改、不再分发该部分二进制）。

## 与本应用的边界

- 内嵌区只加载**本机可信内容**：TTS-Hub 管理台页面（经进程内 `hub://` 协议分发，
  不创建网络连接）与应用内页面；
- 厂商密钥全部保存在 TTS-Hub 服务侧，本应用不读取、不保存、不记录。

完整法律文本：

- LGPL-3.0 正文见许可查看器「PySide6 / Qt 6.7.3 — LGPL-3.0」页与发布目录
  `licenses/LGPL-3.0.txt`；
- 组件来源、版本与用途汇总见 `THIRD_PARTY_LICENSES.md`；
- 本声明不构成法律意见。
