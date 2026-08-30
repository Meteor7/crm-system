# 对抗性审查报告 R2 — Semiconductor CRM（上线前第二轮）

**审查日期：** 2026-08-25
**审查对象：** 工作树当前状态（HEAD `fe66e36` + 117 个未提交变更文件，含 2 个未跟踪文件）
**上一轮基线：** `ADVERSARIAL-REVIEW.md`（16 项发现）
**本轮方法：** 主线程逐行复核上轮 P0/P1 修复 + 重新攻击权限/上传/并发/金额/PDF/部署链 + 实测运行验证（非纯静态）

**实测基线：**

| 门禁 | 结果 |
|---|---|
| `vue-tsc --noEmit` | ✅ 通过 |
| `vitest run` | ❌ **1 文件 / 5 用例失败**（`demo-request-docx.test.ts`，原因见 B1） |
| Python 全量编译 `compileall` | ✅ 通过（242 个源文件无语法错误） |
| `backend/build/rayher_crm.zip` TSD 密文扫描 | ✅ 554 条目全部明文（SHA-256 `3C2FCA2F…76A6D4`） |
| 已构建前端 bundle 扫描 | ✅ 无 `createMockApi`、无 `alex.chen@semicore` 等演示数据 |

---

## 执行摘要

代码层面的上轮 P0 修复**质量良好**：DOCX zip-bomb 双上限、导入路径接入 `validate_and_scan`、报价单模板全量 `| e` 转义、`fromCents`/后端聚合上界守卫均已落地并可验证。权限矩阵本轮还进一步加强（`has_crm_permission` 双重门禁、Engineer 隐藏 stakeholder、RFQ Engineer 只读预览、事件驱动阶段门）。

但本轮发现一个**上线阻断级（Blocker）的发布完整性风险，且当前就处于激活状态**：

> **本机 TipRay（天锐绿盾）透明加密对同一文件在不同进程返回不同字节。** git.exe 看到 9 个跟踪文件是密文二进制；vitest 的 node worker 读到 DOCX 模板是 790,528 字节的 `%TSD-Header-###%` 密文（python/powershell 读到的是 785,497 字节明文）——这直接导致 5 个前端测试失败。当前 115 个文件的未提交工作就泡在这个状态里：**现在执行 `git add/commit` 会把密文 blob 写进历史**（`_archive/tipray-corrupted-20260814` 证明此类事故发生过）。

打包链（`prepare-app-build-context.ps1` 的 TSD 标记 + 空字节双重校验）是有效且 fail-closed 的——当前 ZIP 已验证干净——但这道闸门保护的是**制品**，保护不了 **git 历史**和**本机测试门禁的可信度**。

---

## 🔴 B1 — TipRay 密文-at-rest 当前激活：git 视角 9 个源文件为密文，测试门禁已红（Blocker，发布工程）

**证据链（全部本轮实测）：**

1. `git diff --numstat HEAD` 显示 9 个文件为二进制差异（git 读到密文）：
   `services/{accounts,demo_artifacts,demo_requests,document_access,quotations}.py`、`tests/{test_demo_request_api,test_quotation_api,test_stage5b_schema}.py`、`doctype/crm_demo_comment/crm_demo_comment.json`、`docs/CRM-人员显示名…迁移映射-2026-08-04.csv`
2. 这些文件 mtime 为 08-24/08-25（**昨天到今天被重新加密**），且解密视图内容与 HEAD **存在真实代码差异**（未提交的有效改动被关在密文里）。
3. vitest 内 `readFileSync('public/templates/demo-request-form-v2.docx')` 返回 `{"len":790528,"first4":[37,84,83,68]}`（`%TSD`，密文）；同文件 python/node 直读为 `PK\x03\x04` 785,497 字节（明文）→ **5 个测试失败，报"Word 模板不是有效的 ZIP 文件"**。
4. 上轮审查时 `vitest run` 全绿（102 文件/659 用例），本轮 105 文件/679 用例中 5 个失败——**不是代码回归，是环境加密状态变化**。

**攻击/事故场景：** ① 开发者现在提交 → 仓库永久性引入密文 blob，Linux CI/服务器 clone 即坏；② `vite build` 的 node 进程若拿到密文视图，`public/templates/*.docx` 会以密文复制进 `public/crm/`（会被 ps1 闸门拦下，但构建白做）；③ 本机测试门禁不可信——"全绿"与"全红"取决于 TipRay 心情。

