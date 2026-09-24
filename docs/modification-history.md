# WT-Tool-Experimental Version 逐轮变更登记

本文件是 `MODIFICATION_NOTICE.md` 的**续篇**：声明（许可分层、完整文件清单、
运行行为差异、其他声明）在 `MODIFICATION_NOTICE.md`，此处收录逐轮开发登记。

拆分原因：声明会被 `app/resources/resources.qrc` 内嵌并在程序「关于与许可」中展示，
而逐轮登记已达 100 KB 量级；两者受众不同（前者面向使用者与合规审查，后者面向维护者），
混在一起会让对话框不可读、二进制无谓增大。**两份文件都随源码分发**，合规记录不缺失。

---

## 追加变更登记（2026-09-21 会话）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

### 新增文件

- 无。（语言切换运行时机制位于既有文件 `app/i18n.py` 内，未新增文件。）

> **术语说明**：本节与以下各轮登记里的"既有文件 / 原有文件"是**相对该轮之前**而言的，
> 不等于"上游 beta 0.2.0 已有"。例如 `app/i18n.py` 由**本 fork 创建**（见文首「新增文件」清单），
> 只是在其出现之后的轮次里已成为既有文件。判断某文件究竟属上游原有还是本 fork 新增，
> 一律以文首三段机器比对清单为准。

### 修改过的原有文件

- `app/i18n.py`：新增界面语言运行时机制（`i18n_text` / `mark` / `refresh` / `retrans`）
  与中英文案表（四功能页 242 条已接入；共享控件 105 条已备译文，接入留待后续）。
- `app/pages/bank_page.py`、`app/pages/radio_page.py`、`app/pages/crew_page.py`、
  `app/pages/audio_processing_page.py`：正文静态文案全部改由 `i18n_text()` 输出，
  并新增 `retranslate()` 以响应语言切换（含子控件级联重译）。
- `app/audio/waveform_service.py`：共享类状态（锁、缓存、命中计数）显式标注 `ClassVar`。
- `app/` 其余约 45 个文件、`tests/` 下 8 个文件：ruff 静态修复（导入排序、未用导入清理、
  闭包绑定循环变量、未用解包、集合字面量改元组、`subprocess.run` 显式 `check=False`）。
  上述修复不改变运行语义。
- `app/widgets/` 下的 8 个共享控件（文件拖放区、目录选择器、任务状态面板、自动扫描结果面板、补全组控件、车组/无线电确认组、来源文件列表）已接入语言切换：静态文案在构造点登记，运行时文案走不登记通道 `i18n_live()`，各控件提供 `retranslate()` 供页面级联调用；共 105 条控件文案并入翻译表。
- 同日修订：四功能页 `retranslate()` 补充 `super().retranslate()` 调用，使基础框架文案
  （返回主界面 / 工作区眉题 / 页面标题 / 占位提示）随语言切换；修正 Bank 页动作栏按钮
  与译文的对应顺序。

### 未纳入本次改动的已知遗留

- 少量由数据驱动的动态文案依赖页面重渲染刷新（已在各页 `retranslate()` 中接主要渲染入口）。

## 追加变更登记（2026-09-21 玻璃主题）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

### 新增文件

- `app/widgets/water_backdrop.py` —— 全局水纹流动背板：首选 GLSL 域扭曲 fBm 着色器
  （QOpenGLWidget），GL 不可用时自动降级为 QPainter 缓动光斑；附"减弱动效"偏好 `ui/motion`。

### 修改过的原有文件

- `app/styles/theme.py` —— 双主题新增水纹与玻璃色板（`water_*` / `card_glass` / `panel_glass` /
  `glass_border`）；`appRoot` / `animatedStack` / `pageRoot` 容器透明化；功能卡片与主要面板
  改为半透明玻璃底。
- `app/main_window.py` —— 以 `QStackedLayout`（StackAll）将水纹背板常驻叠放于页面栈之下。
- `app/pages/home_page.py` —— 头部新增"动效：开/关"切换按钮（接入 `ui/motion` 偏好）。
- `app/i18n.py` —— 新增动效开关中英文案。
- `tests/test_release_features.py` —— 主题像素采样回归改采 `fileDropArea` 不透明实体面
  （`appRoot` 已按设计透明化，窗口底色由水纹背板承载）。

### 本轮已知边界

- 卡片玻璃质感为半透明实现；Qt 无控件级背景模糊等价物，真·毛玻璃背板（DWM Acrylic/Mica）
  留作 Windows 11 可选实验，未包含在本轮。

## 追加变更登记（2026-09-21 语言随动修复）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

### 新增文件

- 无。

### 修改过的原有文件

- `app/pages/crew_page.py` —— 确认区空态标签改用免登记通道 `i18n_live()` 生成
  （原 `ui.109` 标记在语言切换重译时泄漏裸 `{0}` 占位符）；确认区清理循环改为
  先 `hide()` 再 `deleteLater()`，消除延迟销毁期间新旧文案叠印。
- `app/pages/radio_page.py`、`app/pages/bank_page.py` —— 同款确认区/分组清理循环加固
  （`hide()` 后再延迟销毁）。

### 本轮已知边界

- 少量由任务运行期驱动的动态文案（如进度条格式串）仍按既有策略在下次任务事件时刷新。

### 追加登记（2026-09-21 · M1 语音批量生成 W0–W5）

新增文件：
- `docs/voice-batch-spec.md`（行模型/身份三分离/spec_hash 规范字节/.vt.state schema/WT_DEFAULT 规则）
- `docs/tts-spike-report.md`（GPT-SoVITS api_v2 契约与 CosyVoice GGUF 外部 runner 结论）
- `app/models/voice_table.py`（VoiceTable/VoiceRow、双轴状态、规范字节；标注待 vtcore 替换）
- `app/services/tts_runner.py`（串行队列 + HTTP 后端 + 假后端 + 子进程托管；本地服务绕过系统代理）
- `app/services/voice_filename_validator.py`（ValidatorProfile + WT_DEFAULT）
- `app/services/save_coordinator.py`（JSON 内部工程文件 + .vt.state 旁车 + 三入口自动保存）
- `app/widgets/voice_table_model.py`（表格模型与行委托：状态徽章 + 试听/重新生成）
- `app/pages/tts_model_page.py`、`app/pages/voice_batch_page.py`（二级模型选择页 / 三级工作台）
- `tools/run_gate.ps1`（可移植全量门禁：逐模块独立进程 + 超时）
- 测试：`tests/test_voice_table.py`、`tests/test_tts_runner.py`、`tests/test_voice_filename_validator.py`、
  `tests/test_voice_batch.py`、`tests/test_voice_save.py`

修改过的原有文件：
- `app/pages/home_page.py`（一级主页新增第三卡）、`app/pages/__init__.py`、`app/main_window.py`（三级路由与后端装配）
- `app/i18n.py`（新增 45 条界面文案，中英对照）
- `README.md`、`MODIFICATION_NOTICE.md`、`docs/tts-spike-report.md`：统一使用官方称呼 GPT-SoVITS（禁用缩写）
- `gsv_weights_list.txt` → `gpt_sovits_weights_list.txt`（更名并同步引用）
- `download_tts_verify.bat`：内容改名并**由 UTF-8 纠正为 GBK + CRLF**、移除 `chcp` 行（合规修复）
- `start.bat`：同步新权重清单名与官方称呼（保持 GBK + CRLF，无 chcp）
- `app/resources/resources_rc.py`：随 README/声明变更重编译并规范 CRLF

冻结约定（M1 不做，后置 M2）：签名/只读锁/TOFU/`.vt` 二进制容器/manifest 验证；
`key_id` 在 M1 恒为空串但保留于规范字节中，便于 M2 无痛升级。

### 追加登记（2026-09-21 · CosyVoice3 推理器与本地服务 B 方案）

新增文件：
- `tools/cosyvoice3_shim.py` —— CosyVoice3 本地推理服务（CrispASR 绑定 → HTTP 契约：
  `GET /health`、`POST /synthesize`、`/v1/audio/speech`；`--fake` 联调引擎与 `--selftest` 自检）
- `app/services/voice_service_launcher.py` —— 服务装配（资产判断/命令组装/子进程托管/复用已有服务）
- `tests/test_cosyvoice_shim.py` —— 8 用例（契约往返 / 400 映射 / OpenAI 风格端点 / 自检 / 装配）

修改过的原有文件：
- `start.bat` —— 新增 CosyVoice3 推理器（CrispASR 官方 Release wheel）检查与下载，
  并新增 `/only-runner` 开关（官方地址：github.com/CrispStrobe/CrispASR，MIT）
- `app/main_window.py` —— CosyVoice 分支优先拉起本地服务（失败回落演示后端），关闭时停止托管进程
- `tools/run_gate.ps1` —— 纳入接口与 shim 测试模块

