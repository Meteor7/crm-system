# 对抗性审查报告 — Semiconductor CRM (Semicore / QIHENG Demo CRM)

**审查范围：** 前端 `src/`（256 源文件）+ Frappe 后端 `backend/apps/rayher_crm`（~179 文件）
**审查方法：** 主线程逐行复核关键路径 + 4 个并行子代理分别从【前端安全 / 业务正确性 / 代码质量与测试 / 后端安全】通读源码，再交叉验证每条发现
**基线验证：** `pnpm typecheck` ✅ 通过 · `pnpm test` ✅ 102 文件 / 659 用例通过 · `pnpm build` ✅ 通过

---

## 执行摘要

这是一个**工程质量显著高于普通 MVP** 的项目。安全、并发、权限、金额计算的实现接近生产级：乐观锁在每一次完整更新上都用 `SELECT … FOR UPDATE` + `modified` 时间戳强制执行；上传做 magic-byte 校验 + zip-bomb/zip-slip 防护 + ClamAV fail-closed；密码修改校验当前密码且只作用于 `frappe.session.user`；SQL 全部参数化；session cookie 设为浏览器会话级；错误边界统一把内部异常收敛为 12 个公开错误码且不泄露堆栈。

**本次对抗性审查未发现 Critical 级别问题。** 发现的实质问题集中在三类：

1. **一个真实 DoS 向量**——Demo Request 表单导入的 DOCX 解析路径**绕过**了项目自己为其他上传精心实现的 zip-bomb / ClamAV 防护。
2. **一个真实的 PDF 注入**——报价单 PDF 的 Jinja 模板未转义用户可控字段，可被写入客户可见的发布产物。
3. **可维护性 / 可观测性**——mock adapter（~2850 行）在客户端重实现了整套后端业务规则，却无任何"mock ↔ Frappe 行为一致性"的契约测试；后端测试在本仓库内无可见门禁；金额聚合无上界保护。

下表为按严重度排序的全部**已主线程复核确认**的发现。

| # | 严重度 | 标题 | 类别 |
|---|---|---|---|
| F1 | 🟠 Medium | DOCX 导入路径 zip-bomb → worker OOM（认证后 DoS） | 后端安全 |
| F2 | 🟠 Medium | 报价单 PDF 模板未转义 Jinja（HTML/可能 JS 注入到客户产物） | 后端安全 |
| F3 | 🟠 Medium | `import_form` 跳过 magic-byte + ClamAV + 扩展名一致性校验 | 后端安全 |
| F4 | 🟠 Medium | append 类操作的乐观锁可被绕过（`expected_modified` 可选且部分端点从不校验） | 并发正确性 |
| F5 | 🔴 High* | `addMoney`/`fromCents` 聚合结果可静默超出 DECIMAL(20,2)（*前端逻辑，已执行验证） | 金额正确性 |
| F6 | 🟠 Medium | mock 与 Frappe 之间无行为一致性契约测试（"测试全绿、生产报错"风险） | 测试/质量 |
| F7 | 🟠 Medium | 后端 pytest 在本仓库内无可见的运行/门禁入口 | CI/质量 |
| F8 | 🟡 Low-Med | `transition_demo_request` 自转移会重置"停滞"计时并污染历史（非幂等写） | 状态机 |
| F9 | 🟡 Low | `getDemoIdentity` 未知 id 静默回退到演示员工170（demo 模式权限升级隐患） | 安全 |
| F10 | 🟡 Low | 销售可硬删 Site（账户删除仅限 Manager），被引用时返回模糊 500 | 权限一致性 |
| F11 | 🟡 Low | bootstrap 向任意已认证用户下发全员目录（含 `user.bio`） | 隐私 |
| F12 | 🟡 Low | 受控文档元数据（含 SHA-256 校验和/文件名）对 Restricted 文档也全量返回 | 隐私 |
| F13 | 🟡 Low | `get_bootstrap` / `get_health` 缺 `@api_endpoint`（异常时不走统一信封） | 错误处理 |
| F14 | 🟡 Low | `weightedMoney`/`readAllPages` 等边界缺测试；`money.test.ts` 仅 4 例（happy-path） | 测试覆盖 |
| F15 | 🟡 Low | 时区硬编码 `Asia/Shanghai`；`contracts` 中 `days===0` 显示"0 天内"、非法日期静默归 normal | 边界/可移植 |
| F16 | 🟡 Low | 仓库卫生：187KB 原型 HTML、31KB 调研 MD、`_archive/`、`.codex-docker-config/` 未忽略 | 治理 |

