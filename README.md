# WT-Tool-Experimental Version

> **本仓库是 fork，不是原项目的官方版本。** 本仓库是 [Beiku（@beikuwawa）](https://github.com/beikuwawa) 的原项目 [WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay)（beta 0.2.0）的实验性 fork，由 Diderde（[@Diderde](https://github.com/Diderde)）制作与维护，仅供个人学习与实验使用，不构成正式发布版本。

 **本仓库所有内容依然处于不完善的阶段，请勿将其视为最终版本。** 欢迎提交Issue报告你所遇到的问题。

- 原始项目：[WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay)（原始作者：Beiku，原始仓库：`beikuwawa/WT-NameRelay`）
- 基线版本：beta 0.2.0
- 修改与新增代码按 GPL-3.0-only 授权，原始代码仍按原始许可授权；来源与许可分层详见 [`MODIFICATION_NOTICE.md`](MODIFICATION_NOTICE.md)。

本项目是非官方第三方工具，不包含、不提供也不分发任何游戏官方资源或官方音频，与 Gaijin Entertainment、War Thunder及其关联主体不存在授权、赞助或合作关系。

> 原始代码按 WT-NameRelay Source-Available License 1.0（[`LICENSE`](LICENSE)）授权，不是 OSI 定义的开源软件：允许个人非商业使用与同许可源码分享，禁止未经许可的商业使用、二次售卖、付费分发和捆绑收费。使用注意事项见 [`PROJECT_USAGE_NOTICE.md`](PROJECT_USAGE_NOTICE.md)。

## 环境与启动

项目验证环境：Windows、Python 3.11.5、PySide6 6.7.3、Qt 6.7.3、PyQtGraph 0.13.7、NumPy 1.26.4。

```powershell
cd "<项目目录>"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

也可以直接运行 `start.bat`（自动创建虚拟环境并安装依赖）。`start.bat` 启动前会执行三段式检查：

1. **环境与文件检查**：git / curl 工具、Python 虚拟环境、`TTS model\` 下的 GPT-SoVITS 代码、CosyVoice3 GGUF 与 GPT-SoVITS 预训练权重；
2. **按需补齐**：虚拟环境缺失时自动创建；TTS 模型资源缺失时弹出 Y/N 询问，确认后调用同目录 `download_tts_verify.bat` 下载（GitHub 浅克隆 GPT-SoVITS 代码、hf-mirror 下载 CosyVoice3 GGUF 与 25 个 GPT-SoVITS 预训练权重，支持断点续传与已完成跳过，自动适配系统代理）；
3. **启动**：全部就绪后运行主程序。

TTS 模型统一存放在 `TTS model\` 下并按模型名分目录（`GPT-SoVITS\` 含代码与权重、`CosyVoice3\` 为 GGUF 权重），该目录已加入 `.gitignore` 不入库；权重清单见 `gpt_sovits_weights_list.txt`。

## 可选组件：vtcore（Rust 扩展）

`.vt` 工程容器、Ed25519 签名与整包校验由 Rust 扩展 `vtcore` 提供（源码在 `vtcore/`，构建后以 abi3 扩展装入虚拟环境）。

**不构建它应用照样能跑**：规范字节（`spec_hash`）自动回退到 Python 参考实现，数值与扩展路径**逐字节一致**（两侧读同一份黄金向量做测试）；但签名、`.vt` 容器、TOFU 信任库与 `.vtmanifest` 整包校验会不可用，调用时报 `vtcore_missing`。当前生效的后端在应用内「关于与许可」页末尾标明。

```powershell
# 前置：Rust 工具链（https://rustup.rs；Windows 需 MSVC 生成工具）
.\.venv\Scripts\python.exe -m pip install maturin
cd vtcore
..\.venv\Scripts\python.exe -m maturin develop --release
```

产物为 CPython 3.12+ 通用的 abi3 扩展，因此在同一份源码上换 Python 小版本无需重编。接口清单与测试方式见 `vtcore/README.md`，字节级规范见 `docs/voice-batch-m2-spec.md`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py app tools tests
$tests = Get-ChildItem tests -Filter "test_*.py" | Sort-Object Name
foreach ($test in $tests) {
  .\.venv\Scripts\python.exe -m unittest ("tests." + $test.BaseName) -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

## 构建与大文件

仓库通过 Git LFS 管理 `app/resources/ffmpeg/bin/` 中的 ffmpeg、ffprobe 与共享 DLL。克隆源码前请先安装 Git LFS；克隆后运行 `git lfs pull` 获取这些二进制资源。

正式发布优先提供完整 onedir ZIP。`build/`、`dist/`、`release/`、虚拟环境、日志、用户音频和测试输出不会加入普通源码提交。

FFmpeg 构建版本、源码披露、许可和第三方声明见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md)、[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) 与 [`licenses/`](licenses/)。

## 已知限制

- 若构建 Windows 可执行包，当前仅面向 x64。
- 打包构建中 onefile 首次启动需要释放 Qt 与 FFmpeg 资源，通常比 onedir 慢，也更容易被安全软件进行额外扫描。
- 名称库生成需要用户自行提供合法的参考目录；仓库不包含游戏官方资源或原始音频。
- 不同游戏版本可能改变 Bank 或语音文件命名，使用前请备份目标文件。

## 免责声明、许可与反馈

使用前请阅读 [`PROJECT_USAGE_NOTICE.md`](PROJECT_USAGE_NOTICE.md)。原始代码适用 [`LICENSE`](LICENSE)，本修改版的修改与新增代码按 GPL-3.0-only 授权，第三方组件继续遵循各自许可证。

发现 Bug 时请在 GitHub Issues 中提供：软件版本、复现步骤、预期行为、实际行为和必要的本地日志片段。提交日志前请先移除个人目录、语音素材名称及其他隐私信息；不要上传游戏官方资源、用户音频、密码或 Token。

---

本工具 fork 自 [Beiku](https://github.com/beikuwawa) 的原项目 [WT-NameRelay](https://github.com/beikuwawa/WT-NameRelay)（beta 0.2.0）

本版（WT-Tool-Experimental Version）维护者：Diderde（GitHub：[@Diderde](https://github.com/Diderde)）