说明：`TTS model\`（权重与推理器）为本地资产且已 gitignore，不入库；
CrispASR 为 MIT，CosyVoice3 权重为 Apache-2.0。

### 追加登记（2026-09-21 · 门禁收尾与 spike 报告回填）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- 无。

修改过的原有文件：

- `tests/test_audio_processing.py` —— 页面/卡片结构断言随 W3 同步（`stack.count()` 6 → 8、
  主页卡片 2 → 3），测试更名为 `test_home_has_audio_route_and_full_page_stack`。
  先前 `d56f641` 只同步了 `test_ui_smoke.py`，本模块漏改，导致全量门禁单模块红。
- `tools/run_gate.ps1` —— 模块清单补齐 `cosyvoice_shim`（18 → 19 模块），与沙箱门禁
  `temp/ps_gate.ps1` 对齐；上一节"纳入接口与 shim 测试模块"的记载至此与实际一致。
- `docs/tts-spike-report.md` —— 新增 §六（CosyVoice3 官方推理器定为 CrispASR、Windows 官方件
  仅含 DLL 与绑定、B 方案落地物清单、localhost 需绕系统代理），§一/§三/§四/§五 中
  "runner 待定 / M1 不捆绑 runner"的口径改为指向 §六。
- `.gitignore` —— 忽略门禁产物 `tools/gate-results.txt`（运行门禁不再弄脏工作区）。

验收（2026-09-21 17:04）：`tools/run_gate.ps1` **19 模块 / 222 用例全绿**（逐模块独立进程；
其中 2 例为按设计跳过的真实推理测试）；ruff 0 项；`compileall` 通过；上述改动文件行尾保持 CRLF。

### 追加登记（2026-09-21 · M2 规范冻结（W0））

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `docs/voice-batch-m2-spec.md` —— M2 字节级规范：`.vt` 二进制容器布局（`VTBL` 头 + chunk TLV +
  `VTBE` 尾部与双层完整性校验）、chunk 类型登记表与未知 chunk 前向兼容规则、
  签名算法编号表（`none` 禁止 / Ed25519 唯一实现 / PQC 预留 / RSA 不做）、签名消息规范字节、
  TOFU 信任库 schema、项目私钥 AEAD 存储格式（主包装钥走系统凭据库）、只读锁语义、
  `.vtmanifest` 整包验证、M1 JSON 工程一次性导入、冻结项与未决项。

修改过的原有文件：

- `docs/voice-batch-spec.md` —— §7 冻结项末尾指向 `docs/voice-batch-m2-spec.md`（M2 规范落点）。

说明：本次为**规范冻结候选**（W0），不含可执行实现；`docs/voice-batch-m2-spec.md` §12 列出四项
待拍板事项（Rust 工具链安装、vtcore 载体形态、`key_id` 是否参与 `spec_hash`、TOFU 首见默认行为）。

### 追加登记（2026-09-21 · M2-W1 前置：共享黄金向量与编码修复）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `tests/fixtures/voice_table_golden.json` —— M1 规范字节黄金向量（11 条：最小行 / 全可选字段 /
  默认值省略 / 空文本 / 多字节与 emoji / `extra` 键名排序 / `key_id` 非空 / 单行表 / 乱序多行表 /
  空表 / 表级 `key_id` 非空），同时作为 **M2 vtcore 的字节兼容基准**（两侧读同一份）。
- `tools/gen_voice_table_golden.py` —— 向量生成与校验脚本；`--check` 模式不写盘，
  仅校验磁盘向量与当前实现一致。

修改过的原有文件：

- `app/models/voice_table.py` —— 规范记录编码修复：**键名改为按 UTF-8 编码**
  （此前按 ASCII 编码，遇到非 ASCII 的 `extra` 键会抛 `UnicodeEncodeError`）；
  依据 `docs/voice-batch-spec.md` §4.1「字符编码 UTF-8」与 §4.1.3「按 UTF-8 字节序」，
  键名本就允许非 ASCII。ASCII 键名的编码结果逐字节不变，M1 黄金向量不受影响。
  该缺陷由新增向量 `row_extra_byte_order` 当场抓出。
- `tests/test_voice_table.py` —— 新增 `GoldenFixtureTests`（3 例）：逐条复现向量文件的
  `canonical_hex` 与 `sha256`，并断言向量文件中两条 M1 手写黄金未被改写（防"实现漂移后
  重新生成"把基准改坏）。

验收（2026-09-21 19:00）：`tools/run_gate.ps1` **19 模块全绿**（`voice_table` 由 20 → **23 用例**）；
ruff 0 项；`compileall` 通过；改动文件行尾保持 CRLF。

### 追加登记（2026-09-21 · M2-W1：vtcore（Rust/PyO3）字节兼容实现）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `vtcore/Cargo.toml`、`vtcore/Cargo.lock`、`vtcore/pyproject.toml` —— Rust crate 与 maturin 构建配置
  （PyO3 0.29 + `abi3-py312` 生成 abi3 wheel；`publish = false`；release 开 LTO）。
- `vtcore/src/canonical.rs` —— M1 §4 规范字节的**权威实现**（纯 Rust，不依赖 pyo3）：
  记录编码、键名 UTF-8 字节序排序、行/表规范字节、行内字段缺省规则。
- `vtcore/src/lib.rs` —— PyO3 薄胶水：`canonical_row_bytes` / `canonical_table_bytes` /
  `spec_hash_row` / `spec_hash_table` / `spec_hash_bytes` / `version`；对 `row_hash` 形状与
  `spec_version` 做输入校验（非法即 `ValueError`）。
- `vtcore/tests/golden.rs` —— Rust 侧黄金向量测试（4 例，与 Python 侧读同一份 fixtures）。
- `vtcore/README.md` —— 构建方式、接口清单与测试方式。
- `tests/test_vtcore.py` —— Python 侧契约测试（7 例）：全部黄金向量与 `tests/fixtures/` 、
  Python 参考实现三方逐字节一致；`hashlib` 对照；非 ASCII `extra` 键回归；非法输入拒绝；
  扩展未构建时整模块跳过。

修改过的原有文件：

- `tools/run_gate.ps1`、`temp/ps_gate.ps1` —— 门禁模块清单纳入 `vtcore`（19 → **20 模块**）。
- `requirements-dev.txt` —— 新增 `maturin==1.15.0`（构建 vtcore 用）。
- `.gitignore` —— 忽略 `vtcore/target/`、`*.pyd`、`*.so`。

环境（本机一次性，不入库）：Rust **1.98.1**（rustup，`x86_64-pc-windows-msvc` 目标，
经清华镜像安装；本机 VS 2022 Build Tools + Windows SDK 10.0.26100 已具备链接环境）。

验收（2026-09-21 19:13）：`tools/run_gate.ps1` **20 模块全绿**；vtcore 侧 Python 7 例 + Rust 4 例
全部通过，与 M1 黄金向量逐字节一致；ruff 0 项；`compileall` 通过；新增文件行尾 CRLF 合规。

### 追加登记（2026-09-21 · M2-W2：Ed25519 签名层）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `vtcore/src/sign.rs` —— 签名层：算法编号表（`0x0000 none` 禁止 / `0x0001` Ed25519 唯一 /
  未知编号拒绝，不降级）、`key_id = SHA-256(公钥)`、签名消息规范字节（`sig` 域分隔 + 记录式，§5.3）、
  Ed25519 签名与验签、7 类稳定失败码。
- `vtcore/src/hex.rs` —— 十六进制编解码（文本层统一小写）。
- `vtcore/tests/sign.rs` —— 签名测试 6 例：**RFC 8032 §7.1 官方 Ed25519 测试向量**
  （公钥推导 / 签名 / 验签，避免"实现与自生成基准互相印证"）、签名消息布局、
  算法编号强制、篡改载荷 / 换对象类型 / 换公钥 / 错 `key_id` 四类拒绝。

修改过的原有文件：

- `vtcore/src/lib.rs` —— 新增 pyo3 导出：`generate_keypair` / `public_key_from_seed` /
  `key_id_from_public_key` / `algorithm_name` / `signing_message_hex` / `sign_object` /
  `verify_object`，以及常量 `ALG_NONE` / `ALG_ED25519` / `SIG_VERSION`；
  十六进制实现收敛到 `hex` 模块（去重复）。
- `vtcore/Cargo.toml` —— 新增依赖 `ed25519-dalek 3.0`（`rand_core` 特性）与 `getrandom 0.4`
  （系统随机源，用于密钥生成）。
- `vtcore/README.md` —— 补充签名接口清单，并写明"被签对象是逻辑规范字节（表级规范字节 /
  manifest 规范字节），重新打包容器不破坏签名"。
- `tests/test_vtcore.py` —— 新增 `VtcoreSignatureTests`（9 例）：RFC 8032 公钥向量、
  `key_id` 与 `hashlib` 对照、签名往返、`signed_at` 语义（0 = 取当前时间）、篡改 / 换对象 /
  换公钥 / 错 `key_id` 拒绝、算法编号强制、签名消息布局。

验收（2026-09-21 19:18）：`tools/run_gate.ps1` **20 模块全绿**（`vtcore` 由 7 → **16 用例**）；
Rust 侧 `cargo test` **10 例全通过**（4 黄金向量 + 6 签名）；ruff 0 项；`compileall` 通过；
改动文件行尾 CRLF 合规。

说明：签名者身份（`key_id`）走签名消息与签名块，**不写入** `spec_hash`（`voice-batch-m2-spec.md`
§4.4 的推荐方案），因此"签名"动作不会让已有产物变为 `stale`；该取舍仍属该规范 §12 未决项 c，
若改为"写入"只需调用方传参，不需要改动字节格式。

### 追加登记（2026-09-21 · `vtcore/Cargo.lock` 行尾例外）

修改过的原有文件：

- `.gitattributes` —— 新增 `vtcore/Cargo.lock text eol=lf`：该文件由 **cargo 自身生成并在依赖变更时
  重写**（始终以 LF 落盘），强制 CRLF 只会持续产生审计噪声；故按仓库"例外需登记"的既有做法
  （与 `app/resources/ffmpeg/bin/` 的 LFS 例外并列）明确登记为**唯一文本行尾例外**。

行尾审计口径随之更新为：除 `vtcore/Cargo.lock`（`attr/text eol=lf`）外，文本文件一律 `w/crlf`。

### 追加登记（2026-09-21 · M2-W3：`.vt` 二进制容器）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `vtcore/src/container.rs` —— 容器读写：`VTBL` 头（16B）+ chunk TLV（类型 / 标记 / 长度 / payload /
  `SHA-256(payload)`，开销 42B）+ `VTBE` 尾部（36B，整文件哈希，只覆盖尾部 magic 之前的字节）；
  未知**非关键** chunk 原样保留、未知**关键** chunk 直接拒绝；自洽校验 `row_count` 与
  `TABH.spec_hash`（由行数据重算）；16 类稳定错误码。
- `vtcore/tests/container.rs` —— 容器测试 14 例：往返字节稳定、头部布局（`reserved=0`、尾部哈希
  覆盖范围）、字节级篡改（**文件层 / chunk 层**，后者即使重算整文件哈希仍被 chunk 哈希抓住）、
  截断与 magic/版本错误、未知 chunk 两种策略、缺必需 chunk、表哈希不符、`row_count` 不符、
  重复 `row_id`、签名往返与内容绑定、声明已签名但缺 `SIGN`。
  其中多条用例用**手工拼装的容器**（不经过本实现编码器）构造，用以独立验证格式理解本身。

修改过的原有文件：

- `vtcore/src/canonical.rs` —— 新增严格记录解析器 `parse_records` / `find_record`
  （长度前缀无前导零、值与长度严格相符、必须带尾随 `LF`），供容器读取 `META` / `ROWS` / `TABH`。
- `vtcore/src/lib.rs` —— 新增 pyo3 导出 `encode_container` / `parse_container` /
  `verify_container_signature` / `row_id_of_row_bytes` 与容器常量；签名块字典读写抽成共用助手。
- `vtcore/README.md` —— 补充容器接口、文档字典形状与"双层完整性"说明。
- `docs/voice-batch-m2-spec.md` —— 新增 §2.4 容器错误码表（`vt_*`），并确立"容器层 `vt_` /
  签名算法层 `sig_`"两层错误码命名约定。
- `tests/test_vtcore.py` —— 新增 `VtcoreContainerTests`（9 例）：往返与字节稳定、表哈希与参考实现
  一致、文件级篡改与截断、未知 chunk 两种策略、chunk 类型长度校验、重复 `row_id`、
  签名容器往返与内容绑定、未签名文件报 `vt_signature_missing`。

**过程中修掉的真实缺陷**：编码器最初把尾部 magic 也算进整文件哈希（规范要求只覆盖
「文件起始 → 尾部 magic 之前」），导致自产容器无法被自己读回；由容器测试当场抓出并修正。

验收（2026-09-21 19:25）：`tools/run_gate.ps1` **20 模块全绿**（`vtcore` 由 16 → **25 用例**）；
Rust 侧 `cargo test` **24 例全通过**（黄金向量 4 + 签名 6 + 容器 14）；ruff 0 项；`compileall` 通过；
改动文件行尾 CRLF 合规。

### 追加登记（2026-09-21 · M2-W4：TOFU 信任库与密钥存储）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `vtcore/src/keystore.rs` —— 项目私钥的 AEAD 封装：`VTKY` 头（magic / version / aead）+
  24 字节随机 nonce + 密文（32 字节 seed）+ 16 字节认证标签；**AAD = key_id 的 ASCII hex**；
  8 类稳定错误码（`key_bad_magic` / `key_unsupported_version` / `key_unsupported_aead` /
  `key_bad_length` / `key_bad_key_id` / `key_decrypt_failed` / `key_randomness`）。
- `vtcore/tests/keystore.rs` —— 封装测试 7 例：往返、**每次封装 nonce 随机**（同明文两次密文不同）、
  换主包装钥 / 换 `key_id`（AAD）/ 篡改任意字节均失败、格式类错误码。
- `app/services/vt_trust_store.py` —— TOFU 信任库（规范 §6）：缺失或损坏一律按空库处理；
  首见**不自动信任**；`trust` / `revoke` / `forget` 人工动作；`tables` 记录每张表已确认的签名者，
  用于检测"同表换签名者且无轮换记录"（`key_rotated_unknown`，且确认前不更新该字段，告警持续）；
  轮换记录；原子写盘。
- `app/services/vt_key_store.py` —— 项目密钥存储（规范 §7）：主包装钥经 **Windows DPAPI（用户范围）**
  保护后落盘，保护层留 `MasterKeyProtector` 抽象（将来可接 Keychain / Secret Service）；
  项目私钥经主包装钥 AEAD 封装落盘 `vt_keys/<key_id>.vtkey`；错误消息**不含**密钥材料。
- `tests/test_vt_trust.py`、`tests/test_vt_key_store.py` —— 26 例：含**真实 DPAPI 往返**、
  `key_id` 绑定（改名即解密失败）、篡改检测、换主包装钥失败、"错误消息不泄漏种子"。

修改过的原有文件：

- `vtcore/src/lib.rs` —— 新增 pyo3 导出 `wrap_project_key` / `unwrap_project_key` 与常量
  `KEY_BLOB_MAGIC` / `KEY_BLOB_VERSION` / `KEY_BLOB_LEN` / `AEAD_XCHACHA20_POLY1305`。
- `vtcore/Cargo.toml` —— 新增依赖 `chacha20poly1305`。
- `docs/voice-batch-m2-spec.md` —— §6 信任库 schema 补 `tables` 字段与"确认前不改写"规则、
  字段名统一为 `public_key`；§7 明确主包装钥的 DPAPI 文件实现与抽象接口。
- `tools/run_gate.ps1`、`temp/ps_gate.ps1` —— 门禁纳入 `vt_trust`、`vt_key_store`（20 → **22 模块**）。
- `vtcore/README.md` —— 补充密钥封装接口。

验收（2026-09-21 19:31）：`tools/run_gate.ps1` **22 模块全绿**（`vtcore` 25 例 + `vt_trust` 16 例 +
`vt_key_store` 10 例）；Rust 侧 `cargo test` **31 例全通过**（黄金向量 4 + 签名 6 + 容器 14 + 密钥 7）；
ruff 0 项；`compileall` 通过；改动文件行尾 CRLF 合规。

### 追加登记（2026-09-21 · M2-W5：只读锁、manifest 整包验证、JSON 迁移与 Python 侧接入）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `vtcore/src/manifest.rs` —— `.vtmanifest` 规范字节（§9）：`manifest` 域分隔 + 记录式；
  `file` 记录按路径升序、`file_count` 与条数自校验；路径必须是**相对 POSIX** 且不含 `|` 与换行；
  4 类稳定错误码；另提供 `hash_bytes`（与表/行哈希同一实现）。
- `vtcore/tests/manifest.rs` —— manifest 测试 6 例：布局与排序、**输入顺序不影响字节**、空包、
  路径 / 哈希 / 重复路径拒绝、SHA-256 已知值对照、清单签名往返（含"表签名不得被当作清单签名"）。
- `app/services/vt_project.py` —— `.vt` 读写与**只读锁**（§8）：只读属性 + 应用层写守卫
  （`vt_locked`）、已签名默认上锁、解锁是显式动作；**M1 JSON 一次性导入**（§10，原 JSON 不删不改、
  导入失败不落盘）。
- `app/services/vt_manifest.py` —— 整包验证（§9）：目录形态、条目收集、构建 / 写盘 / 读取、
  四类结果（`ok` / `missing` / `extra` / `modified`）与签名校验结果（`sig_*`）。
- `tests/test_vt_project.py`、`tests/test_vt_manifest.py` —— 21 例：含锁定拒写与显式解锁、
  签名容器往返、导入保原文件、导入签名后自动上锁、`extra` 字段经 vtcore 正确编码、
  四类验证结果与"仅多出文件不算失败"、篡改清单导致验签失败。

修改过的原有文件：

- `app/models/voice_table.py` —— **规范字节接入 vtcore**（§4）：`row_canonical_bytes()` 与
  `VoiceTable.canonical_bytes()` 优先调用 vtcore，扩展未构建时回退参考实现；
  新增 `HASH_BACKEND` 标注当前后端；纯 Python 编解码保留为参考实现（测试交叉验证用）。
- `vtcore/src/lib.rs` —— 新增 pyo3 导出 `manifest_canonical_bytes` / `hash_bytes` 与 `MANIFEST_VERSION`。
- `tools/run_gate.ps1`、`temp/ps_gate.ps1` —— 门禁纳入 `vt_project`、`vt_manifest`（22 → **24 模块**）。
- `vtcore/README.md` —— 补充 manifest 接口与 M2 完成说明。

验收（2026-09-21 19:38）：`tools/run_gate.ps1` **24 模块全绿**（`vtcore` 25 + `vt_trust` 13 +
`vt_key_store` 13 + `vt_project` 10 + `vt_manifest` 11 例）；Rust 侧 `cargo test` **37 例全通过**
（黄金向量 4 + 签名 6 + 容器 14 + 密钥 7 + manifest 6）；ruff 0 项；`compileall` 通过；CRLF 合规。

## M2 收官状态（2026-09-21）

对照 `HANDOFF-M1.md` §四「冻结决策」的六项，逐项落地情况：

| 冻结决策 | 落地 | 证据 |
| --- | --- | --- |
| 1. 签名最小集（Ed25519 + 算法编号表，禁 `none`，RSA 不做，ML-DSA 预留） | `vtcore/src/sign.rs` | RFC 8032 §7.1 官方向量；算法编号强制用例 |
| 2. `.vt` 二进制容器（`VTBL` + chunk TLV + 固定小端） | `vtcore/src/container.rs` | 往返字节稳定、双层完整性、未知 chunk 策略等 14 例 |
| 3. 身份三分离（table_id / key_id / row_id） | M1 已定；M2 只把 `key_id` 用于签名层 | 见 `m2-spec` §4.4 与其未决项 c |
| 4. `spec_hash` 由 vtcore 单点计算 | `app/models/voice_table.py` 接入 + 黄金向量共用 | Python/Rust 两侧读同一份 `tests/fixtures/voice_table_golden.json` |
| 5. 只读锁 / TOFU / `.vtmanifest` / manifest 验证 | `vt_project.py`、`vt_trust_store.py`、`vt_manifest.py` | 锁定拒写、TOFU 判定、四类整包结果用例 |
| 6. 水纹背板与玻璃主题的「减弱动效」偏好保留 | 未触碰 | — |

另：`key_id` 是否写入 `spec_hash`（`m2-spec` §12 未决项 c）当前采用**不写入**方案，
签名者身份走签名块，因此签名动作不会让已有产物变为 `stale`；若日后改为写入，只需调用方传参，
字节格式无需改动。

### 追加登记（2026-09-21 · 源码分发就绪（②′）第一批：文档、后端可见性、Rust 依赖清单）

背景：本修改版**以源码形式分发**（不做 EXE 打包），而 `vtcore` 是 Rust 扩展。接收者若不构建它，
`spec_hash` 会**静默回退**到 Python 参考实现（数值逐字节一致，但签名 / `.vt` 容器 / 信任库 /
整包校验不可用）。本批处理三处缺口。

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

新增文件：

- `tools/collect_rust_licenses.py` —— 从 `vtcore/Cargo.lock` 与本地 cargo registry 元数据
  **机械汇总** Rust 依赖许可证（不依赖人工转录）；支持 `--json` 与 `--out`（UTF-8 直写，
  避免控制台编码影响中文表头）。

修改过的原有文件：

- `README.md` —— 新增「可选组件：vtcore（Rust 扩展）」一节：说明不构建也能运行、回退的具体后果、
  三步构建命令（rustup → `pip install maturin` → `maturin develop --release`）、
  abi3 产物跨 Python 小版本通用，并指向 `vtcore/README.md` 与 `docs/voice-batch-m2-spec.md`。
- `app/widgets/about_dialog.py` —— 「关于与许可」页新增一行**规范字节后端**显示：为 `vtcore` 时
  只显示后端名；处于回退态时额外提示"签名、`.vt` 容器与整包校验不可用"。该行属技术信息，
  按仓库规则保持固定中文原文。
- `THIRD_PARTY_LICENSES.md` —— 新增「Rust 依赖（vtcore 扩展）」：**53 个第三方 crate** 的名称 /
  版本 / 许可证表（由上述工具生成），逐项标出非 MIT/Apache 项（BSD-3-Clause ×3、LLVM-exception、
  `(MIT OR Apache-2.0) AND Unicode-3.0`、Unlicense、含 LGPL-2.1-or-later 的可选项）；
  并说明源码分发下各 crate 自带许可证文本，**若改为分发 vtcore 二进制产物则必须另行附带文本并重新审计**。

验收（2026-09-21 19:49）：`tools/run_gate.ps1` **24 模块全绿**（含读取 `THIRD_PARTY_LICENSES.md`
与构造「关于」对话框的用例）；ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 界面接线（①）增量 1：导出 `.vt`）

工作格式按既定分叉取「甲」：**继续以 JSON 工程文件编辑，`.vt` 作为导出/签名的成品**。

修改过的原有文件：

- `app/pages/voice_batch_page.py` —— 工作台工具栏新增「导出 .vt」按钮：把当前表写成 `.vt` 容器
  （默认未签名；传 `seed_hex` 时签名并自动上锁）。核心逻辑抽成 `export_vt(target, *, seed_hex="")`，
  只返回可读状态文案、不做对话框交互，便于无界面测试；vtcore 未构建时按钮禁用并附 tooltip，
  导出请求返回明确提示（**不静默失败**）。
- `app/i18n.py` —— 新增 7 条中英文案：导出按钮、导出对话框标题、导出成功、已签名导出成功、
  扩展未构建、只读锁拒绝、按错误码的失败提示。
- `app/services/vt_project.py` —— 新增公开访问器 `vtcore_api()`（界面调用 `sign_object` 等扩展能力），
  避免跨模块使用私有函数。
- `tests/test_voice_batch.py` —— 新增 4 例：扩展缺失时的提示文案、导出未签名容器（行数与表格一致、
  `row_id` 可解析）、带种子导出即签名且上锁、二次导出被锁拒绝、按钮可用性与后端一致；
  另加 `_reset_table()` 使导出断言与"页面启动会自动加载上次工程"的历史无关
  （此前的写法在门禁里因残留工程行而失败，已按真实加载行为修正）。

验收（2026-09-21 20:03）：`tools/run_gate.ps1` **24 模块全绿**（`voice_batch` 由 11 → **15 例**）；
ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 界面接线（①）增量 2：密钥与签名导出）

新增文件：

- `app/widgets/vt_key_dialog.py` —— 「签名密钥」对话框：列出项目密钥（当前密钥置顶）、显示
  `key_id` 与**公钥**（可选中复制）、可生成新密钥；私钥始终留在 `config/`，界面不读取不显示。

修改过的原有文件：

- `app/pages/voice_batch_page.py` —— 工具栏新增「签名并导出 .vt」与「密钥…」：
  `sign_and_export_vt(target, create_if_missing=True)` 用**项目密钥**签名并导出（无密钥时自动生成，
  之后复用同一把），失败一律转可读文案；首次使用时弹确认框；新增模块级 `_key_store_dir()`
  指向项目内 `config/`（便于测试整体替换）；vtcore 未构建时三个相关按钮统一禁用并带 tooltip。
- `app/services/vt_key_store.py` —— 新增 `latest_project_key()`（当前密钥 = 最近写入的一把）与
  `describe_project_key()`（由种子推导公钥，只返回公开引用，**不返回私钥**）。
- `app/i18n.py` —— 新增 13 条中英文案（签名导出、密钥对话框、提示语、不可读错误码等）。
- `tests/test_voice_batch.py` —— 新增 3 例：签名导出会**自动建密钥且二次导出复用同一把**
  （断言两次导出的签名者一致、文件已上锁、签名可验证）、无密钥且禁止创建时给出提示且不落盘、
  密钥对话框的列出/生成/复制公钥（公钥与种子推导结果一致）。

验收（2026-09-21 20:13）：`tools/run_gate.ps1` **24 模块全绿**（`voice_batch` 由 15 → **18 例**，
连跑两次结果一致）；ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 界面接线（①）增量 3：打开工程与锁状态徽章）

修改过的原有文件：

- `app/pages/voice_batch_page.py` —— 工具栏新增「打开工程…」：`open_project(path)` 载入 JSON 工程
  （`read_project` + 按旁车刷新各行产物状态），载入后**自动保存写回该工程文件**（`_project_path()`
  改为优先返回当前工程，未打开时仍用项目内默认路径）；新增**锁状态徽章** `lock_label`：
  导出已签名 `.vt` 后显示"🔒 已签名并锁定：<文件名>"，解锁后自动清空（`set_lock_state()`）。
  非 JSON 与损坏文件都返回可读文案，不抛给 UI。
- `app/i18n.py` —— 新增 6 条中英文案（打开工程动作 / 对话框标题 / 载入成功 / 打开失败 /
  仅支持 JSON / 锁徽章）。
- `tests/test_voice_batch.py` —— 新增 4 例：打开工程后行身份一致**且自动保存目标切到该文件**、
  非 JSON 被拒、损坏 JSON 报 `JSONDecodeError`、锁徽章随签名导出出现并在解锁后清空。

说明：按既定分叉「甲」，JSON 仍是工作格式；`.vt` 是导出成品，因此打开入口只接受 JSON
（`.vt` 提示"只读成品"），避免把只读容器当成可编辑工程。

验收（2026-09-21 20:31）：`tools/run_gate.ps1` **24 模块全绿**（`voice_batch` 由 18 → **22 例**，
连跑两次结果一致）；ruff 0 项；`compileall` 通过；CRLF 合规。
首跑时 `pyqtgraph_timeline` 因残留进程争用出现 TIMEOUT（该模块单独复跑 22 例 17s 通过，
属 `HANDOFF-M1.md` §五记载的已知环境 flake），清理残留 python 进程后复跑全绿。

### 追加登记（2026-09-21 · 界面接线（①）增量 4：TOFU 信任流程与整包清单 —— ① 收尾）

修改过的原有文件：

- `app/pages/voice_batch_page.py` —— 工具栏改为**两行**（上行：编辑与生成；下行：工程与签名），
  下行新增「校验 .vt…」「导出整包清单…」「校验整包…」：
  - `verify_vt_file(path, decide=...)`：结构校验 → 签名校验 → **TOFU 判定**（信任库落
    `config/vt_trust.json`）；已信任直通、已撤销拒绝、同工程换签名者且无轮换记录则告警、
    未签名只报"内容自洽通过"；首次见到未知签名者时弹**三选一**（信任并记住 / 仅本次 / 拒绝），
    `decide` 可注入以便无界面测试。
  - `export_manifest(package_dir, seed_hex=...)` / `verify_manifest_package(package_dir)`：
    生成与校验 `.vtmanifest`（后者输出四类结果摘要，含签名状态）。
- `app/i18n.py` —— 新增 22 条中英文案（校验 / 信任三选一 / 整包清单 / 各失败与告警文案）。
- `tests/test_voice_batch.py` —— 新增 5 例：首见信任并记住（且**已信任后不再询问**）、
  「仅本次」不写信任库、「拒绝」文案、已撤销密钥被拒 + 未签名容器提示、
  整包清单往返（`ok=2` → 改文件后 `modified=1`）与未签名清单报 `sig_missing`。

说明：① 界面接线四个增量至此全部完成 —— 工作台已覆盖「打开工程 → 导出/签名 `.vt` →
校验并处理 TOFU 信任 → 导出/校验整包清单」的完整闭环，全部经无界面测试覆盖。

验收（2026-09-21 20:40）：`tools/run_gate.ps1` **24 模块全绿**（`voice_batch` 由 22 → **27 例**，
连跑两次结果一致）；ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · `.vt` 只读查看（打开成品））

新增能力：导出的 `.vt` 现在可作为**只读**工程载入工作台查看（行字段完整还原），不再只提示"这是成品"。

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

修改过的原有文件：

- `vtcore/src/canonical.rs` —— 新增 `parse_row_bytes()`（`canonical_row_bytes()` 的**逆操作**）：
  按 §4.1 严格解析记录并还原必填/可选字段、`extra.` 前缀键与 `key_id`，未知键收进 `unknown`
  以免查看时静默丢失信息；`RecordError` 增 `MissingDomain` 与 `BadInteger` 两个变体。
- `vtcore/src/lib.rs` —— 新增 pyo3 导出 `parse_row_bytes(block) -> dict`（供只读查看）。
- `vtcore/tests/golden.rs` —— 新增 2 例：全部行向量**解析后重新编码字节一致**（无损往返）、
  畸形输入拒绝（缺域分隔 / 长度不符 / 长度前导零 / 整数非法）与最小行的默认值回落。
- `app/services/vt_project.py` —— 新增 `container_to_table(path)`：把 `.vt` 还原为只读 `VoiceTable`
  并套用旁车 `<文件>.vt.state` 状态（沿用 M1 §5 规则），返回 `signed` / `locked` / `table_hash` /
  `signature` / `applied`。顺带修掉一个**潜在 `NameError`**：该函数用到 `json` 而模块未导入
  （ruff F821 抓出；只有旁车分支才会触发，已补测试覆盖）。
- `app/pages/voice_batch_page.py` —— `open_project()` 按扩展名分流：`.json` 可编辑（自动保存写回
  该文件）、`.vt` **只读查看**（不改变自动保存目标、不改写容器本体），并按锁定状态刷新徽章；
  打开对话框过滤器改为 `*.json *.vt`。
- `app/i18n.py` —— 新增 4 条中英文案（过滤器名、只读载入（未签名/已签名两态）、支持类型提示）。
- `tests/test_voice_batch.py`、`tests/test_vt_project.py` —— 新增 5 例：只读查看还原字段与 `extra`、
  **不改写自动保存目标**、旁车状态被套用、破损 `.vt` 报错、未知扩展名被拒；服务层另加
  "还原后重新编码与原容器**字节一致**"与签名/锁定信息核对。

验收（2026-09-21 20:48）：`cargo test` **39 例全通过**（黄金向量 4 → **6**）；
`tools/run_gate.ps1` **24 模块全绿**（`voice_batch` 27 → **30 例**、`vt_project` 10 → **12 例**）；
ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 交接轮 A：`.gitignore` 补仓库根临时目录规则）

- `.gitignore` —— 新增 `/tmp*/`（**限定仓库根**）：本机曾残留 7 个 `tmp*` 目录
  （子进程在仓库根以 `mkdtemp` 建目录所致）。这些目录对后续进程**不可读**，
  `git` 无法列出其内容、又匹配不上既有规则（原规则只有 `*.tmp`，**不匹配目录名**），
  表现为**每条 git 命令都打印 7 条 "could not open directory" 告警**，且它们既不被忽略、
  也不被列为未跟踪，属"隐形未跟踪"。规则限定根目录，以免误伤树内同名目录。
  同轮已清除这 7 个残留目录（清除后告警消失）；保留规则以防复发。

验收（2026-09-21 21:19）：`tools/run_gate.ps1` **24 模块全绿**（318 用例，exit 0）；
ruff 0 项；`compileall` 通过；CRLF 合规（工作区仅 `vtcore/Cargo.lock` 为 `w/lf`，属已登记例外）。

### 追加登记（2026-09-21 · 交接轮 B：stub 服务端补 `shutdown()`，消除门禁"全绿却 FAILED"）

修改过的原有文件：

- `tests/test_cosyvoice_shim.py` —— `tearDownClass` 在 `server_close()` 之前补
  `server.shutdown()` 与 `thread.join(timeout=5)`。
- `tests/test_tts_interface.py` —— `StubService.__exit__` 同上（同一模式）。

说明：两处 stub HTTP 服务此前**只调 `server_close()`、不调 `shutdown()`**，守护线程里的
`serve_forever()` 被直接抽掉底层 socket 后抛 `OSError [WinError 10038]`，其 traceback 在
解释器退出阶段继续写 `stderr`，与 stderr 缓冲锁的收尾竞争，**约 2%（1/50）概率**触发
`Fatal Python error: _enter_buffered_busy: could not acquire lock for <_io.BufferedWriter
name='<stderr>'> at interpreter shutdown, possibly due to daemon threads` 并 abort
（实测退出码 `0xC0000409`）。症状极具误导性：unittest 已打印 `Ran N tests / OK`，
但**进程退出码非零**，于是 `tools/run_gate.ps1` 记为 `FAILED` —— 即门禁"全绿却失败"，
且每次随机落在 `tts_interface` 或 `cosyvoice_shim` 之一（两者合计约 24 模块中每轮 4%）。

`shutdown()` 会阻塞至 `serve_forever()` 循环退出，线程随之正常结束，因而从**机制上**
关闭该竞态（而非仅降低概率）：实测 stderr 中 `serve_forever` 线程 traceback 由
**4261 字节 → 0**；同条件 50 轮复跑 abort 由 **1/50 → 0/50**。

验收（2026-09-21 21:19）：`tools/run_gate.ps1` **24 模块全绿**（318 用例，exit 0，
`tts_interface` 与 `cosyvoice_shim` 均 OK）；ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 交接轮 C：品牌改名与 fork 来源声明前置）

改动性质：**用户可见品牌与文档标题**（不改规范字节格式与许可名称，见下"有意不改"）。

- `app/branding.py` —— `APP_NAME` 由 `WT-NameRelay` 改为 **`WT-Tool`**，新增
  `APP_SUBTITLE = "Experimental Version"` 与事实性署名常量 `BASE_AUTHOR_HANDLE`、
  `BASE_REPO_URL`；`WINDOW_TITLE` 仍取 `APP_NAME`（窗口标题 "WT-Tool"）。
  `BASE_PROJECT` 仍为 `WT-NameRelay` —— 它表示 **fork 来源**，不是本版名称。
- `app/widgets/disclaimer_dialog.py` —— 启动"使用声明"**首段即声明 fork 来源**
  （原项目 WT-NameRelay、原仓库地址、原作者 Beiku/@beikuwawa、基线 beta 0.2.0，
  并声明不代表原项目作者）；眉题改为 `Experimental Version · 使用声明`。
  顺带把段落样式由**下标硬编码**改为与 `_PARAGRAPHS` 等长的 `_STYLES` 元组 ——
  原先 `index == 3` / `index in (1, 2)` 在首段插入后会让"严禁二次售卖"的告警色串位。
- `app/widgets/about_dialog.py` —— 标题下新增副标题行；页脚改为 fork 优先表述
  （"本工具 fork 自 Beiku 的 WT-NameRelay beta 0.2.0（仓库地址） · 本版维护者：Diderde"）。
- `app/i18n.py` —— `dialog.disclaimer.window_title` 改为 `WT-Tool 使用声明` /
  `WT-Tool Disclaimer`；`_ABOUT_OURS`（法律内容，固定中文原文，不入 `_STRINGS`）改为
  fork 来源前置并附原仓库链接。
- `README.md` —— 标题改为 `# WT-Tool（Experimental Version）`；首段明确"本仓库是 fork，
  不是原项目的官方版本"；页脚署名改为 fork 优先。