---

## 详细发现

### 🟠 F1 — DOCX 导入路径 zip-bomb → worker OOM（认证后 DoS）
- **位置：** `backend/.../services/demo_request_imports.py:109-125`（`_docx_tables`）经由 `api/v1/demo_requests.py:28-49`（`import_form`）
- **证据：**
  ```python
  with ZipFile(BytesIO(content)) as archive:
      document = archive.read("word/document.xml")   # 无解压尺寸上限、无条目数上限
  ...
  root = ElementTree.fromstring(document)            # 整段 XML 一次性物化进内存
  ```
  唯一的上限是压缩后 `MAX_FILE_BYTES = 10 MiB`（`:12`、`:235`）。但 DEFLATE 可把 10 MiB 的 `document.xml` 膨胀约 1000× 至数 GB。
- **对比：** 项目自己的 `file_security._docx_is_valid` 对**其他** DOCX 路径实现了 `MAX_DOCX_ENTRIES=500`、`MAX_DOCX_UNCOMPRESSED_BYTES=50 MiB`、拒绝加密条目与 zip-slip。**唯独这条导入路径全部绕过**——两位独立审查者同时命中此处。
- **攻击场景：** 任一 Sales/Manager 用户向 `import_form` POST 一个 zip-bomb `.docx`，Frappe web worker 解压 XML 时被 OOM-kill；反复请求即可拖垮整个应用。
- **建议：** 在 `archive.read` 前用 `ZipInfo.file_size` 上限校验（直接复用 `file_security.MAX_DOCX_UNCOMPRESSED_BYTES`），改为流式解析而非 `ElementTree.fromstring(整段)`；PDF 路径 `_pdf_text` 同理应加上限页数（pypdf 无内置上限）。

### 🟠 F2 — 报价单 PDF 模板未转义 Jinja（HTML/JS 注入到客户可见产物）
- **位置：** `backend/.../templates/quotation/quotation.html:59-116` + `services/quotations.py:42-49,407-411`
- **证据：** 模板里大量 `{{ customerName }}`、`{{ addressText }}`、`{{ attentionName }}`、`{{ attentionPhone }}`、`{{ item.name }}`、`{{ item.model }}`、`{{ item.description }}`、`{{ group.name }}`、`{{ group.model }}`、`{{ seller }}`、`{{ opportunityTitle }}` **均为裸插值，无 `|e`/`|safe` 之外的转义**。这些字段来自 `_text`/`_bounded_text`——**只做 `.strip()` + 长度上限，无任何 HTML 清洗**。Frappe 的 `render_template`（print format）默认**不自动转义**。
- **攻击场景：** Sales 用户在自管理的报价单里写入 `<script>`/`<img onerror>`/恶意 CSS，渲染进**发布给客户**的 PDF。金额仍由后端 `quotation_rules.calculate_totals` 计算（无法通过模板造假金额），但可演示员工106/污损正式报价；若 PDF 引擎（wkhtmltopdf）在渲染时执行 JS，还存在 SSRF/RCE 的有界风险。
- **建议：** 对所有自由文本插值加 `|e`（Jinja autoescape），或在 `_validated_values` 写入时做 HTML 编码；固定文案保留原样。

### 🟠 F3 — `import_form` 跳过统一的上传安全校验
- **位置：** `backend/.../services/demo_request_imports.py:229-243`
- **证据：** 仅按文件名后缀（`.docx`/`.pdf`）分发，**无** `file_security.validate_and_scan`、无 magic-byte、无扩展名↔MIME 一致性校验。`contact_files`/`demo_artifacts`/`demo_reports`/`document_uploads` 都演示员工174 `validate_and_scan`。
- **影响：** 内容只解析不持久化（无存储型 RCE/XSS），但破坏了"所有上传统一过安全门"的不变量，且与 F1 叠加放大 DoS。
- **建议：** 把 `import_form` 也接入 `validate_and_scan`（至少 magic-byte + ClamAV）。

### 🟠 F4 — append 类操作的乐观锁可被绕过
- **位置：** `backend/.../services/demo_requests.py:490-491`、`evaluations.add_evaluation_run`、`evaluations.set_evaluation_test_run_deadline`、`quotations.create_version`
- **证据：**
  ```python
  doc = lock_document("CRM Demo Request", name, expected_modified, "NOT_FOUND") \
      if expected_modified is not None else _lock_demo_request(name)
  ```
  `_lock_demo_request`（`:417-423`）只 `SELECT … FOR UPDATE`，**不比对 `modified`**。而 `add_evaluation_run` 等端点**从不**传 `expected_modified`，也从不做版本校验。
