# WT-NameRelay by Beiku（beta 0.2.0）

战争雷霆语音包文件名称补全、复制与语音处理工具。车组、无线电与 Bank 模块支持手动导入和目录自动检索；语音处理模块提供波形时间轴、非破坏性裁切、试听和 FFmpeg 导出。

本项目是非官方第三方工具，不包含、不提供也不分发任何游戏官方资源或官方音频，与 Gaijin Entertainment、War Thunder 及其关联主体不存在授权、赞助或合作关系。

> 项目原创部分采用自定义 source-available 许可，不是 OSI 定义的开源软件。允许个人非商业使用与同许可源码分享；禁止未经许可的商业使用、二次售卖、付费分发和捆绑收费。详见 [`LICENSE`](LICENSE) 与 [`PROJECT_USAGE_NOTICE.md`](PROJECT_USAGE_NOTICE.md)。

## 环境与启动

项目验证环境：Windows、Python 3.11.5、PySide6 6.7.3、Qt 6.7.3、PyQtGraph 0.13.7、NumPy 1.26.4。

```powershell
cd "<项目目录>"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

在 VS Code 中打开项目后，选择 `.venv\Scripts\python.exe` 作为解释器，并以 `main.py` 作为启动入口。

正式 Windows EXE 不放入源码提交。请从 GitHub Releases 下载标有 `beta 0.2.0` 的 Windows x64 ZIP，并使用同页提供的 SHA-256 文件校验下载内容。

## 车组手动复制流程

1. 进入“车组文件复制”，拖入文件或点击“选择文件”。可一次导入多个文件；文件夹会被忽略。
2. 程序仅移除最后一个扩展名，并在内置名称库中区分大小写精确匹配。未知名称和无扩展名文件保留在左侧，不参与补全。
3. 右侧显示同组剩余目标名称。可逐项勾选、全选或全部取消；同组多个来源会自动随机且均衡分配，无需手动选择来源。
4. 点击“开始复制”。若目标已存在，统一选择跳过、覆盖或取消本批任务。
5. 文件以二进制形式复制到被分配来源文件的同级目录，沿用该来源文件的扩展名；源文件不会被修改或移动。

同组导入多个来源时，已导入名称不会再次生成，剩余目标会自动随机且尽量均衡地分配给这些来源。执行开始后分配关系固定。

车组页采用整体纵向滚动布局：手动复制和自动复制区域各自保留独立的状态、进度条和任务栏。

## 车组自动检索与补全

1. 在“自动检索与补全”区域选择或粘贴目标目录，按需勾选“包含子目录”。默认只扫描当前目录；递归扫描时每个目录独立分析和输出。
2. 点击“开始识别”。程序只读取受支持音频文件的名称与扩展名，并与内置名称库精确匹配。
3. 右侧仅显示已经出现但不完整的名称组：红色为已存在文件，白色复选项为待补全文件。可搜索、按组全选/取消或全局全选/取消。
4. 多个同组来源会自动随机且均衡分配；“重新分配来源”只重新随机分配，不允许手动指定来源。
5. 点击“开始自动复制”后，文件在后台补全到对应目录。自动模式永不覆盖已有文件；扫描后出现的目标会自动跳过。

支持的扩展名为 `.wav`、`.flac`、`.ogg`、`.mp3`、`.m4a`、`.aac` 和 `.opus`，扩展名匹配不区分大小写。

## 名称库生成

运行时不读取 Excel。名称库由一次性脚本从 `Sheet1!A3:A643` 提取并嵌入 Qt 资源：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools\extract_crew_names.py --input "<名称库 Excel 路径>"
.\.venv\Scripts\pyside6-rcc.exe app\resources\resources.qrc -o app\resources\resources_rc.py
```

默认提取结果会校验 511 个有效名称、151 个名称组；`A644` 及后续行不会读取。

## 无线电名称库生成

无线电名称库只在生成时读取下列工程目录的当前层文件；应用日常运行不会访问它们。脚本会生成正式 JSON 和审计报告，并拒绝把高度、单位、方位角或孤立名称作为可补齐变体。

```powershell
.\.venv\Scripts\python.exe tools\build_radio_name_groups.py `
  --voice1 "<无线电 voice1 参考目录>" `
  --additional-01 "<无线电 additional_01 参考目录>" `
  --english "<无线电 english 参考目录>"