- `MODIFICATION_NOTICE.md` —— 标题随本版名称；"基本信息"表新增 **本修改版名称** 与
  **原始仓库** 两行，原始作者补 GitHub 账号；"运行行为差异"与英文摘要同步。
- `tests/test_release_features.py`、`tests/test_ui_smoke.py` —— 两处品牌断言同步为 `WT-Tool`。

**有意不改**（避免破坏规范或越界）：

- `app/services/vt_project.py` 的 `GENERATOR = "WT-NameRelay/0.2"`、vtcore 侧生成器串与
  黄金向量 —— 属 `.vt` / manifest **规范字节**（§七.6 冻结），改名会让已产出产物与测试集体失配。
- `LICENSE` 内的 `WT-NameRelay Source-Available License 1.0` 与 `resources.qrc` 别名 ——
  原许可名称，不得更名。
- `.spec` / `windows_version_info.txt` / `build_release.py` 的产物名、Rust 侧元数据、
  临时目录前缀 —— 已定不做 EXE 打包，本轮未动。

验收（2026-09-21 21:33）：`tools/run_gate.ps1` **24 模块全绿**（318 用例，exit 0，
`release_features` 与 `ui_smoke` 均 OK）；ruff 0 项；`compileall` 通过；
CRLF 合规（8 个改动文件均 `w/crlf`）。