**修复要求（上线前必须完成）：**
- 让 IT 把本仓库目录（含 `backend/build/`、`public/`）加入 TipRay 排除/解密白名单，确认 `git status` 中上述 9 个文件恢复为文本 diff；
- 恢复后重新生成并记录 `rayher_crm.zip` SHA-256，重跑 `vitest run`（须 679/679 绿）再提交；
- 给 `prepare-app-build-context.ps1` 补一条"git 视角同检"（`git diff --numstat` 无 `-` 二进制行才允许打包），防止复发；
- 长期：把"加密态检测"做成提交前钩子（现有 `.git/hooks` 无任何非 sample 钩子，`core.hooksPath` 未设置）。

---

## 上轮 16 项发现修复状态复核

| # | 上轮问题 | 状态 | 本轮证据 |
|---|---|---|---|
| F1 | DOCX 导入 zip-bomb | ✅ **已修复** | `_docx_tables` 现先查 `MAX_DOCX_ENTRIES=500` 与声明解压总量 ≤50MiB 再 `read`；残量：`_pdf_text` 对 100MB PDF 仍无页数上限（见 M3） |
| F2 | 报价单 PDF 模板注入 | ✅ **已修复** | `quotation.html`/`service_quotation.html` 所有自由文本插值均带 `\| e`；剩余未转义插值（subtotal/total/qty/日期）均为服务器计算值 |
| F3 | `import_form` 绕过统一校验 | ✅ **已修复** | `import_demo_request_form` 首行即 `validate_and_scan`，扩展名↔MIME 二次核对 |
| F4 | append 类乐观锁可绕过 | 🟡 **部分修复** | `transition_demo_request` API 层 `expectedModified: str` 必填；`update_evaluation_status` 经 `lock_document` 实际强制。**仍开放**：`add_evaluation_run`、`set_evaluation_test_run_deadline`、`complete_evaluation_preparation` 三端点 API 层可省略（服务层回退 `_lock_*` 不比对 `modified`）→ 追加类写入仍可静默覆盖并发编辑 |
| F5 | `addMoney`/`fromCents` 越界 | ✅ **已修复** | `fromCents` 加 `> 99999999999999999999n` 守卫；后端 `aggregate_by_currency` 同步加上界抛错 |
| F6 | mock↔Frappe 行为契约缺失 | 🟡 **部分修复** | 新增 `server-id-contract.test.ts`（纯类型层）+ `frappe-frontend-contract.ps1`（bundle 禁词/资产存在性）；**仍无**同一输入灌双实现比对的行为契约 |
| F7 | 后端 pytest 无门禁 | 🟡 **部分修复** | `run-backend-tests.ps1`（强制 `.test` 站点）+ 6 个 HTTP 验收 ps1 已就位；仓库内仍无 CI workflow，门禁靠人执行 |
| F8 | Evaluation 自转移重置停滞计时 | ❌ 未修复 | `evaluationStatusOptions` 仍把 `current` 列为合法目标，`mock-adapter` 无同状态拒绝 |
| F9 | demo 身份未知 id 回退管理员 | ❌ 未修复 | `identities.ts:28` 仍为 `?? DEMO_IDENTITIES[0]` |
| F10 | 销售可硬删 Site、引用时 500 | ❌ 未修复 | `delete_site` 仍仅 `account:write` + `ignore_permissions` 硬删 Address，无 Link 引用守卫（仅清 Contact.custom_crm_site） |
| F11 | bootstrap 全员目录含 `user.bio` | ❌ 未修复 | `_personnel_directory` 仍下发 `bio` |
| F12 | Restricted 文档 checksum 泄露 | ❌ 未修复 | `read_only_views.py:81` 仍返回 `content_hash` |
| F13 | `get_bootstrap` 缺 `@api_endpoint` | ❌ 未修复 | 仍无装饰器（`get_health` Guest 开放为有意设计，可接受） |
| F14 | money/边界测试不足 | 🟡 略改善 | `money.test.ts` 4→5 例，仍未覆盖负数/前导零/上限 |
| F15 | 合同 0 天/非法日期边界 | ❌ 未修复 | `contracts.ts` 无 `days===0` 文案分支 |
| F16 | 仓库卫生 | ✅ 基本修复 | `.gitignore` 已含 `_archive/`、`.codex-docker-config/`、`artifacts/` 等；根目录原型 HTML/调研 MD 仍在 |

---

## 本轮新发现