.\.venv\Scripts\pyside6-rcc.exe app\resources\resources.qrc -o app\resources\resources_rc.py
```

当前无线电库包含 56 个确认分组、480 个完整名称；其中二维矩阵名称（例如 `..._A_0_1` 至 `..._A_3_3`）作为一个完整组处理。审计结果写入 `reports/radio_name_analysis.json`。JSON 与公开审计报告只保存外部来源标识，不记录开发机绝对路径。

## Bank 名称库与复制规则

Bank 模块将 `.assets.bank` 与普通 `.bank` 作为不同角色。只有同一目录、同一类别（`common` 或 `ground`）、同一国家的两个角色同时存在，才能成为复制来源；一个目标国家的两个角色始终来自同一个来源国家组。

```powershell
.\.venv\Scripts\python.exe tools\build_bank_name_groups.py `
  --sound "<War Thunder sound 参考目录>"
.\.venv\Scripts\pyside6-rcc.exe app\resources\resources.qrc -o app\resources\resources_rc.py
```

当前 Bank 库包含 52 个完整国家组：common 17 组、ground 35 组。完整审计写入 `reports/bank_name_analysis.json`。自动检索永不覆盖文件；手动复制会统一询问跳过、覆盖或取消。

## 语音处理时间轴

语音处理页使用 PyQtGraph 图形视图显示真实波形。时间轴模型以整数毫秒保存裁切范围，试听与正式导出都从同一个不可变 `TimelineSnapshot` 生成，因此片段顺序、裁切范围和空白时长保持一致。

- 左右手柄进行非破坏性裁切，中央区域用于选择与排序。
- 时间尺根据可视范围自动显示秒或毫秒，最大缩放为 1000 px/s（1 px/ms）。
- `Ctrl + 鼠标滚轮` 缩放，`Shift + 鼠标滚轮` 水平滚动；缩放保持可视区左侧时间不变。
- 音频探测、波形解析、试听缓存和正式导出均在后台执行。
- 第三方组件及许可全文见 `THIRD_PARTY_LICENSES.md` 与 `licenses/`。

## 测试

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py app tools tests
$tests = Get-ChildItem tests -Filter "test_*.py" | Sort-Object Name
foreach ($test in $tests) {
  .\.venv\Scripts\python.exe -m unittest ("tests." + $test.BaseName) -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

自动化测试仅在临时目录创建测试字节文件，不会操作用户的音频素材。按模块分别启动测试进程，可以避免 QtMultimedia 全局状态在同一进程中跨测试模块残留。

## 当前范围

- 已实现：车组、无线电、Bank 的手动导入与自动检索、精确识别、分组确认、均衡随机分配、后台复制、统一冲突处理、取消、进度与结果展示。
- 复制任务暂不提供暂停；Windows 发布流程已提供调试 onedir、正式 onedir 和正式 onefile 构建。

## 构建与大文件

仓库通过 Git LFS 管理 `app/resources/ffmpeg/bin/` 中的 FFmpeg、ffprobe、ffplay 和共享 DLL。克隆源码前请先安装 Git LFS；克隆后运行 `git lfs pull` 获取这些二进制资源。

正式发布优先提供完整 onedir ZIP。`build/`、`dist/`、`release/`、虚拟环境、日志、用户音频和测试输出不会加入普通源码提交。

FFmpeg 构建版本、源码披露、许可和第三方声明见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md)、[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) 与 [`licenses/`](licenses/)。

## 界面预览

项目截图将在 GitHub 仓库与 Release 说明中维护；源码仓库不提交包含个人目录、测试音频或调试状态的临时截图。

## 已知限制

- 当前正式构建面向 Windows x64。
- onefile 首次启动需要释放 Qt 与 FFmpeg 资源，通常比 onedir 慢，也更容易被安全软件进行额外扫描。
- 名称库生成需要用户自行提供合法的参考目录；仓库不包含游戏官方资源或原始音频。
- 不同游戏版本可能改变 Bank 或语音文件命名，使用前请备份目标文件。

## 免责声明、许可与反馈

使用前请阅读 [`PROJECT_USAGE_NOTICE.md`](PROJECT_USAGE_NOTICE.md)。项目原创部分适用 [`LICENSE`](LICENSE)，第三方组件继续遵循各自许可证。

发现 Bug 时请在 GitHub Issues 中提供：软件版本、复现步骤、预期行为、实际行为和必要的本地日志片段。提交日志前请先移除个人目录、语音素材名称及其他隐私信息；不要上传游戏官方资源、用户音频、密码或 Token。

作者：Beiku