### 追加登记（2026-09-21 · 交接轮 D：清理同一类项目名残留）

轮 C 只覆盖用户可见品牌与文档标题；本轮清掉 `app/` 与 `tools/` 内**同一类**的项目名
残留（均为文案与标识，不涉及规范字节）：

- `app/__init__.py` —— 包文档串 `WT-NameRelay application package.` → `WT-Tool ...`。
- `tools/cosyvoice3_shim.py` —— `_Handler.server_version` 由
  `WT-NameRelay-CosyVoice3-Shim/1.0` 改为 `WT-Tool-CosyVoice3-Shim/1.0`（HTTP `Server:` 头）。
- `tools/extract_crew_names.py` —— argparse 描述文案随改名。
- `tools/visual_check_audio_page.py` —— 视觉自检窗口标题随改名。

**仍未改**（按轮 C 已确认的范围，或属上游历史物）：`packaging/hooks/hook-pyqtgraph.py`
的文档串（打包区）、Rust 侧元数据、`.spec` / `windows_version_info.txt` /
`build_release.py` 的产物名、`FFMPEG_BUILD_INFO.md` 与 `JSON_GROUPING_REPORT.md`
（上游文档）、临时目录前缀、`LICENSE` 原许可名与 `resources.qrc` 别名、
`vt_project.GENERATOR` 等规范字节串。

验收（2026-09-21 21:36）：`tools/run_gate.ps1` **24 模块全绿**（318 用例，exit 0）；
ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 交接轮 E：正式名定为全称 / "战争雷霆" 统一为War Thunder）

**正式名**：轮 C 曾把名称拆为 `WT-Tool` + 副标题 `Experimental Version`；本轮改为
**单一正式名称 `WT-Tool-Experimental Version`**，并移除 `APP_SUBTITLE` 与两处副标题控件
（关于页副标题行、声明眉题恢复为"使用声明"）：

- `app/branding.py` —— `APP_NAME = "WT-Tool-Experimental Version"`，删除 `APP_SUBTITLE`。
- `app/widgets/about_dialog.py`、`app/widgets/disclaimer_dialog.py` —— 移除副标题行与眉题拼接；
  声明首段的 fork 来源句补上本版名称（"本项目（WT-Tool-Experimental Version）为 …"）。
- `app/i18n.py` —— `dialog.disclaimer.window_title` 随全称。
- `README.md`、`MODIFICATION_NOTICE.md`（标题、"基本信息"表、运行行为差异、英文摘要）随全称。
- `tests/test_release_features.py`、`tests/test_ui_smoke.py` —— 两处品牌断言同步为全称。

**声明措辞**：启动"使用声明"第 2 段由原文改为
"本工具仅用于辅助制作War Thunder语音包，不提供任何未经许可的War Thunder官方的资产。"

**术语统一**："战争雷霆"改为正式名**War Thunder**（全仓 6 处 → **5 处**：
`_ABOUT_ORIGINAL` 那处属上游原文，已由轮 F 回退）：
`app/i18n.py` 的 `home.eyebrow`、`home.subtitle` 与 `_ABOUT_ORIGINAL` 首句、`README.md`
项目描述、`windows_version_info.txt` 的 `FileDescription`，以及声明正文（随本轮改写）。
其中 `_ABOUT_ORIGINAL` 原按"逐字保留、不翻译"处理，本轮曾一并统一术语；
该处已由轮 F 按"上游原文不改"回退。

**保留短名**：`app/__init__.py` 的包文档串与 `tools/` 内部工具（shim 的 HTTP `Server` 头、
argparse 描述、视觉自检窗口标题）仍用短名 `WT-Tool` —— 均为内部标识，且 HTTP 产品令牌
不允许含空格。

验收（2026-09-21 21:44）：`tools/run_gate.ps1` **24 模块全绿**（318 用例，exit 0）；
ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 交接轮 F：上游原文不改（回退轮 E 一处）/ War Thunder 相邻不留空格）

**上游边界（经确认）**：**原仓库的相关文档（许可、证书等）与逐字保留的上游原文一律不改**，
可改的只限本 fork 自己的文案。据此回退轮 E 的一处越界改动：

- `app/i18n.py` 的 `_ABOUT_ORIGINAL` 首句 —— 由 `War Thunder语音包文件名称补全、复制与
  语音处理工具。` **回退为上游原文**`战争雷霆语音包文件名称补全、复制与语音处理工具。`
  （该块标注"逐字保留，不做翻译"）。故术语统一的实际结果为 **6 处 → 5 处**，非轮 E 所记的 0 处。

**上游不改清单**（此后不再触碰）：`LICENSE`、`PROJECT_USAGE_NOTICE.md`、
`JSON_GROUPING_REPORT.md`、`FFMPEG_BUILD_INFO.md`、`app/resources/resources_rc.py` 内嵌的
`LICENSE` 副本，以及 `app/i18n.py` 的 `_ABOUT_ORIGINAL` 整块。

**间距统一为口述风格**：本 fork 自有文案中 `War Thunder` 与中文相邻处**不留空格**：

- `app/i18n.py` —— `home.eyebrow` 中文串 `War Thunder语音工具`、`home.subtitle` 中文串
  `War Thunder语音包文件名称补全与复制工具`。
- `app/widgets/disclaimer_dialog.py` —— 声明第 3 段两处（`War Thunder及其关联主体`、
  `War Thunder及相关名称`）。
- `README.md` —— 项目描述与"非官方第三方工具"段各一处。
- `windows_version_info.txt` —— `FileDescription`。
- `MODIFICATION_NOTICE.md` —— "其他声明"段与轮 E 标题、正文（本文件随程序展示，属可见文案）。

英文串（如 `War Thunder Voice Tools`）与上游文档内的空格不受此规则影响。

验收（2026-09-21 21:50）：`tools/run_gate.ps1` **24 模块全绿**（318 用例，exit 0）；
ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 交接轮 G：进入 TTS 工作台不再阻塞 GUI 线程）

**缺陷**：`MainWindow._open_voice_batch()` 在 **GUI 线程**同步做后端装配 ——
`GptSovitsBackend.is_available()` 是阻塞式 HTTP 探活（`timeout=3.0`），CosyVoice 3 分支
还会拉起 shim 子进程并轮询到就绪（`SubprocessTtsService.start()`，上限 **180s**）。
实测点击 TTS 模型卡后界面冻结：GPT-SoVITS **2.079s**、CosyVoice 3 **2.613s**；
若服务始终起不来，最坏会冻满 180s。（`SerialTtsRunner` 的文档本就写着"勿在 UI 线程跑"，
只有路由这一层违反了。）

根因数据（非代码问题）：本机 `Steam++.Accelerator` 在 <proxy> 提供系统代理并带
localhost 过滤，使"连接本机未监听端口被拒"需约 **2.05s** —— 对照组未使用端口 59999 同样
2.05s，裸 socket 亦然，故每次失败探活都吃满 2 秒。

修改过的原有文件：

- `app/main_window.py` —— 新增 `backend_ready` / `backend_failed` 信号与装配令牌
  `_backend_token`；`_open_voice_batch()` 改为"立即切页 + 起 daemon 工作线程"；
  新增 `_prepare_backend()`（工作线程，禁止触碰界面对象）、`_on_backend_ready()`、
  `_on_backend_failed()`、`_stop_service()`；`_backend_for()` 改为返回
  `(backend, service)` 元组，不再直接写 `self._voice_service`（消除跨线程写状态）；
  `closeEvent()` 自增令牌作废在途结果。过期结果由**工作线程自行**收掉刚拉起的服务 ——
  只靠界面侧判断的话，关窗后事件循环不再排空信号，子进程会漏在外面。
- `app/pages/voice_batch_page.py` —— 新增 `_backend_pending` 与 `set_backend_pending()`
  （禁用生成 + 提示连接中）；`set_backend()` 清除 pending 并在非生成态恢复按钮；
  `_update_summary()` 在 pending 期间不覆盖提示文案。
- `app/i18n.py` —— 新增 1 条中英文案 `voice.backend.connecting`
  （"正在连接推理服务…" / "Connecting to the inference service…"）。
- `tests/test_release_features.py` —— 新增 `TtsBackendRoutingTests` 3 例：切页即时返回
  并显示连接中、改选后过期结果被丢弃且其服务被停掉、装配异常回落演示后端。

**实测（同一探针，修复前 → 修复后）**：`_open_voice_batch` 返回耗时
GPT-SoVITS **2.079s → 0.022s**、CosyVoice 3 **2.613s → 0.001s**；后台仍在
2.100s / 2.614s 完成装配 —— 阻塞时间没变，只是不再占用 GUI 线程。

**本轮未改**：那 2 秒本身（Steam++ localhost 过滤）仍在；缩短探活超时属另一项改动。

验收（2026-09-21 22:41）：`tools/run_gate.ps1` **24 模块全绿**（**321** 用例 = 318 + 3）；
ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-21 · 交接轮 H：TTS 工作台改「左微调 / 右推理」两栏，接通上游微调全链路）

**背景**：此前没有任何微调训练入口；推理参数也恒为 `params={}`，界面等于没有参数面。

**布局**：`app/pages/voice_batch_page.py` 的 body 改为 `QSplitter` 左右两栏（左「微调界面」
/ 右「推理界面」），原有表格、生成、试听、工程与签名能力全部留在右栏。

**右栏 · 推理参数**（新增 `app/widgets/tts_params_panel.py`）：

- 字段按后端切换：GPT-SoVITS 显示 `speed_factor` / `seed` / `top_k` / `top_p` /
  `temperature` / `text_split_method` / `prompt_text` / `prompt_lang`；CosyVoice 3 只显示
  `speed`（其 shim 只认这个字段）；
- 可选项按需下发：未勾"固定随机种子"不发 `seed`；`prompt_text` 留空不发；
  `prompt_lang` 为 `auto` 时不发（交后端按行语言处理）；
- 生成时真正塞进 `TtsRequest.params`，经既有契约透传给后端。

**左栏 · 微调**（新增 `app/services/tts_training.py` + `app/widgets/tts_train_panel.py`）：
驱动**上游脚本原样运行**，编排忠实复刻官方 `webui.py`：1A 文本/BERT → 1B 自监督特征
（Pro 版本多一步说话人向量 `2-get-sv.py`）→ 1C 语义 Token → s2 训练 → s1 训练。要点：

- prep 三阶段**没有命令行参数**，全部以环境变量传参（`inp_text` / `opt_dir` / `i_part` /
  `all_parts` / `_CUDA_VISIBLE_DEVICES` / `is_half` / `version` …），按 GPU 串拆 part 并行；
- 1A/1C 需把各 part 合并成单文件（1C 合并**带表头**），1B 不需要；分片合并后删除；
- 训练配置为**现场改写模板**：s2 走 JSON（Pro 系用专属模板），s1 走 YAML；
- 子进程 **CWD 固定为上游仓库根**；`is_half` 只传 `"True"`/`"False"`（上游会 `eval()`）；
  s1 额外传 `hz=25hz` 与合并后的 `_CUDA_VISIBLE_DEVICES`；`version` 必须在 env 里
  （s1/s2 的**导入期**依赖）；权重输出目录由本模块自建（上游在 import 时做）。

**顺带修掉一个自造缺陷**：s1 的 YAML 由本模块自写输出（本应用 venv **不含 PyYAML**，
且训练本就该用上游那套带 torch 的解释器）。初版把 `0.00001` 输出成 `1e-05` ——
PyYAML 的浮点正则**要求带小数点**，会被解析成**字符串**，Lightning 拿到即废；
已改为指数一律摊成普通小数，并加测试锁死。

修改过的原有文件：