- **影响：** 行锁仍能串行化请求（不会产生脏写崩溃），但"并发编辑被静默覆盖"的真乐观锁语义在这些端点上失效。README"controlled status progression / 乐观锁"的承诺不一致。
- **建议：** 让所有 state-changing 端点强制 `expected_modified`，统一走 `lock_document`；前端 `addEvaluationRun` 等也应回传 `expectedModified`。

### 🔴 F5 — `addMoney`/`fromCents` 聚合可静默超出 DECIMAL(20,2)
- **位置：** `src/domain/money.ts:11-22`，经 `src/domain/dashboard.ts` 注入 Open/Weighted Pipeline、漏斗、负责人业绩
- **证据（子代理已用 Node 执行验证）：**
  ```
  addMoney(['999999999999999999.99', '0.01'])        → "1000000000000000000.00"   // 19 位整数
  addMoney(['999999999999999999.99','999999999999999999.99']) → "1999999999999999999.98"
  ```
  输入正则 `DECIMAL_20_2` 限制了**单笔**输入（≤18 位整数），但 `fromCents` 只校验非负，不校验上界。求和/加权结果可超过 DECIMAL(20,2) 上限 `999999999999999999.99`，写入 MariaDB 时被截断或报错。
- **建议：** `fromCents` 末尾加 `if (value > 99999999999999999999n) throw` 守卫，并补一条位于上限的回归用例。

### 🟠 F6 — mock 与 Frappe 之间无行为一致性契约
- **位置：** `src/api/mock-adapter.ts`（~2850 行，含权限/状态机/乐观锁/校验的完整客户端实现）vs `src/api/frappe-adapter.ts`（462 行，纯 transport，**零业务校验**）
- **证据：** 659 个前端用例的压倒性多数跑在 mock 上；`frappe-adapter.test.ts` 只断言 transport 形状（URL/form 字段/CSRF/multipart/错误信封）。名为 contract 的测试（`list-pagination-contract`、`notification-contract`、`quotation-contract`）全部只调 `createMockApi()` 或纯函数，**没有**任何用例把同一输入同时灌进 mock 与 Frappe 比对。
- **影响：** 一条 mock 强制但 Frappe 缺失（或反之）的规则——例如 mock 的 `BOOKING_SOURCE_INVALID`、上传扩展名过滤——CI 永远全绿却与生产不符。
- **建议：** 增加一份 `CrmApi` 契约一致性套件，用同一张 `(方法, 输入) → 期望输出/错误码` 表分别驱动 mock 与一个 Frappe 测试 fixture；或把校验下沉到后端单一真源、mock 收窄为纯数据返回。

### 🟠 F7 — 后端 pytest 在本仓库内无可见门禁
- **位置：** `package.json` 仅有前端 `typecheck`/`test`/`build`；后端 `tests/test_*.py`（20+ 文件，内容扎实）存在但无 `pnpm` 脚本或可见 CI 纳入同一质量门。
- **影响：** 后端是权限/并发/状态机的**权威实现**，恰恰最需持续回归；不随 PR 跑则 F6 漂移被放大。
- **建议：** 增加 `pnpm test:backend`（bench run-tests 或 docker compose 起 MariaDB+Frappe 跑 pytest），纳入必过门。

### 🟡 F8 — `transition_demo_request` 自转移非幂等，重置"停滞"计时
- **位置：** `src/domain/evaluations.ts:57-63` + `mock-adapter.ts:1965-1970`
- **证据：** `evaluationStatusOptions` 永远把 `current` 列为合法目标，故对已 `Testing` 的记录再 `updateEvaluationStatus(id,{status:'Testing'})` 会通过校验、`markProgress` 把 `lastProgressAt` 刷成 now、并追加历史——反复"推进到同状态"会清掉 ≥5 天的 `stalled` 标志并污染历史。
- **建议：** 拒绝 `command.status === evaluation.status`，或对同状态做真正 no-op（跳过 `markProgress`）。