### 🟠 N1 — LibreOffice 无沙箱转换不可信 Office 文件（Medium~High，视威胁模型）

- **位置：** `services/rfqs.py:_office_preview`（`soffice --headless` 转换用户上传的 docx/xlsx/pptx 为 PDF 预览）
- **证据：** 转换发生在 Frappe 应用容器内（与 DB 凭据、站点文件同宿主），无 seccomp/firejail/独立容器隔离；仅有 `--norestore` 等开关、临时目录与超时。历史上 LibreOffice 转换过滤器多次爆出可利用 CVE（如 CVE-2022-26305 签名绕过、多个 parser 漏洞）。
- **攻击场景：** 任一 Sales 上传构造的 Office 文件 → 触发容器内解析 → 若命中转换器漏洞则直接落在应用容器（可读站点 `site_config.json` 的 DB 凭据）。另每次调用冷启动 soffice（约 0.5–2s），无并发信号量 → 并发上传可做 CPU 放大。
- **建议：** 把转换挪到独立的一次性容器或至少 `--convert-to` 专用 profile + ulimit；加进程级并发上限（如 semaphore=1）；长期盯 LibreOffice 安全公告并固定版本。

### 🟡 N2 — TipRay 头部前缀可被任意上传者伪造，绕过 magic-byte/一致性校验（Low-Medium）

- **位置：** `file_security.validate_and_scan`：`content.startswith(TIPRAY_HEADER)` 时直接信任 `claimed_mime`。
- **影响：** 任何认证用户在文件前拼 15 字节 `%TSD-Header-###%` 即可把**任意二进制**以 `.pdf` 名义存入 contact_files / demo_artifacts / RFQ 原件（ClamAV 仍会扫，投递带 `nosniff`+`attachment`，故非直接 RCE/XSS）；受控文档发布路径不受影响（有 hash 校验）。RFQ 预览路径对 TipRay 显式拒绝，证明设计者知晓此格式——但**信任判定基于 15 字节前缀，任何人都可伪造**。
- **建议：** 若需支持 DLP 加密件，改为可校验的判定（如全文熵值 + 尾部结构），或仅允许 Manager 角色上传 TipRay 件，其余一律拒绝。

### 🟡 N3 — 上传预算放宽到 100MiB×10 文件 + 210m body 的可用性放大（Low-Medium）

- `MAX_FILE_BYTES`/`MAX_REQUEST_BYTES` 从上轮的 10MiB 提到 **100MiB**（`file_security.py:14-16`），nginx `CLIENT_MAX_BODY_SIZE=210m`，gunicorn 2 worker×4 thread，ClamAV INSTREAM 单流 10s 超时。
- 4 个 Sales 并发各传 100MB → worker 内存驻留 ~0.8–1GB + 4 路 ClamAV 流；`_pdf_text` 对恶意多页 PDF 无页数上限（100MB 可构造数十万页，pypdf `extract_text` 逐页烧 CPU 至 gunicorn 120s 超时）。
- **建议：** 单文件上限回调到业务实际需要（DRF/报告 ≤25MiB？）；`_pdf_text` 加 `MAX_PDF_PAGES`（如 200）与文本量上限；ClamAV 10s 对 100MB 偏紧，要么降文件上限要么提超时。

### 🟢 N4 — 残余小项

1. `quotations._document_for_version` 线性扫全表 + 逐行 `get_doc`（每次访问请求 O(全部文档)，暂可接受，文档量上来会慢）。
2. `transition_demo_request` API 缺 `expectedModified` 时抛 TypeError → 走通用 500（应为 422；同类问题适用于所有 Frappe whitelisted 必填参数）。
3. `get_preview_pdf` 每次请求双渲染（body+overlay PDF 再 pypdf 合并），无缓存无频控——Sales 反复点预览即 CPU 消耗；建议对同 version 缓存或限频。
4. `hooks.py` scheduler 引用的 `services/ddl_reminders.py` 及其测试**尚未 `git add`**（当前 zip 已包含，因为 ps1 按工作树打包）；若任何环境从 git 部署，daily 调度会 ImportError。提交时勿遗漏。
5. `docs/CRM-Ubuntu-Staging部署与回滚清单` 记录的候选 ZIP（245 entries / SHA `E0A7…`）已过期（现 554 entries / `3C2F…`）——按清单要求部署前重录即可，属文档漂移提醒。
6. `backend/.env.lan` 使用 `HTTP_BIND_ADDRESS=0.0.0.0`（LAN 预览用）；staging 清单已要求绑定 `127.0.0.1` + 主机反代 TLS，执行时勿直接复用 lan 配置。