- `app/pages/voice_batch_page.py` —— 两栏布局；`can_navigate_away` / `request_safe_close`
  计及训练运行中；`retranslate` 覆盖两栏标题与两个面板。
- `app/i18n.py` —— 新增约 50 条中英文案（两栏标题、推理参数、微调表单/阶段/状态/日志/报错）。
- `tests/test_voice_batch.py` —— 新增 `TtsParamsPanelTests` 3 例、`TtsTrainingPlanTests` 6 例。

**实测**：对着**真实上游模板**装配计划验证通过 —— v2ProPlus 用 `s2v2ProPlus.json` +
`s1longer-v2.yaml` 且 1B 多一步 `2-get-sv.py`；v1 用 `s2.json` + `s1longer.yaml`；
生成的 s1 YAML 保留模板原值（`phoneme_vocab_size` 732/512、`top_k` 15/5）并正确覆盖超参。

**未做（下一轮候选）**：数据集制作（0b 切分 / 0c ASR / 0d 标注）未接；训练前置检查
`readiness_report` 已就绪但未挂到界面按钮；训练产物（s2/s1 权重）尚未回填到推理侧模型选择。
真正的训练执行需在装有 torch 的上游环境里实跑验证（**本机未验证**）。

验收（2026-09-21 22:57）：`tools/run_gate.ps1` **24 模块全绿**（**330** 用例 = 321 + 9）；
ruff 0 项；`compileall` 通过；CRLF 合规。

## 追加变更登记（2026-09-21 TTS 两栏布局修复）

以下改动与新增同样按 **GPL-3.0-only** 授权（原始代码部分仍遵循原许可）：

### 新增文件

- `app/widgets/flow_layout.py` —— 流式布局（Qt 官方 FlowLayout 示例实现）：
  子项按行排列、一行放不下自动换行，用于按钮条在窄分栏下不压扁、不裁字。

### 修改过的原有文件

- `app/pages/voice_batch_page.py` —— 两栏最小宽度显式化（左 380 / 右 400）；
  右栏主要操作收为单行（添加行 / 生成选中行 / 生成未完成项 / 停止），
  行操作与工程、签名、校验、密钥等低频动作收进「更多」下拉菜单；
  推理参数面板默认折叠（展开后限高滚动）；主表格最小高度 180；
  隐藏本页未使用的通用状态面板（其高度挤压两栏，为布局压垮根因之一）。
- `app/widgets/tts_train_panel.py` —— 数据集 / 超参表单与阶段区放进滚动容器，
  日志区固定最小高度 140；表单随分栏增高逐步展开。
- `app/i18n.py` —— 新增「更多 / Parameters」切换文案。

### 本轮已知边界

- 任务运行期动态文案（如进度条格式串）沿用既有策略：待下次任务事件刷新。

### 追加登记（2026-09-21 · CosyVoice 3 契约诚实化）

- `tools/cosyvoice3_shim.py` —— `/synthesize` 契约升级：`voice` / `seed` / `language`
  从"启动期一次性生效、请求期被忽略"升级为**每请求参数**（CrispASR 会话旋钮在锁内
  串行应用：`set_voice`（参考调节有缓存）/ `set_tts_seed` / `set_target_language`）；
  种子 0 = 随机。
- `app/widgets/tts_params_panel.py` —— CosyVoice 3 移除语速假控件（crispasr
  cosyvoice3 运行时无语速旋钮），暴露固定随机种子；契约测试同步更新。
- `tests/test_voice_batch.py` —— `exposes_speed_only` 用例改为 `exposes_seed_only`
  （诚实契约：CosyVoice 3 参数为空或 `{seed: N}`）。

### 追加登记（2026-09-21 · 数据集工具 ASR 后端对齐官方矩阵）

- `app/services/tts_training.py` —— 新增 `ASR_BACKENDS` 官方矩阵（与上游
  `tools/asr/config.py` 的 asr_dict 逐项对齐：Fun-ASR-Nano / SenseVoice /
  达摩 ASR / Faster Whisper，语言·规模·精度约束随方式联动）；
  `asr_command` 按矩阵解析脚本路径，未知后端回落默认方式。
- `app/widgets/tts_train_panel.py` —— 「识别方式」下拉对齐四种官方后端；
  语言/规模/精度下拉随方式联动重填（保留仍可选中的当前值）。
- `tests/test_voice_batch.py` —— 新增 ASR argv 契约用例
  （funasr / faster-whisper / 未知后端回落默认）。

### 追加登记（2026-09-21 · CosyVoice 3 模型信息面板）

新增文件：
- `app/widgets/cosyvoice_info_panel.py` —— CosyVoice 3（GGUF）信息面板：
  用途说明、模型目录、就绪状态（q4 集合计数）、推理服务说明；随语言切换刷新。

修改文件：
- `app/pages/voice_batch_page.py` —— 左栏改为模型感知双面板栈：
  GPT-SoVITS 显示微调面板，CosyVoice 3 显示模型信息面板（`set_model_kind`）；
  装配后端时按后端类型联动切换。
- `app/main_window.py` —— 进入三级工作台时立即下发模型键（后端装配前先切左栏）。
- `app/i18n.py` —— 新增面板标题与模型状态文案。
- `tests/test_voice_batch.py` —— 新增模型切换行为用例。

### 追加登记（2026-09-22 · 缺陷修复轮：GBK bat 注释谎报编码 / 「应用权重」阻塞 GUI 线程）

本轮为**缺陷修复**，不含新功能。两处缺陷均由字节级 / 线程级核查发现（检查脚本见 `temp/`）。

#### 缺陷 1 · `download_tts_verify.bat` 头部注释谎报编码

第 5 行原写 `（UTF-8 / CRLF；并行下载；本地资产检测）`，但该文件**实际是 GBK**——
字节级实测：无 BOM、UTF-8 解码失败、GBK 解码成功、CRLF 324 处且无裸 LF。
项目约定（`AGENTS.md` §1、交接文档 §六.2）明确要求该文件必须 GBK，同目录 `start.bat:6`
也正确标注为 `（GBK 编码 / CRLF 行尾）`。该注释属**主动误导**：照它把文件另存为 UTF-8
会一次性毁掉全部 66 行中文。

修法：字节级 GBK 补丁（`temp/fix_bat_encoding_comment.py`：GBK 解码 → 精确锚点替换 →
GBK 编码写回，幂等可重跑），**未使用 Write/Edit 工具**（二者按 UTF-8 重写会毁中文）。
改后校验：UTF-8 仍不可解码、无 BOM、CRLF 324 → 324、裸 LF 0、中文行数 66 不变、
字节数 11728 → 11731（与 `UTF-8` → `GBK 编码` 的 GBK 字节差精确吻合）。

#### 缺陷 2 · 「应用权重」在 GUI 线程做阻塞 HTTP（回归）

`app/pages/voice_batch_page.py` 的 `_apply_weights_clicked` 由按钮 `clicked` 直连，
却同步调用 `GptSovitsBackend.set_weights()` —— 后者是**两个阻塞 HTTP**
（`/set_gpt_weights` + `/set_sovits_weights`），超时取 `DEFAULT_TIMEOUT_S` = **300 s**。
后果：点一下最坏冻结 **600 s**；本机因系统代理过滤 localhost，即使服务未启动也要卡约 4 s。
这与既有修复 `6253d0e`（把后端装配挪到工作线程）属**同一类回归**——权重热切换是其后
`96f88c0` 加入的，又把同步阻塞引了回来。

修法（沿用页面既有的"工作线程 + 事件队列 + QTimer 泵"范式，不另起炉灶）：

- `_apply_weights_clicked` 改为起 daemon 工作线程后立即返回；期间禁用按钮、提示"正在应用权重…"；
- 新增 `_apply_weights_worker`（工作线程边界：异常统一转失败结果，经 `_events` 回主线程）；
- `_drain_events` 新增 `"weights"` 分支：恢复按钮并按结果刷新摘要；
- `app/i18n.py` 新增 `voice.weights.applying`。

**顺带修掉一个健壮性问题**：`set_weights` 原先把两个端点包在同一个 `try` 里，任一失败只报
裸异常。上游**没有事务/回滚接口**，若 GPT 已切、SoVITS 失败，服务会停在"新 GPT + 旧 SoVITS"
的错配状态，而用户只看到"失败"、误以为没生效。现在失败信息写明是哪个端点失败、并标注
"某某已生效，当前为混合权重状态，请重试或重启推理服务"；docstring 亦标注该调用阻塞。

修改过的原有文件：`download_tts_verify.bat`、`app/pages/voice_batch_page.py`、
`app/services/tts_runner.py`、`app/i18n.py`、`tests/test_voice_batch.py`。

新增测试（`TtsWeightsApplyTests` 3 例）：慢桩下点击即时返回且显示"正在应用权重…"、
工作线程异常转成失败文案、不支持的后端不起线程。

验收（2026-09-22 18:06）：`temp\ps_gate.ps1` **24 模块全绿**（**335** 用例 = 332 + 3）；
ruff 0 项；`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-22 · 修复轮 2：`start.bat`「按需补齐」提示只列真正缺失项）

**现象**：`[1/3]` 的逐项检测已能正确标出「[缺失] ASR 识别模型」，但 `[2/3]` 的提示是
**写死的静态文案**，四项全列：

```
检测到缺失的 TTS 模型资源（GPT-SoVITS 代码 / CosyVoice3 GGUF / 预训练权重 / ASR 识别模型）。
下载来源: GitHub + hf-mirror.com（权重约 4.93 GB，支持断点续传）。
```

只缺 ASR 时也照样列出其余三项，且「约 4.93 GB」是 GPT-SoVITS 预训练权重的数字，
对该场景属误导。**下载逻辑本身正确**（`ASR_SET=1`、其余置 0 跳过），错的只是提示文案。

**改法**：① 逐项列出真正缺失的项；② 体积提示只在对应项确实缺失时出现：

```
检测到以下缺失项：
  - ASR 识别模型（Faster Whisper large-v3）
下载来源: GitHub + hf-mirror.com（支持断点续传）。
预计下载 ASR 识别模型约 3 GB。
```

由各 `NEED_*` 标记驱动 `if ... echo`，并补上了原先漏在列表外的 `NEED_COSY_RUNNER`。
体积数字只保留有据可查的两项（GPT-SoVITS 预训练权重 4.93 GB、ASR 约 3 GB，均取自
`download_tts_verify.bat` 既有文案），不臆造 GGUF/代码的体积。

**改法与验证**：该文件是 GBK，仍用字节级补丁（`temp/fix_start_bat_missing_list.py`，
**未使用 Write/Edit**）。改后校验：UTF-8 仍不可解码、无 BOM、CRLF 157 → 164（正好等于
新增 7 行）、裸 LF/CR 均为 0、无 `chcp`、中文行 45 → 51。

**行为验证**（`temp/verify_missing_prompt.py`）：从**发布文件里按行号抽取真实提示块**，
生成 GBK+CRLF 的临时 harness 用 `cmd` 实跑三种缺失组合，Y/N 喂 N 跳过下载：

| 场景 | 输出 |
| --- | --- |
| 只缺 ASR | 只列 ASR 一项 + 仅 ASR 体积提示 |
| 全部缺失 | 列全 5 项 + 2 条体积提示 |
| 只缺 GPT-SoVITS 代码 | 只列 1 项、无体积提示 |

断言全过（旧静态列表不再出现、未缺失项不得被列出、体积提示与缺失状态一致）。

> 验证过程踩到两个环境坑，记录以免重犯：① `cmd` 在非 936 代码页下读 GBK 的 bat，
> 中文会变成 `U+FFFD`（报告里表现为「锟斤拷」）——非产品缺陷，测试须显式 `chcp 936`；
> ② `subprocess` 传 list 时 `list2cmdline` 会转义命令内引号（成 `\"`），令 cmd 找不到文件；
> 含 `&` 的复合命令应传**单个字符串**。

验收（2026-09-22 18:13）：`temp\ps_gate.ps1` **24 模块全绿**（**335** 用例）；ruff 0 项；
`compileall` 通过；两个 bat 的 GBK / CRLF / 无 BOM / 无 `chcp` 均复检通过。
（首跑 `pyqtgraph_timeline` 出现 TIMEOUT，按交接文档 §六.1 单独复跑 22 例 16.8s 通过，
属已知环境时序 flake，非本轮改动所致。）

### 追加登记（2026-09-22 · 修复轮 3：下载过程实时显示已下载大小 / 用时 / 预计剩余时间）

**现象**：`download_tts_verify.bat` 的批量下载**全部静默**——GGUF（6 文件）与权重
（25 文件 / 4.93 GB）用 `curl -s` + `start /b` 丢后台并行，ASR（6 文件 / 约 3 GB）虽是前台
串行但同样带 `-s`。用户除了 `[排队] xxx` 之外看不到任何进度，不知道下了多少、还要多久。

**改法**（下载仍由 curl 负责，保留 `-C -` 断点续传与 `--ssl-no-revoke`，不改网络行为）：

- 新增 `tools/download_progress.py` —— **只读**进度监视器：统计目标文件在磁盘上的大小，
  算出已下载/总量、百分比、用时、速度与**预计剩余时间**。总量未知时（如 GGUF 取不到
  Content-Length）诚实降级为"总量未知，无法估算剩余"，不编数字。
  - 清单格式 `<预期字节>|<路径>`；预期为 0 时可用 `--url-base` 发 HEAD 取 Content-Length；
  - 退出条件：全部达标，或 curl 全部退出且一段时间无新增字节；
  - 完成判定只看"预期已知"的条目，清单里的说明行不会卡住完成；
  - 始终以 0 退出——它只是显示层，绝不能影响下载流程。
- `download_tts_verify.bat`（GBK 字节级补丁，**未使用 Write/Edit**）：
  - 解析可用的 Python（优先 `.venv`，回退 PATH 上的 `python`）与工具路径，缺失则静默跳过进度显示；
  - GGUF 与权重两个并行阶段：排队后调用监视器（权重用清单里的精确大小，GGUF 用 HEAD 探测）；
  - ASR 阶段是前台串行，直接去掉 `curl -s` 的 `s`，让它自带的进度表（含用时/剩余）显示出来。
- `start.bat` 本轮**未改动**：其中的 CosyVoice3 推理器下载本就是前台、无 `-s`，curl 自带进度表
  已含大小/用时/剩余；再包一层反而重复。

**顺带**（防御性收紧，**不是缺陷修复**）：给 `:check_weight` / `:queue_weight` / `:verify_weight`
各加一行数字守卫 `for /f "delims=0123456789" %%A in ("%~1") do exit /b 0`，使清单若出现非数字行
不会被当作下载项去比较大小。