### 🟡 F9 — `getDemoIdentity` 未知 id 静默回退演示员工170
- **位置：** `src/demo/identities.ts:27-29`（`?? DEMO_IDENTITIES[0]`，即 Manager 演示员工24/administrator）；`identities.test.ts:26` 把该行为固化。
- **影响：** demo 身份切换里一个拼错的 id 静默获得**全员权限**。仅 demo/test 路径（Frappe 模式下 `identity-switch.ts` 直接抛错），但属静默权限升级隐患。
- **建议：** 未知 id 直接抛错（对齐 `migrateLegacyUserId` 的 fail-loud）。

### 🟡 F10 — 销售可硬删 Site，而被引用时返回模糊 500
- **位置：** `backend/.../services/sites.py:112-124`（仅 `account:write`）vs `accounts.py:71-72`（账户删除限 Manager）
- **影响：** 销售可删除所辖账户的 Site 并静默解除 Contact 关联；若 Site 被 Opportunity/Booking/InstalledTool 引用，`LinkExistsError` 被 `api_endpoint` 转成通用 500。
- **建议：** 把 `delete_site` 对齐 Manager-only，或对在用 Site 返回干净的 `CONFLICT`。

### 🟡 F11 — bootstrap 全员目录披露
- **位置：** `backend/.../api/v1/bootstrap.py:33-60,78`
- **证据：** `_personnel_directory` 把**所有**启用且恰好持一个 CRM 角色的 System User 的 `id`（通常即登录邮箱）、姓名、角色、`team`（源自 `user.bio`）下发给任一已认证用户。
- **影响：** 内部 CRM 目录尚可接受，但 `bio` 可能含任意 HR 文本，且销售可枚举全部工程师/经理。
- **建议：** 确认此为有意设计；否则按角色裁剪可见字段，或剥离 `bio`。

### 🟡 F12 — 受控文档元数据对 Restricted 文档也全量返回
- **位置：** `backend/.../services/read_only_views.py:37-86`
- **证据：** `list_controlled_documents` 对所有 Released 文档（含 Restricted 保密级）返回 `content_hash`（checksum）、文件名、尺寸、版本，给任何 `account:view`（三角色皆有）的用户。**文件内容**分发仍由 `controlled_documents.render_controlled_document` 正确门禁，泄露的只是元数据。
- **建议：** 对未获批准请求的 Restricted 文档，脱敏 checksum/文件名。

### 🟡 F13 — `get_bootstrap`/`get_health` 缺 `@api_endpoint`
- **位置：** `backend/.../api/v1/bootstrap.py:63-64`、`health.py:11-12`
- **影响：** `get_bootstrap` 会调 `resolve_crm_role`，对 Guest/歧义角色抛 `frappe.PermissionError`；缺装饰器时不走统一 `{data,meta,warnings,error}` 信封，开发模式下可能吐原始堆栈。`get_health` 故意对 Guest 开放。
- **建议：** 给 `get_bootstrap` 加 `@api_endpoint`（`get_health` 保留 `allow_guest`）。

### 🟡 F14 — 边界测试缺失（`money`/`contracts`/`operations-rules`）
- **位置：** `src/domain/money.test.ts`（仅 4 例）、`contracts.test.ts`、`demo/operations-rules.test.ts`
- **证据：** `money.test.ts` 不覆盖负数、前导零、`"1.2"`vs`"1.20"`、概率 0/100/非整、DECIMAL(20,2) 上限——正是 F5 溜过的边界。`operations-rules` 的 `hasScheduleConflict` 不测跨午夜/畸形时间；`contracts.getContractRisk` 不测 `days===0`/非法日期。
- **建议：** 补表驱动边界用例。

### 🟡 F15 — 时区硬编码 + 演示员工116风险边界
- **位置：** `src/domain/demo-lifecycle.ts:6-18`（`Asia/Shanghai`）；`src/domain/contracts.ts:11-16`
- **证据：** `getContractRisk('2026-08-05','2026-08-05')` → `days:0`、band `'30d'`、label **"0 天内"**（语义不通）；带时间/偏移的非法 `endDate` → `NaN` → 静默归 `'normal'`。时区全仓硬编码北京（目标市场明确，大概率 by-design）。
- **建议：** 加 `days===0 → '今天到期'` 分支；校验 `endDate` 为纯 `YYYY-MM-DD`；若计划出海，把时区改为 bootstrap 下发的租户配置。

### 🟡 F16 — 仓库卫生
- **位置：** 根目录 `semiconductor-crm-demo.html`（187KB 原型，已确认无密钥、仅 mock 数据）、`Salesforce…调研-2026-07-29.md`（31KB）、`_archive/`（286 文件/2.3MB）、`.codex-docker-config/`（**未** gitignore）、`.codex-tmp/`（磁盘 435MB，已忽略）
- **建议：** `.gitignore` 追加 `_archive/`、`.codex-docker-config/`；原型 HTML/调研 MD 移出主仓库。