---

## ✅ 本轮交叉攻击未攻破（新增确认）

| 领域 | 结论 |
|---|---|
| 权限矩阵收紧 | `has_crm_permission` 现按"角色能力 + DocPerm + 行级 SQL"三重判定；Engineer 序列化时不再收到 Opportunity stakeholders；RFQ Engineer 仅预览无原件下载（`rfqs.py:502-504`） |
| 阶段门事件化 | `设备规格确认→报价`/`报价→采购流程` 从手动白名单移除，改由 `rfq_approved`/`quotation_published` 服务端事件驱动 + `FOR UPDATE` 行锁；回滚到"报价"之前会 `reopen_approved_rfq_for_stage_rollback` |
| 金额链 | 前端 bigint + 上界、后端 Decimal + 聚合上界、半进位舍入，双层一致 |
| 上传链（除 N2/N3） | magic-byte、扩展名↔MIME、zip-bomb（条目数+声明解压总量+加密条目拒绝+zip-slip）、`vbaproject.bin`（xlsx/pptx）、ClamAV fail-closed、文件名路径/控制字符剥离、`is_private=1` |
| 受控文档分发 | 原件 hash 校验 + File 归属校验（attached_to 三元组）+ Request/Approved 状态机 + Manager 直通 + 每次访问写审计（含 denied）；投递头 `no-store`+`nosniff` |
| 密码与会话 | 改密校验当前密码、强度策略、只作用于 `session.user`；`sid` cookie 强制浏览器会话级（after_request 钩子） |
| 测试安全 | `before_tests` + meta_path finder 强制 `.test` 专用站点，compose `ALLOW_TESTS=true` 必须同时满足 `CRM_TEST_SITE=true` + `*.test` 站点，防止测试数据打进生产库 |
| 部署链 | 镜像全部 digest 固定；`secrets-init` 运行时生成 root/admin 密码（umask 077, chmod 0444）；ps1 打包闸门（TSD 前缀 + 文本空字节 + 重parsepoint + 条目数复核）实测有效；mock 代码/演示人员不出现在生产 bundle（实测 grep 为 0） |
| SQL 注入 | 本轮复查 `scope.py`/`bookings.py`/`opportunities.py` 等全部用户值仍走 `%s` 参数或 `frappe.db.escape`；新增代码未引入 f-string 拼接用户输入 |
| XSS | 全 `src/` 复查仍无 `v-html`/`innerHTML`/`eval`；模板 `| e` 转义完备 |

---

## 上线 Gate（建议顺序执行）

| # | 动作 | 阻断级 |
|---|---|---|
| 1 | **TipRay 排除仓库目录并验证 9 个文件恢复文本 diff**（B1）；恢复后 `vitest run` 须 679/679 绿 | 🔴 P0 |
| 2 | 提交全部工作树（**含未跟踪的 `ddl_reminders.py`/`test_ddl_reminders.py`**）；确认 `git show HEAD:<9 文件>` 为明文 | 🔴 P0 |
| 3 | 重新跑 `prepare-app-build-context.ps1` + `run-backend-tests.ps1` + 6 个 HTTP 验收脚本；重录 ZIP SHA-256 到部署清单 | 🔴 P0 |
| 4 | N1：soffice 转换加并发信号量（一行改动）；沙箱化列入第一迭代 | 🟠 P1 |
| 5 | F4 残余：三个 append 端点 API 层必填 `expectedModified` | 🟠 P1 |
| 6 | N3：确认业务真实文件上限并回调；`_pdf_text` 加页数上限 | 🟠 P1 |
| 7 | F8/F9/F10/F11/F12/F13/F15 与 N2、N4 小项按上轮优先级表排入迭代 | 🟡 P2 |

---

## 方法论说明

本轮以"上轮结论可能被推翻/修复可能不完整"为前提：所有 ✅ 修复结论均重读当前工作树源码确认（而非信任 diff 注释）；所有 ❌/🟡 均附行级证据；B1 通过三个独立进程视角（git/python/powershell/vitest-node）交叉取证，并用构建 ZIP 内容扫描闭环验证制品未被污染。前端测试失败原因经最小复现测试（临时 diag 用例 dump 首字节）定位，复现后已清理临时代码。