> **更正一处此前的错误判断**：我最初认为权重清单首行的说明注释（含 `|`）会被当成第 26 个下载项、
> 多发一次 404 请求并让计数 +1。用真实清单实跑真实 `:check_weight` 循环后**该判断不成立**：
> 实测 `W_SKIP=25 W_FAIL_N=0`，计数精确等于 25 个真实文件、无任何报错输出。同时验证新增守卫
> 在真实清单上 **25 行全部正常放行**，没有误伤。

**验证**：

- 监视器自测（`temp/test_download_progress.py`，5 种情形）：全部达标 → 立即完成并显示
  `2.93 KB/2.93 KB (100.0%)`；部分下载 → 显示百分比/用时/剩余并超时收尾；总量未知 → 诚实降级
  （`完成 0/0`）；清单缺失 → 优雅跳过；**清单夹说明行 → 仍判为完成 2/2**（不被卡住）。
- bat 行为验证（`temp/verify_progress_bat.py`、`temp/verify_check_weight.py`）：从**修补后的真实
  文件**抽出代码行实跑 —— GGUF 产出 `0|绝对路径`、权重产出 `<精确大小>|绝对路径`，格式符合
  监视器契约；真实 `:check_weight` 循环得 `W_SKIP=25 W_FAIL_N=0`。
- 编码不变量：两个 bat 均 GBK 可解、UTF-8 不可解、无 BOM、无 `chcp`；`download_tts_verify.bat`
  CRLF 324 → 361（正好等于新增 37 行）、裸 LF / 裸 CR 均为 0、行数 324 → 361。

> 环境坑（延续上一轮的记录）：`cmd` 在非 936 代码页下读 GBK 的 bat 会把中文变成 `U+FFFD`，
> 测试须先 `chcp 936`；子进程 stdout 为管道时 Python 按系统默认编码（本机 GBK）输出，
> 测试要按 GBK 解码。另外：**含中文的文本文件一律用 write/edit 工具改**，用 PowerShell
> `Get-Content`/`Set-Content` 往返会因 BOM 与编码推断把中文毁掉（本轮踩到过一次）。

验收（2026-09-22 18:28）：`temp\ps_gate.ps1` **24 模块全绿**（**335** 用例）；ruff 0 项；
`compileall` 通过；两个 bat 编码不变量复检通过。
（首跑 `pyqtgraph_timeline` 再次 TIMEOUT，单独复跑 22 例 17.7s 通过，同属已知环境 flake。）

### 追加登记（2026-09-22 · 文档轮：新增开发注意事项汇编）

新增文件：

- `docs/development-notes.md` —— 把散落在 `AGENTS.md`、开发经验手册、历次交接文档与
  `MODIFICATION_NOTICE.md` 里的**开发注意事项**汇编成一份仓库内可查的操作手册，共 10 节：
  权威顺序与入口 / 硬规则 / 每轮收尾流程 / 门禁与测试 / 环境与工具链 / 批处理 /
  本机工具链陷阱 / 冻结的架构决策 / 仓库布局 / 速查命令。目标是让新接手的人或代理
  **动手前在一处就能读全**，减少返工与损坏文件（本轮及前几轮踩过的坑全部收录）。

修改过的原有文件：

- `.gitignore` —— 模型/音频通配符补 `*.gguf`。撰写文档核对时发现：该清单已有
  `*.onnx` / `*.pt` / `*.pth` / `*.ckpt`，唯独漏了 `*.gguf`（CosyVoice3 的模型格式，
  单个 1~3 GB）。现有 GGUF 都落在已忽略的 `TTS model/` 下，**不构成实际泄漏**，
  但补上可防将来把 GGUF 放在别处时误入库 —— 与相邻条目意图一致。

**文档事实自查**：新增 `temp/check_doc_facts.py`，逐条核验文中声称的路径、目录、依赖清单、
门禁模块数与清单一致性、关键符号存在性、temp 辅助工具与 cargo 路径，共 **43 项**。
首轮 3 项失败：1 项是脚本自身把仓库外路径当成仓库内（已改文档措辞）、1 项即上述 `*.gguf`
缺失（已补）、1 项是本轮登记尚未写入（本提交补齐）。复核后全部通过。

验收（2026-09-22 18:35）：`temp\ps_gate.ps1` **24 模块全绿**（**335** 用例）；ruff 0 项；
`compileall` 通过；CRLF 合规。

### 追加登记（2026-09-22 · 修复轮 4：资源完整性检测 + 官方哈希比对）

**起因**：`start.bat` 的检查只看**存在性**（且权重只抽查一个代表文件），无法发现"文件在但内容残缺"。
本轮补上内容完整性检测，并引入**官方哈希**作为基准。

#### 1 · 官方哈希清单（新增 `tts_assets_manifest.txt`，41 文件 / 12.52 GB）

- 新增 `tools/collect_tts_asset_hashes.py` —— 从 HuggingFace tree API 采集：
  **LFS 大文件取 `lfs.oid`（官方 SHA-256）**，普通小文件取 `oid`（git blob SHA-1，
  可按 git 算法本地复算）。采集一次写进仓库，**运行期校验不依赖网络**。
  范围按"下载脚本实际会拉取的文件"裁剪：权重 25、GGUF 11（全部集合）、ASR 5。
- 采集时发现 **`hf-mirror.com` 的 API 返回 403**，而 `huggingface.co` 经系统代理可达
  （直连超时）——采集脚本用默认 opener，已在注释中写明。

#### 2 · 校验器（新增 `tools/verify_tts_assets.py`）

- 默认只做**存在性 + 大小**比对（快，仅 stat），适合每次启动跑；
  `--hash` 才逐文件计算官方哈希比对（慢，需读全量字节）。
- 区分四种结果：`ok` / `缺失` / `不完整（大小不符）` / `哈希不符`，另有
  `--allow-missing`：GGUF 按集合下载，未选用的文件不计为错误（但**已存在却大小不符仍算错**）。
- **只读**，绝不修改任何文件；`--group-ascii` 供 bat 解析。

#### 3 · `start.bat`（GBK 字节级补丁，未用 Write/Edit）

- **[1/3] 新增资产完整性检测**：对 weights / gguf / asr 三组各跑一次大小校验，
  有问题的组把对应 `NEED_*` 置 1，于是会被列入缺失清单并交由下载脚本按需补齐；
  Python/清单未就绪时打印"跳过"而不报错。
- **新增 `start.bat /verify` 深度校验模式**：逐文件比对**官方哈希**，只报告不下载。
- **修正一处显示与标记不一致**：原第 47 行先打印结论、后设置 `NEED_WEIGHTS`，
  导致"权重都在、只缺清单文件"时 `[1/3]` 显示 `[OK]` 而 `[2/3]` 又列为缺失；
  已把判断提前，并把文案改为"权重或缺清单文件"。
- 头部注释补充 `/verify` 用法。

#### 4 · `download_tts_verify.bat`：ASR 列表去掉不存在的 `vocabulary.txt`（缺陷修复）

`Systran/faster-whisper-large-v3` 仓库实际只有 7 个条目，**没有 `vocabulary.txt`**
（`config.json` / `model.bin` / `preprocessor_config.json` / `tokenizer.json` / `vocabulary.json`）；
上游 `fasterwhisper_asr.py` 对 large-v3 也主动把该文件从下载列表移除。
原 `FW_LIST` 带着它会导致：① 每次多下一个必然 404 的文件（含回退官方 HF 的第二跳）；
② 收尾校验永远报一条消不掉的「ASR 文件不完整: vocabulary.txt」。

#### 5 · 测试与门禁

- 新增 `tests/test_asset_verify.py`（8 例）：真实清单解析与分组、**git blob SHA-1 与
  `git hash-object --no-filters` 对拍**、sha256 与 hashlib 对拍、缺失/大小/哈希三档判定、
  `--allow-missing` 语义、汇总计数。为避免依赖未下载的大文件，构造情形时把模块级 `REPO`
  patch 到临时目录。
- `tools/run_gate.ps1` 与 `temp/ps_gate.ps1` 的 `$mods` **各加 `asset_verify`** →
  门禁由 24 模块升为 **25 模块**。

#### 6 · 实证（本机真实资产）

- **哈希链路自证**：`git-sha1` 与 `git hash-object --no-filters` 完全一致（注意：默认的
  `git hash-object` 会套用 `.gitattributes` 的 text/eol 过滤，哈希的是 LF 归一后的 blob，
  与"按存储字节"的 HF oid 口径不同——这一点已写进测试注释）。
  三个 GGUF 的**官方 SHA-256 与本地实算逐字节吻合**（665 KB / 14 MB / 41 MB 各一）。
- **端到端**：抽出修补后 `start.bat` 的真实 `:check_integrity` 子过程对真实资产跑三组 ——
  `weights` 25/25 → 不置位；`gguf` 通过 6 / 未选用 5 → 不置位；
  `asr` 报 3 缺失 + **`model.bin` 大小 33,912,329 应为 3,087,284,237** → 正确置位 `NEED_ASR=1`。
- **本轮最有价值的发现**：那个残缺的 `model.bin` **文件是存在的**，旧的 `if not exist` 判断
  会显示 `[OK] ASR 识别模型`，用户要到识别失败才发现；新检测把它判为**不完整** ✓。
  这正是"增加内容完整性检测"的实际价值。

验收（2026-09-22 18:53）：`temp\ps_gate.ps1` **25 模块全绿**（**343** 用例 = 335 + 8）；ruff 0 项；
`compileall` 通过；CRLF 合规；两个 bat 的 GBK / 无 BOM / 无 `chcp` 不变量复检通过。
（两轮门禁分别命中 `audio_page_matrix` 与 `pyqtgraph_timeline` 各一次，均按交接文档 §六.1
单独复跑通过——已知环境时序 flake，与本轮改动无关。）

### 追加登记（2026-09-22 · 文档轮 2：Test Drive 立项文档移入 `docs/`）

#### 1 · 变更内容

- **新增 `docs/test-drive-plan.md`** ——《The Test Drive — A Standalone Voice-Pack
  Simulator for War Thunder》立项规划 v1.0（2026-09-21，英文 canonical），
  由 `temp/mod_plan.md` 原样移入：**正文逐字未改，仅归一 CRLF**（源文件实测为 LF-only）。

#### 2 · 为什么移

`temp/` 是 gitignored 的本地目录（现有 800+ 个历次会话的补丁 / 探针 / 日志），
立项文档放在其中既不进版本控制，也会随 `temp/` 清理一并丢失。
上一份交接文档 §九 已建议"若要长期保留则移入 `docs/`"，本轮据此落位。

#### 3 · 移动方式（可复核）

不做人工转录，走字节级脚本 `temp/move_test_drive_plan.py`（读源 → 归一 CRLF → 写目标），
脚本内置自校验 6 项并全部 PASS：正文逐字不变 / 目标纯 CRLF（裸 LF=0、裸 CR=0）/
行数与源一致（263）/ 无 BOM / UTF-8 可解码 / 无开发机绝对路径。
字节数 13090 → 13353，差值 263 恰为补入的 263 个 `\r`，与行数吻合。

#### 4 · 边界（重要）

- 该文档是**立项规划，不是已交付功能**：其 §11 路线图（P1 / P2 / P3）与 §5.2 提到的
  `tools/export_voice_sim_mapping.py` **在本仓库尚不存在**，不参与任何门禁与测试；
- Test Drive 本体是**独立项目、独立仓库**（文档 §9），与本仓库语音包产线互不阻塞；
- 本轮**未改动任何代码、规格或界面**，故无运行行为差异。

验收（2026-09-22 19:08）：`temp\ps_gate.ps1` **25 模块全绿 / 343 用例**（本轮无 flake）；ruff 0 项；
`compileall` 通过；行尾合规（唯一例外 `vtcore/Cargo.lock`，已登记）；
`docs/test-drive-plan.md` 与源文件内容逐字一致（脚本已校验）。

### 追加登记（2026-09-22 · 清理轮：公开面去掉内部环境与内部流程措辞）

#### 1 · 变更内容（纯文案，无行为变化）

- `tools/run_gate.ps1` —— 头注释去掉"与 `temp/ps_gate.ps1` 同源 / 不依赖沙箱专用补丁 /
  普通开发机"这类内部环境表述，改为陈述脚本自身行为（逐模块独立进程 + 超时保护，
  结果写入 `tools/gate-results.txt`）。
- `tests/test_vt_project.py` —— 辅助方法 docstring 的"临时目录会被沙箱池复用"改为
  "临时目录可能被复用"。
- `vtcore/README.md` ——
  ① "仅测试交叉验证用" → "仅交叉验证用"；
  ② 构建说明不再提 `tests/test_vtcore.py` 与"门禁的 `vtcore` 模块"，改为**如实说明未构建时的
  后果**（应用仍可运行，签名 / `.vt` 容器 / 整包校验不可用，「关于与许可」页会提示）；
  ③ 原「## 测试」一节改为「## 验证」：不再给出 `cargo test` / `unittest tests.test_vtcore` /
  黄金向量路径等指向开发侧产物的指引，只保留规范基准与两侧对拍说明；
  ④ 结尾删除"门禁 24 模块全绿"（既是内部流程表述，也是过期数字）。
- `docs/voice-batch-spec.md` §4.4 —— 规范字节稳定性不再表述为"由测试锁定"并指向
  `tests/test_voice_table.py`，改为"由**固定向量**锁定（给定行字段 → 期望字节串 → 期望 hash
  前若干位），Python 与 Rust 两侧共用同一批向量"。
- `docs/voice-batch-m2-spec.md` —— ① §4 参考实现说明去掉 `tests/test_voice_table.py` 路径；
  ② M2 验收清单第 8 条原为"全量门禁（19 模块 + vtcore 测试模块）全绿，ruff 0，CRLF 审计 0，
  `MODIFICATION_NOTICE.md` 已登记"（内部流程 + 过期数字），改为产品级表述：
  Python 侧封装（`.vt` 读写 / 只读锁 / 签名 / 信任库 / manifest）与 Rust 实现行为一致、接口可依赖。
- `app/services/tts_runner.py`（2 处）、`app/widgets/tts_params_panel.py`（1 处）—— 去掉指向
  `docs/tts-spike-report.md` 的引用（该报告不随源码分发），技术说明与契约内容原样保留。

#### 2 · 为什么清理

公开分发的那份（`release/public` 分支）不含开发过程文档：`docs/tts-spike-report.md`、
`docs/development-notes.md`、`tests/`、`tools/run_gate.ps1` 均不在其中。于是上述措辞要么
暴露内部开发环境（沙箱 / 内部门禁脚本 / 开发机），要么**指向公开副本里并不存在的文件**
（悬空引用）。清理后公开面自洽：读者不需要任何内部上下文即可读懂这些说明。

#### 3 · 边界

- **纯文案**：不改逻辑、接口、常量、规格数值；`vtcore/README.md` 移除的两条测试指引属开发侧
  信息，不影响使用者构建与运行。