---

## ✅ 已验证健壮（多方交叉攻击未攻破）

| 领域 | 结论 |
|---|---|
| 乐观并发（完整更新类） | `concurrency.lock_document` 对 11 类可变 DocType 在每次 update/transition 上 `SELECT…FOR UPDATE` + 比对 `modified`（ISO、要求带时区）。Demo→Evaluation 重复生成靠状态机守卫 + 行锁串行 + savepoint 三重保险，并发双击不产重复（F4 仅针对 append 类） |
| 授权（无 IDOR） | 每个服务函数先 `assert_capability`（角色级）再 `_require_*`（`frappe.has_permission` 文档级 read 复核）；`merge_contacts` 禁止跨账户合并且 Manager-only；`change_password` 校验当前密码且只改 `session.user`；delete/transition 二次校验文档权限 |
| SQL 注入 | 全部 `frappe.db.sql` 用 `%s` 占位符；f-string 只插内部字面量（表/列名）；用户值经 `frappe.db.escape` |
| XSS（前端） | 全 `src/` **零** `v-html`/`eval`/`new Function`/`document.write`；Vue 默认转义；xlsx writer 用 `inlineStr` |
| 上传安全（除 F1/F3） | magic-byte 校验拒绝声称 MIME 与内容不符；office 防 zip-bomb/zip-slip/拒绝 `vbaproject.bin`；ClamAV fail-closed；文件名剥离路径分隔符与控制字符；`is_private=1` + `nosniff` + 审计 |
| 金额精度（单笔） | `bigint` 运算规避 IEEE-754；`weightedMoney` 半进位舍入方向正确（已执行验证 `0.025→0.03`、`0.005→0.01`） |
| 会话安全 | `sid` 设为浏览器会话级；`redirect-to` 做 URL 编码 |
| 前端请求乱序/防抖 | `sessionRequestRevision` 单调递增 + 完成时比对；`loadSequence` 守卫；`clearTimeout`-before-`setTimeout` 防抖 |
| 错误边界 | `api_endpoint` 把 `CrmApiException`→稳定码、`PermissionError`→401/403、`Exception`→rollback+log+泛化消息；`normalize_error_code` 收敛为 12 个公开码 |
| 身份切换不可在生产发生 | Frappe 模式 `identity-switch.ts` 直接抛错 |
| 密钥 | 无硬编码；`.env.*` 已忽略（仅 `.env.example` 无密钥）；`compose.yaml` 运行时生成 DB/演示员工170密码 |
| `parseFileName`（前端） | `.split(/[\\/]/).pop()` + 去控制字符，防御性剥离路径分量（文件字节来自后端，非文件名） |
| `cents()` 分数处理 | 已执行验证：`"1.2"→120¢`、`"1.20"→120¢`、`"1"→100¢`，`padEnd` 正确 |
| `readAllPages` 终止性 | total 与空页双重终止，无死循环（但无内存上限，见 F14） |
| Dashboard 订阅去重 | `notifying-api` 用 symbol 守卫防重复包裹 |

---

## 修复优先级

| 优先级 | 项 | 工作量 |
|---|---|---|
| **P0（上线前）** | F1 DOCX zip-bomb 防护 · F2 PDF 模板转义 · F3 导入接入 `validate_and_scan` | 中 |
| **P0（上线前）** | F5 `fromCents` 上界守卫 + 回归用例 · F7 后端 CI 门 | 小～中 |
| **P1（首个迭代）** | F4 强制 `expected_modified` · F6 mock↔Frappe 契约测试 · F8 自转移 no-op | 中 |
| **P2（治理/体验）** | F9/F10/F11/F12/F13 权限与隐私收敛 · F14 边界测试 · F15 时区与演示员工116边界 · F16 仓库卫生 | 小～中 |

---

## 方法论说明

本报告由 4 个并行子代理分别从【前端安全、业务正确性、代码质量/测试、后端安全】通读源码，主线程同时直接复核了所有 P0/P1 级目标（金额、并发、权限、上传、密码、路由、状态机、PDF 模板、导入解析）。所有列出的发现均已由主线程独立读源确认证据；子代理提出但经复核**不成立**或**降级**的条目（如分页 meta 在生产实际恒定返回、`parseFileName` 仅防御性）未计入上表，改列"已验证健壮"。