- `docs/voice-batch-m2-spec.md` 是**冻结规范**：本次只改 §4 的一句说明与验收清单第 8 条
  （均为非约束性的过程表述），**未触碰 §2–§9 的任何字节级规定**。

验收（2026-09-22 19:58）：`temp\ps_gate.ps1` **25 模块全绿 / 343 用例**（无 flake）；ruff 0 项；
`compileall` 通过；行尾合规（唯一例外 `vtcore/Cargo.lock`，已登记）。
公开面复扫：`release/public` 重建后确认无 沙箱 / 门禁 / `ps_gate` / 指向 `tests/` 与
`docs/tts-spike-report.md` 的悬空引用。

### 追加登记（2026-09-22 · 工作格式改取「乙」：TTS 模块只认 `.vt`）

#### 1 · 决策变更

冻结决策第 7 条由「**甲**」（JSON 为可编辑工作格式、`.vt` 为导出成品）改为「**乙**」：
**`.vt` 是唯一工程格式** —— 未签名即可编辑（自动保存原地写回），已签名自动上锁为只读。
JSON 工程读写**整体移除**（维护者决策：不做一次性导入入口）。

#### 2 · 服务层

- `app/services/vt_project.py`
  - 新增 `table_to_document(table, *, seed_hex, created_at, generator)`：把语音表编码为容器文档
    （行按 M1 §4 规范字节；`seed_hex` 非空即签名），由原 `import_json_project` 的内联逻辑抽出；
  - 新增 `save_table(path, table, *, seed_hex, lock, allow_locked)`：语音表 → `.vt`，签名默认上锁；
  - **删除** `import_json_project()`（JSON 工程导入）；
  - `container_to_table()` 的旁车读取改走 `save_coordinator.read_state()`。
- `app/services/save_coordinator.py` 重写为"只编排、不写 JSON"
  - **删除** `project_dict` / `table_from_project_dict` / `write_project` / `read_project` /
    `UnsupportedProjectPath` / `DOC_KIND`；
  - 新增 `state_path(project)`（旁车命名：剥掉尾部 `.vt` 后追加 `.vt.state`）与
    `write_state()` / `read_state()`；
  - `SaveCoordinator` 增加可注入 `writer`，默认写入器写 `.vt` 容器 + 旁车；`save()` 的异常捕获补上
    `RuntimeError`（覆盖 `VtProjectError`，例如目标已上锁）。

#### 3 · 界面（`app/pages/voice_batch_page.py`）

- `open_project()` 只接受 `.vt`；`.json` 明确提示"本版本只支持 .vt 工程文件"（不再读取）；
- `_view_vt_container()` → `_open_vt_project()`：**未上锁即可编辑**（自动保存写回该容器），
  **已上锁（已签名）即只读**并保留锁徽章；
- 新增「更多 → 解锁以编辑」：解锁后原地转为可编辑工作文件，保存写出未签名容器（提示语如实说明）；
- 默认工作文件 `temp/voice-output/voice_project.json` → **`voice_project.vt`**；
- `export_vt()` 改用 `vt_project.save_table()`，去掉重复的文档拼装；
- i18n 新增 `voice.action.unlock_project` / `voice.open.vt_editable` / `voice.open.vt_readonly` /
  `voice.open.json_retired` / `voice.unlock.done` / `voice.unlock.failed`；删除 `voice.open.done` /
  `voice.open.vt_signed` / `voice.open.vt_unsigned`（中英各一条）。

#### 4 · 测试

- `tests/test_voice_save.py`：由"JSON 工程往返"改写为**旁车命名与往返 + 协调器**——命名规则
  （`proj.vt` → `proj.vt.state`，不再产生 `.vt.vt.state`）、缺失/损坏旁车降级、注入 writer 的修订号与
  防抖、失败信号、默认写入器产出未签名容器 + 旁车、**拒绝覆盖已签名工程**。
- `tests/test_vt_project.py`：`JsonImportTests` → `WorkFileRoundTripTests`（未签名写出、文档与参考实现
  一致、往返保持身份与内容、签名即上锁且拒绝覆盖、解锁后可写回、本体不含生成状态）。
- `tests/test_voice_batch.py`：打开/保存路由改为 `.vt`（未签名可编辑且改自动保存目标；已签名只读、
  解锁后转为可编辑；`.json` 提示不支持）、旁车命名断言，并**新增"编辑后自动保存写回 `.vt`"往返**。

#### 5 · 规格与文档

- `docs/voice-batch-m2-spec.md`：§10 由"与 M1 的迁移"改写为"工程格式"（甲乙变更 + JSON 已移除）；
  §8 只读锁改述（已签名才禁写，未签名即工作文件）；§8.3 旁车命名更正为剥尾 `.vt` 的写法。
- `docs/voice-batch-spec.md` §5：旁车命名规则与"只读约束"表述同步。
- `docs/development-notes.md` §7：冻结决策第 2、7 条更新。
- `docs/tts-workflow-guide.md` §5：面向用户改写（工程文件就是 `.vt`；导出＝另存；签名导出＝只读；
  解锁以编辑）。
- `.gitignore`：补 `*.vt` / `*.vt.state` / `*.vtmanifest`（此前只靠产物落在 `temp/` 才未被误提交）。

#### 6 · 边界与影响

- **旧 JSON 工程不再可读**：本版遇到 `.json` 只提示不支持；需用旧版本先导出 `.vt`。
- **行序规范化**：容器按 `row_id` 规范序存放行（规范字节要求顺序稳定），故保存后重新打开时行顺序
  按 `row_id` 排序——这是容器格式既有性质，非本轮引入。
- 签名语义不变：已签名自动上锁；`key_id` 不进 `spec_hash`；`.vt.state` 不签名、可随时删。

验收（2026-09-22 20:27）：`temp\ps_gate.ps1` **25 模块 / 347 用例全绿**；ruff 0 项；`compileall` 通过；
行尾合规（唯一例外 `vtcore/Cargo.lock`，已登记）。

### 追加登记（2026-09-22 · 修复轮 5：未构建 vtcore 的启动崩溃与后端误判；start.bat 获取扩展）

#### 1 · 缺陷（上一轮引入的回归）

「工作格式改取乙」把启动时的默认工程加载改成读 `.vt`，而该路径**没有 vtcore 守卫**，
于是"未构建扩展"的环境**启动即崩**：

```
AttributeError: module 'vtcore' has no attribute 'parse_container'
  main.py → MainWindow → VoiceBatchPage.__init__ → _load_existing_project → container_to_table
```

根因不止一处，逐条修掉：

1. **`import vtcore` 会命中仓库里的源码目录**：源码分发时 `vtcore/`（Rust crate 目录，无
   `__init__.py`）会被当成**隐式命名空间包**导入成功，于是
   ① `app/models/voice_table.py` 的 `HASH_BACKEND` 误判为 `vtcore`（界面 8 处守卫随之失效）；
   ② `vt_project._require_vtcore()` 只判 `None`，抛出的 `AttributeError` 不在捕获范围内 → 冒到启动层。
   **修复**：两处都改为**校验实际 API**（`canonical_row_bytes` / `parse_container`）——
   不可用时 `HASH_BACKEND` 回退 `python-reference`，`vt_project` 抛可捕获的 `vtcore_missing`。
2. **启动加载补守卫**：`_load_existing_project()` 增加 `HASH_BACKEND != "vtcore"` 早退（与其它入口一致）。
3. **"工程读写不可用"提示常驻化**：`_update_summary()` 在无扩展时把提示并入状态栏文案
   （否则会被行数统计覆盖，用户根本看不到）。
4. **保存失败此前一直静默**（既有缺口）：`SaveCoordinator.failed` 从未接线；现接入
   `_on_save_failed()`，显示「工程保存失败：<错误码>」。

#### 2 · `start.bat`：新增 vtcore 扩展获取（GBK 字节级补丁）

- [1/3] 新增 `NEED_VTCORE` 探测：**按 API 判定**（`hasattr(vtcore,'parse_container')`），而非仅 import；
- [2/3] venv 就绪后调用新子过程 `:fetch_vtcore`：从本 fork 的 GitHub Release 下载预编译 **abi3
  wheel**（`vtcore-0.1.0-cp312-abi3-win_amd64.whl`）→ `pip install --no-deps --force-reinstall` →
  复验 API；**失败只提示、不阻塞启动**（应用仍可运行，只是工程读写不可用）。
- ⚠️ 该下载地址**需先发布 Release 资产才生效**（当前尚未发布；失败路径会给出本地构建指引
  `maturin develop --release`）。
- 补丁方式：`temp/patch_start_bat_vtcore.py`（GBK 解码 → 锚点唯一性校验 → 插入 → GBK 写回）。
  不变量复检：GBK 可解码 / UTF-8 不可解码 / 无 BOM / **CRLF 增量 == 新增行数（227→285）** /
  无裸 LF 与裸 CR / 无 `chcp`；幂等（重复执行输出 SKIP）。

#### 3 · 实证（可复跑）

- `temp/verify_no_vtcore_startup.py`：用**没有扩展的 venv** 跑修复后代码（且默认 `.vt` 工作文件存在）
  → 页面构造成功、`HASH_BACKEND=python-reference`、状态栏常驻提示、导出按钮禁用；对照组（有扩展）
  → `HASH_BACKEND=vtcore`、正常载入工程行。
- `temp/smoke_start_bat_vtcore.py`：抽出 `:fetch_vtcore` 单独调用 → 早退分支正确
  （`probe-errorlevel=1`）；探测语句在主仓 venv 返回 0、在未构建扩展的 venv 返回 1。

#### 4 · 边界

- 无扩展时**工程读写整体不可用**（`.vt` 的唯一解释器是 vtcore）。本轮取舍是"提示清楚 + 绝不崩"，
  扩展获取交给 `start.bat`；Release 资产发布前该下载路径必然失败（属预期）。
- 决策 8（不做 EXE 打包）由此重新成立：未构建 vtcore 也能**启动并正常使用其它功能**。

验收（2026-09-22 21:16）：`temp\ps_gate.ps1` **25 模块 / 347 用例全绿**；ruff 0 项；`compileall` 通过；
行尾合规（唯一例外 `vtcore/Cargo.lock`）；`start.bat` GBK / CRLF / 无 `chcp` 不变量通过。

### 追加登记（2026-09-22 · vtcore 预编译扩展随源码附带；start.bat 本地件优先）

#### 1 · 新增：预编译扩展（免 Rust 工具链即可用）

- `vtcore/wheels/vtcore-0.1.0-cp312-abi3-win_amd64.whl` —— 由本仓库的 `vtcore` 源码构建的
  **abi3 wheel**（跨 CPython 3.12+ 通用，仅 Windows x64），**293,321 字节**，
  sha256 `F72F184E7A73BCC9B2937110CC0C4111CC4DD1E923EAE5305E540BC4D7404F44`。随源码分发，`start.bat` 会自动安装，使用者**无需 Rust 工具链、无需联网**。
- 支撑工具（新增，随源码分发）：`tools/check_wheel_leaks.py`（残留检查）、
  `tools/sanitize_wheel.py`（中和 SBOM 绝对路径 + 重建 `RECORD`）、
  `tools/view_gbk_bat.py`（把 GBK bat 转 UTF-8 以便阅读）。

#### 2 · 构建纪律（**重要，踩过**）

直接 `maturin build` 得到的 wheel **会把构建机痕迹烤进去**，不能入库/发布：

- `vtcore/vtcore.pyd` 内含 **16 条依赖 crate 的 panic 位置字符串**
  （`<users-dir>\<用户名>\.cargo\registry\…\pyo3-0.29.2\src\…`）——`--strip` 去不掉，
  必须 `RUSTFLAGS=--remap-path-prefix=<cargo 目录>=/cargo --remap-path-prefix=<仓库根>=/src`
  ——**目标必须是 POSIX 风格**：写成 `C:\cargo` 会在 `.pyd` 里留下"盘符绝对路径"形状，
  被 `tools/check_wheel_leaks.py` 的形状规则判为 FAIL；
- maturin 的 SBOM（`dist-info/sboms/*.cyclonedx.json`）含项目绝对路径
  （`path+file:///<项目目录>/vtcore`）——由 `tools/sanitize_wheel.py` 归一为 `<包名>#<版本>`
  （不再含任何路径形状，且换构建机产出一致）并重建 `RECORD`。

完整命令见 `docs/development-notes.md` §4.2；`vtcore/README.md` 新增「预编译扩展（随源码附带）」一节。

#### 3 · `start.bat`：本地件优先、Release 兜底（GBK 字节级补丁 2）

- `:fetch_vtcore` 先看 `vtcore\wheels\<同名 wheel>`：存在即安装并 `goto :vtcore_install`；
  缺失才走 Release 下载（资产尚未发布，该路径优雅失败）。
- 不变量复检：GBK / 无 BOM / **CRLF 增量 == 新增行数（285→293）** / 无裸 LF·CR / 无 `chcp`；幂等。

#### 4 · 文档

- `docs/development-notes.md` §4.2：补"**按 API 判定**而非 import"的教训、预编译件路径与构建去痕迹流程；
  新增 **§6.6「删除/清理文件前先备份」**（`Remove-Item` 不进回收站；曾因此误删非测试产物）。
- `vtcore/README.md`：新增「预编译扩展（随源码附带）」一节（使用者视角：不需要工具链/网络）。

#### 5 · 边界与未做

- **Release 资产未发布**（按指示本轮不推送）：`start.bat` 里的 Release 兜底地址当前必然 404，
  本地件优先已覆盖实际使用场景；将来发布时用同一文件名即可直接生效。
- wheel **只覆盖 Windows x64 + CPython ≥ 3.12**（abi3）；其它平台仍需自行构建。
- 已核实：fork 与上游**均无**可用的 vtcore 预编译件（上游 release 只有整包 ZIP）；GitHub Packages
  不支持 PyPI，故只能随源码附带或走 Release 资产。

验收（2026-09-22 21:4x）：`tools/check_wheel_leaks.py` 对入库 wheel **PASS**（无构建机路径/用户名）；
该 wheel 在独立 venv 实测安装 + 导入成功（`parse_container` / `encode_container` / `canonical_row_bytes`
齐全，`pip check` 干净）；`temp\ps_gate.ps1` 25 模块 / 347 用例全绿；ruff 0 项；`compileall` 通过；
行尾合规；`start.bat` 不变量通过。

#### 6 · 同轮追加：彻底的路径清查、工具去痕与版本号规则

1. **SBOM 归一化更彻底**：`tools/sanitize_wheel.py` 改为通用正则归一
   （`path+file:///<任意绝对路径>/<包名>#<版本>` → `<包名>#<版本>`），不再硬编码本机路径，
   且**换构建机产出一致**。入库 wheel 已按新逻辑重新中和：**293,321 字节**，
   sha256 `F72F184E7A73BCC9B2937110CC0C4111CC4DD1E923EAE5305E540BC4D7404F44`，
   `tools/check_wheel_leaks.py` **PASS**。
   （此前那版残留 `…/WT-NameRelay/` 的路径形状 —— 正是本轮新增的检查器抓出来的。）
2. **构建期 remap 也归一为 POSIX 风格**：检查器新增"形状"规则（任何 `X:\…` 即 FAIL）后，
   发现 `.pyd` 里仍留着 `C:\cargo\registry\…`（上一版 remap 的目标是 `C:\cargo`）。
   已改用 `--remap-path-prefix=…=/cargo` 与 `…=/src` 重建 —— 现在 wheel 里**不含任何盘符路径**。
2. **工具自身的痕迹**：`tools/view_gbk_bat.py` 曾把本机绝对路径写进默认参数（**真泄漏**，
   已改为仓库相对路径 + 默认输出到 stdout）；`tools/sanitize_wheel.py` 的 docstring 亦含真实项目路径
   （已改占位式 `<项目目录>`）；`MODIFICATION_NOTICE.md` 同处一并改为占位式。
3. **发布前把关流程**：新增 `temp/sweep_abs_paths.py`（按"路径形状"清查全仓库，报告按
   "是否会进公开分支"分类，落 `temp/sweep_result.txt`）；`docs/development-notes.md` 新增 §2.6。
4. **版本号规则**（`docs/development-notes.md` §2.5）：
   `FORK_VERSION = rc-<上游主版本>.<上游次版本>.<当前分支提交数 − 30>`
   —— 当前提交数 **102** ⇒ **`rc-0.2.72`**。已同步三处：`app/branding.py`（`FORK_VERSION`）、
   `windows_version_info.txt`（`filevers/prodvers=(0,2,72,0)`、`FileVersion='0.2.72.0'`、
   `ProductVersion='rc-0.2.72'`）、以及展示位（「关于与许可」页脚 + 启动日志
   `Application startup (rc-0.2.72)`）。

验收（2026-09-22 22:04）：清查报告——公开面命中 0（`temp/sweep_abs_paths.py HEAD` 在修正后仅剩
"模式定义处"与上游许可证原文两类，均已在 §2.6 说明并排除）；wheel 检查 PASS；版本号自查
`rc-0.2.72 == rc-0.2.(102−30)` 通过；ruff 0 项；`compileall` 通过；行尾合规。

### 追加登记（2026-09-23 · 语音工作台：参考音频选择 + GSV 微调模型选择）

#### 1 · 参考音频选择（GPT-SoVITS 与 CosyVoice 两条链路共用）

- 现状与缺口：每行的「音色」列（`VoiceRow.voice`）本就是两个后端的参考音频来源
  （GSV `api_v2` 的 `ref_audio_path`、CosyVoice shim 的 `voice` 参数），但此前只能
  手敲路径。现给该列换上带「…」按钮的编辑器 `VoicePathEditor`
  （`app/widgets/voice_table_model.py`），点击弹音频文件对话框
  （wav/mp3/flac/ogg/m4a），选定即提交；仍可手输/粘贴路径。
- **编辑器用容器（QWidget）而不是 QLineEdit 本身**：模态文件对话框会把焦点从行编辑器
  夺走，QLineEdit 的 `editingFinished` 随之触发、被视图当成"提交并关闭编辑器"，
  会出现"对话框还没开编辑器就没了"；容器编辑器没有该自动提交接线，按钮焦点策略为
  NoFocus，提交时机由委托（`createEditor`/`setEditorData`/`setModelData` 覆盖 +
  `commitData`）控制。
- 提示文案同步改写（`voice.table.hint`），并顺手修正其中**过期的 `.json` 工程导入提法**
  （工作格式取「乙」后 `.json` 已不再支持）。

#### 2 · GSV 推理微调模型选择（训练产物 → 推理面板）

- 新增纯逻辑 `tts_training.discover_finetuned_weights(repo)`：按实验归并训练产物，
  覆盖两个落点——`logs/<实验名>/`（epoch 检查点，含 `logs_s2_*` 子目录）与仓库根
  `GPT_weights*` / `SoVITS_weights*`（savee 另存的最终权重，实验名从文件名解析，
  模式对应 `s1_train.py:75` 与 `s2_train.py:569` 的写盘格式）；同一实验各取修改时间
  最新的 GPT(.ckpt) 与 SoVITS(.pth)，不完整时在展示名上标注「（缺GPT/SoVITS）」。
- 工作台推理栏权重区重构：`微调模型 [下拉] [扫描] [应用权重] + 两个路径输入框`。
  下拉选中即回填两条路径（**不自动切换**，仍需显式点「应用权重」走 api_v2 热切换，
  该调用是阻塞 HTTP、依旧走工作线程）；切换到 GPT 后端时自动扫描一次；
  微调训练完成（`weights_discovered`）后也刷新下拉。
- 训练面板的训练后回填（`_discover_trained_weights`）改用同一发现函数——顺带把
  根权重目录里的最终权重也纳入回填范围（此前只扫 `logs/<exp>`）。
- 已知边界：发现函数只认上述两个落点的文件名约定；实验名解析不出的根目录文件按
  文件名列归档，不强行猜测。

#### 3 · 其他

- 仓库外开发根的 `AGENTS.md` 新增约定：**尽可能不使用 Windows PowerShell**，
  复杂命令写成 Python 脚本或 `.ps1` 文件执行，避免命令行内联转义地狱。
- **修复既有缺陷（深度检查发现）**：`CosyVoiceGgufBackend` 沿用默认 `build_payload`
  把参数嵌在 `"params"` 里，而 shim 只读**顶层**字段——面板承诺的「固定随机种子」
  从未真正到达后端（静默丢弃）。现重写其 `build_payload` 摊平参数（`seed` 上提）；
  同步修正 `test_tts_runner` 锁死旧契约的断言并新增 seed 用例。
- **接口契约全量对审（2026-09-23 深查）**：GUI → 载荷 → 后端逐字段核对。
  - GSV：载荷 12 字段与 vendored `api_v2.py` `/tts` 全部对上（必需项 `text_lang`/
    `prompt_lang` 由面板与行语言兜底，恒非空）；**新发现缺口**——`ref_audio_path`
    是硬要求（api_v2.py:314 空值 400），此前空值只会得到不透明的"HTTP 400"。
    现由 `GptSovitsBackend.requires_reference_audio` 标记契约，工作台发送前预检：
    空参考音频的行以 `reference_missing` 可读失败（状态徽章 tooltip 可见），
    不再发必败请求；`batch_size`/`aux_ref_audio_paths` 保持上游默认未暴露。
  - CosyVoice：shim 引擎对 `voice`/`seed`/`language` 均**逐请求**生效
    （`set_voice`/`set_tts_seed`/`set_target_language`，锁内串行），与客户端四字段
    一一对应；`speed`/`prompt_text` 面板对 Cosy 正确隐藏（shim 不支持，诚实化）。
- **i18n 全键位扫描（新增 `temp/i18n_key_sweep.py`，640 键）**：修复两处——
  `w.089` 英文为**空串**（`tr()` 对空串回落中文，英文界面会露出" 个"），补为空格
  尾缀；`voice.params.title` 被 `TtsParamsPanel` 构造函数引用但**键不存在**（标题恰
  被 `set_backend_kind` 立即覆盖、从未暴露），改为构造时不设标题。另通报一批
  字面量未引用的遗留键（w.*/ui.* 等，动态家族已排除；是否清理由维护者定夺）。
- **使用者文档同步**：`docs/tts-workflow-guide.md`（随发布分支分发）补上新 UI 的
  作业描述——「音色」列的「…」选择器与空值预检提示、「微调模型」下拉与扫描、
  推理参数中的参考音频文本/语言两行。
- **其它核验（无问题）**：Rust 侧 `cargo test` 39 例全过；`git fsck` 仅历史悬空
  对象（amend 遗留，无损坏）；模型选择页无需同步。
- **常驻参考音频入口（维护者反馈"前端看不到上传处"后补强）**：此前的选择能力
  藏在「音色」列双击编辑态里，可发现性为零。现于生成按钮正下方新增常驻控件行：
  `参考音频 [当前路径] [上传参考音频…] [应用到所有行] [清除该行]`——上传即写入
  选中行（未选中行则应用到全部行），显示框随选中行联动；「音色」列编辑器保留
  作每行覆盖。4 例新测试（选中应用/无选中全应用/批量与清除/联动与取消）；
  测试页保存目标隔离到临时目录（防抖定时器可能跨测试触发，不得写用户默认工作文件）。
- **GUI 风格统一审计（2026-09-23，全页面实拍）**：真实窗口逐页截图比对（新增
  `temp/visual_sweep_pages.py`，主页/模型选择/语音工作台/语音处理/文件复制/无线电/
  Bank/车组 8 页 + 浅色主题抽检）。结论：新控件（参考音频行、微调模型下拉）与
  既有按钮/输入/下拉/表格样式完全一致（类级 QSS + Fusion 调色板），深浅两主题均适配。
  顺手修正：右上提示文案以常驻「参考音频」行为主（原文案还在教双击音色列的旧路径）；
  参考音频显示框占位缩短为「未设置」（长文案移入 tooltip，避免截断）。
  另记录一处**既有**差异待定夺：Bank 页把「手动复制」标题放在玻璃面板内（白 18px），
  与 Crew/Radio 的强调色 20px 分区标题不一致（非本轮改动引入）。
- **CosyVoice 3 真实推理首次实跑（2026-09-23 深查）**——交接 §六.1 的首次真实验证：
  - **打通**：shim（应用 venv 解释器）+ CrispASR 0.8.34 + q4 权重，首次合成 58s
    （含模型加载），产出 24 kHz 真实中文语音 WAV；/health、错误通道、懒加载均正常。
  - **修复 shim 真缺陷**：`os.add_dll_directory` 不接受相对路径（WinError 87），
    按 docstring 示例用相对路径手动启动必炸；`CrispAsrEngine.__init__` 现统一
    `resolve()`（应用的 launcher 一直传绝对路径，线上未受影响）。
  - **已知边界（上游，不修）**：`set_voice` 在实测所有路径下（启动时 / 逐请求、
    真实语音、16k/24k）一律 `rc=-2` 被拒——该模型的参考音频音色克隆当前不可用，
    指定参考音频的行会失败（默认音色不受影响）；已写入使用者指南 FAQ。
  - **实测修正文档**：同种子两次合成**字节不一致**（GGUF 多线程采样固有非确定性），
    指南中"完全相同"的强断言已软化为"整体听感稳定"。
  - **客户端错误透传**：`HttpWavBackend` 此前丢弃 HTTP 错误响应体（GSV 的
    "ref_audio_path is required"、shim 的 `engine_error` 诊断全都不可见），现提取
    `message` 附加到行错误文案；新增对应单测。

验收（2026-09-23 00:0x）：`temp/ps_gate.ps1` **25 模块全绿（voice_batch 45→55 用例，
新增发现/下拉/编辑器 10 例）**；ruff 0 项；`compileall` 通过；`git ls-files --eol` 行尾合规
（唯一例外 `vtcore/Cargo.lock` 照旧）。

### 追加登记（2026-09-24 · 随包 FFmpeg 改自建 LGPL 构建；版本基线重置为 `rc-0.0.02`）

#### 1 · 缺陷：随包件名为 LGPL，实含 GPL 组件

原随包件取自 BtbN FFmpeg-Builds 的 `win64-lgpl-shared`，但其 `avformat-63.dll` 经
chromaprint（`-DFFT_LIB=fftw3`）**静态链入了 FFTW 3.3.11（GPL-2.0-or-later）**，
该 DLL 须整体按 GPL-3.0 对待，与 README 与界面所标的 LGPL-3.0-or-later 不符。
根因在上游构建脚本缺闸门：`scripts.d/25-fftw3.sh` 的 `ffbuild_enabled()` 是裸
`return 0`，`scripts.d/50-chromaprint.sh` 只判断 FFmpeg 版本（对照 `50-x264.sh` 有
`[[ $VARIANT == lgpl* ]] && return -1`），而 BtbN README 明示 lgpl 变体
"Lacking libraries that are GPL-only"。

#### 2 · 处置：自建最小 LGPL 构建并换件

- 源码锁定 `fe953596e9f53e3d61c465bce7a29834cae3375b`（与原随包件同一 commit，
  DLL 主版本号不变，不牵动 spec、打包与文档里的名字）。
- configure 仅下列开关：`--enable-version3 --enable-shared --disable-static
  --disable-autodetect --disable-network --disable-doc --disable-debug --disable-ffplay
  --enable-libmp3lame --enable-libopus --enable-zlib`；**无** `--enable-chromaprint`、
  **无** `--enable-gpl`、**无** `--enable-nonfree`。
- 构建前缀归一为中性路径 `/ffbuild/ffmpeg-lgpl`，二进制内嵌的 `FFMPEG_CONFIGURATION`
  不再带构建机目录。
- 随包件 10 → 13 个（增 `libgcc_s_seh-1.dll`、`libwinpthread-1.dll`、`libmp3lame-0.dll`、
  `libopus-0.dll`；去 `ffplay.exe`），体量约 145 MB → 30.6 MB。
- 新增 `tools/audit_ffmpeg_license.py`（挖掉 configure 行后按组件特征扫描，再与界面
  声明的许可标签对拍）、`tools/verify_ffmpeg_licenses.py`（许可文本哈希）、
  `tests/test_ffmpeg_license.py`（换件绊线）、`tools/ffmpeg-build/`（可复现构建脚本）、
  `licenses/ffmpeg/`（组件许可正文与清单）。
- 功能等价逐项核对：程序只用 PCM 编码器、内置滤镜、`wav` muxer、`-f lavfi`
  （libavdevice 的 lavfi indev）与 ffprobe，chromaprint 从未被引用，换件不损失现有能力。

#### 3 · 发布面与版本基线

- 二进制许可审计脚本 docstring 里遗留的构建机路径改写为占位符 `<构建机工作目录>`。
- `FORK_VERSION` 重置基线由 `rc-0.0.01` 改为 **`rc-0.0.02`**，同步
  `windows_version_info.txt`（数值形式 `0.0.2.0` 与 `ProductVersion`）。

验收（2026-09-24）：`tools/run_gate.ps1` **26 模块全绿**；`tools/audit_ffmpeg_license.py`
PASS（GPL-only 指纹 0 命中）；`tools/verify_ffmpeg_licenses.py` 7/7 一致；`compileall` 通过；
两个工作区 `git ls-files --eol` 无 `w/mixed`；随包件自报版本 `N-125829-gfe953596e9`、
内嵌前缀 `/ffbuild/ffmpeg-lgpl`。
