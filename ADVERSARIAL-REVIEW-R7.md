# 对抗性审查报告 R7 — Semiconductor CRM（独立仓库重建后第一轮）

> **状态补记（PR3）**：本文保留的是修复前审查快照，不代表 PR3 当前状态。
> PR3 已以明文提交并修复 R7-B2、R7-B3、R7-B4；后续修复又收紧了
> `CRM Quotation Version` 原始 DocType/附件权限，并在插入前拒绝无
> Site/Address 权限的 Quotation，关闭标准私有文件路由绕过和死草稿问题。
> 其余条目仍按本文原始结论跟踪，不能因本补记视为自动关闭。

**审查日期：** 2026-08-30（审查对象：HEAD `d878925`，工作树干净，无未提交改动）
**上一轮基线：** `ADVERSARIAL-REVIEW-R6.md`（R6，对象为旧仓库 `d969e3a`）
**本轮方法：** 全历史密文取证（逐 commit 逐 blob 首字节比对）→ 远端引用状态核对 → PRD v1.1 与 scope.py 逐条对账 → 全 service 授权入口普查（`conditions_for_doctype` / `frappe.has_permission` 覆盖率）→ 运行时镜像内取证（`frappe.get_all` 语义）→ 发布制品逐条目与 HEAD 对账 + 打包脚本实跑复现 → 前端 `vue-tsc` + `vitest run` 实测

**实测基线：**

| 门禁 | 结果 |
|---|---|
| `vue-tsc --noEmit` | ✅ 通过 |
| `vitest run` | ❌ **退出码 1**：645 例中 4 失败（全为 timeout），另有 **2 个测试文件 worker 启动超时未执行**（跟踪 105 个 `.test.ts`，报告仅 103） |
| `backend/build/rayher_crm.zip` | ❌ **存在但受污染**：内含 TipRay 密文 PNG，且非受控脚本产出（详见 N1） |
| 后端全量（docker 栈） | ⬜ 未执行（需拉起完整 Frappe 栈，90 分钟量级；本轮以静态取证 + 镜像内取证替代） |
| 工作树 vs HEAD | 干净；全库 offset-0 密文扫描 **无命中**（TipRay 本轮静默） |
| 提交密钥扫描 | ✅ 无命中 |

---

## 执行摘要

R6 的三大 P0 中，**只有一个真正关闭**：PRD 已正式修订为 v1.1「产品口径已确认」，把 Public 的语义收窄为「仅客户主档 + Contact 开放」，并新增「Private 父级硬边界」——R6-B3 的规格漂移由产品拍板走 ② 方案解决，`scope.py` 的实现与 v1.1 逐条吻合，R6-N4 的掩蔽缺口也已补齐。

但**重建仓库并没有解决密文问题，只是把它重新演了一遍**：新仓库的初始提交 `bdabc1b` 本身就带着 16 个 TipRay 密文 blob，`9988e4a` 以「normalize Windows checkout text fixtures / padded binary blobs」的措辞把它们明文化——**提交信息回避了「这是密文」这一事实**；紧接着 `7f23b2e`（正是那次安全修复）又把 5 个文件整体以密文提交，**并已推送到 GitHub**。而修复它的 `d878925` **只存在于本地**：`origin/main` 仍停在 `9988e4a`，即**远端主干至今没有这次安全修复**，唯一含修复的远端引用是一条读不出来的密文分支。

功能面上，本轮找到一个**真实、可利用、且被绿灯测试掩盖**的缺口：`services/rfqs.py` 是全仓库唯一不走 `conditions_for_doctype` / `frappe.has_permission` 的业务服务，`7f23b2e` 为 RFQ 新增的父级边界 SQL **从未被任何 API 路径使用**；而新增的 `test_all_sales_child_scopes_include_the_private_parent_guard` 只断言 SQL 字符串里出现了守卫，不断言行为，于是缺口带着绿灯出厂。RFQ 恰恰是 PRD v1.1 的 AC-14 点名列举的对象。

**当前状态：语义已对齐、实现有一处点状缺口、制品受污染、远端主干无修复、密文已上公网。**

---

## 优先级总表

| 优先级 | 编号 | 问题 | 本轮证据 | 修复建议 |
|---|---|---|---|---|
| 🔴 **P0** | R7-B1 | **密文第二次进 git 历史，且已推送 GitHub**。`7f23b2e`（"enforce private account boundary"）5 个文件全部为 TSD 密文：`scope.py` / `contacts.py` / `test_scope.py` / `test_account_contact_api.py` / 权限 PRD，块对齐 24576/28672。**重建仓库未消除问题**：初始提交 `bdabc1b` 本身即含 16 个密文 blob（15 个 Playwright 快照 + R6 报告），由 `9988e4a` 明文化，但该提交信息写作「normalize Windows checkout text fixtures … padded binary blobs」，**回避了密文性质**（与 R6-B2 同族的措辞问题） | `git cat-file blob 7f23b2e:…/scope.py` 首 16 字节 = `%TSD-Header-###%`；`bdabc1b:ADVERSARIAL-REVIEW-R6.md` 同；`git cat-file blob origin/fix/private-account-boundary:…/scope.py` → 密文（**已在公网**） | ① IT 侧把本仓库目录白名单化（R6 起连续第七轮）；② 决策并执行历史重写（`git filter-repo` 移除 `7f23b2e` 的密文 blob）或删除远端 `fix/private-account-boundary` 分支并正式记录隔离决定；③ 打包/发布链路增加「push 前 offset-0 密文扫描」硬闸 |
| 🔴 **P0** | R7-B2 | **安全修复没有推送，远端主干仍是易受攻击版本**。`origin/main` = `9988e4a`，其 `scope.py` 为明文但**不含父级边界**；含修复的 `7f23b2e` 只以密文存在于侧分支；含明文修复的 `d878925` **仅存在于本地**。任何人 clone 得到的都是修复前代码 | `git log --oneline origin/main -3` → `9988e4a`；`git cat-file blob origin/main:…/scope.py` → `"""SQL-backed ro`，无 `_sales_parent_account_condition` | 先做 B1 的密文处置，再把 `d878925` 推上 `main`；`fix/private-account-boundary` 作废重开 |
| 🔴 **P0** | R7-B3 | **RFQ 完全绕过 scope 体系，`7f23b2e` 为 RFQ 加的父级边界是死代码**。`services/rfqs.py` 是唯一不调用 `conditions_for_doctype` 的业务服务（计数 = 0）：`list_rfqs()` 用 `frappe.get_all("CRM RFQ", filters={"sales_owner": user})`，`_require_rfq()` 只走自建 `_visible()`（`owner == frappe.session.user`，无父级判定）。**镜像内实证** `frappe/__init__.py:2043` 的 `get_all` docstring：「Will **not** check for permissions」→ `permission_query_conditions` 钩子对 RFQ 从不生效。**PRD v1.1 AC-14 点名列举 RFQ**：「即使 Manager 将其中某条业务记录的 owner/assignee 设为 Sales B，也不得绕过 Private」。攻击路径：Sales B 是某 RFQ 的 `sales_owner`，其父 Account 属于 Sales A 且为 Private → `list_rfqs` / `get_rfq` 仍返回该 RFQ（含 opportunity 标题、account 名、站点、文件名） | `services/rfqs.py:115-121`（`_visible`）、`:215-231`（`list_rfqs`）；对照 `opportunities.py:272` / `visits.py:122` / `quotations.py:167` / `bookings.py:180` / `leads.py:107` / `demo_requests.py:283` / `evaluations.py:46` / `installed_tools.py:287` 全部为 `frappe.has_permission(...)` | `_visible()` 改为 `frappe.has_permission("CRM RFQ", "read", doc=doc, ...)`；`list_rfqs` 改为 `frappe.db.sql` + `conditions_for_doctype('CRM RFQ')`（与其余 13 个服务同构），或至少 `frappe.get_list`。补服务级（非字符串级）回归测试 |
| 🔴 **P0** | R7-B4 | **守卫测试只验字符串不验行为，是 B3 带绿灯出厂的直接原因**。`test_all_sales_child_scopes_include_the_private_parent_guard` 对 13 个 DocType 只断言 `conditions_for_doctype(dt, sales)` 文本中出现 `tabCustomer` 与 `custom_crm_visibility`；行为级测试 `test_private_parent_cannot_be_bypassed_by_sales_child_ownership` 只覆盖 7 个对象（Contact / Lead / Opportunity / Booking / Installed Tool / Demo Request / Evaluation），**恰好漏掉 Visit / Quotation / Quotation Version / Quotation Approval / RFQ / RFQ Version 这 6 个**——RFQ 的缺口就落在这个空档里 | `tests/test_scope.py` 两个新测试的覆盖差集；`tests/test_rfq_api.py` 无任何 Private 父级用例 | 把行为级用例扩到全部 13 个 DocType，并且断言必须打在**服务函数**（`list_rfqs` / `get_rfq` 等）上而非 `conditions_for_doctype` 上 |
| 🟠 **P1** | R7-N1 | **发布制品受污染，且不是受控脚本的产出**。`backend/build/rayher_crm.zip`（08-30 02:35）中 `rayher_crm/public/images/quotation-planck-logo.png` 是 **TSD 密文**（24576 B，首 16 字节 `%TSD-Header-###%`），git HEAD 为正常 PNG（20257 B）→ 报价单 PDF 的 logo 在生产上是乱码。该 zip 含 **54 个目录条目**，而 `prepare-app-build-context.ps1` 只写文件条目 → **该 zip 不可能由受控脚本产生**，因而绕过了脚本内建的密文/空字节双重校验。本轮以 `-OutputArchive …/rayher_crm.audit.zip` 实跑该脚本：376 条目、PNG 明文 20257 B、校验通过（临时件已删）。`compose.yaml` 直接 `COPY build/rayher_crm.zip` 进镜像，`app-package-contract.ps1` 只校验源码树与脚本文本，**从不校验落盘的 zip** | zip 内条目逐条与 `git cat-file` 对账：247 条中 EOL 归一后仅 1 条不同，即该 PNG；条目数 430 vs 376，差集 54 全为目录项 | 删除现制品重跑 `prepare-app-build-context.ps1`；把「制品内容 == HEAD（EOL 归一后）」与「制品由受控脚本产出」纳入 `app-package-contract.ps1`；发布清单登记新 SHA |
| 🟠 **P1** | R7-N2 | **DDL 提醒绕过新父级边界（记录存在性泄露）**。`ddl_reminders._related_users()` 纯按 owner 关系收集收件人（`booking_owner` / `sales_owner` / `engineer_owner` / `action_owner` / `quotation_owner` / RFQ 双 owner），`_active_recipients()` 只校验「用户启用 + 有 CRM 角色」，**无任何 scope 校验**。Sales B 若持有他人 Private Account 下某条子业务的 owner 身份，仍会收到含 `source_name` 与深链 `route` 的站内通知——点进去 API 会 403，但记录 ID、类别与 DDL 已泄露，与 PRD §6.2「不暴露客户是否存在」冲突 | `services/ddl_reminders.py:19-56`、`:99-165` | 收件人集合在 `_active_recipients` 后再过一道 `has_crm_permission(source_doc, user)`，无权者直接剔除 |
| 🟠 **P1** | R7-N3 | **mock-adapter 仍是修复前的权限模型**。`canAccessOpportunity()` / `canAccessDemo()` 仅比对记录 owner，**无父级 Account 门**；`scoped()` 默认谓词是账户级 `canAccessBusinessAccount`。即 105 个前端测试文件所依据的语义 = `7f23b2e` 修复掉的那个语义（R6-N3 的放大版）。**已实证不进生产包**（79 个构建产物 grep 无 `createMockApi` / `canAccessBusinessAccount`），故非线上漏洞，但前端回归对该类缺陷完全失明 | `src/api/mock-adapter.ts:357-370`（`canAccessBusinessAccount` / `canAccessOpportunity`）、`:432`、`:490` | 三处谓词补 `canAccessAccount(accountId)` 父级门，与后端同构；加一组双端契约测试锁定 |
| 🟠 **P1** | R7-N4 | **前端门禁不稳定，且会静默漏跑测试文件**。`vitest run` 实测退出码 1：4 例失败**全部是 timeout**（15s/5s，非断言失败），总时长 354 s；另有 2 个文件（`QuotationDetailPage.test.ts`、`seven-page-workspace.test.ts`）因 worker 启动超时**根本没跑**，只体现为 "Unhandled Errors"，摘要显示「103 个测试文件」而仓库跟踪 **105** 个。当前没有任何机制断言「应跑文件数」 | vitest 摘要 `Test Files 2 failed / 101 passed (103)`；`git ls-files 'src/**/*.test.ts'` 计数 = 105 | 抬高 `testTimeout` / 降并发（或 `pool: forks`）稳住 AppShell 用例；在 release gate 里加「实跑文件数 == 跟踪文件数」断言，使漏跑变红而非变绿 |
| 🟠 **P1** | R7-N5 | **PRD §7.3 审计日志完全未实现**（R6-N8 顺延）。要求记录「客户创建 / visibility 变更 / 负责人变更 / Manager 删除客户 / 越权拒绝」，字段含旧值新值与请求 ID。实际仅有 `CRM File Access Audit` 一个审计 DocType，且只服务文件访问；`services/accounts.py` 内 **零** 审计写入。v1.1 修订并未放宽 §7.3——而整套权限模型正建立在「visibility 翻转可追溯」之上 | `services/accounts.py` 无 audit 调用；`doctype/` 下仅 `crm_file_access_audit` | 为 create/update_account 增加审计写入（操作者、客户 ID、字段旧值/新值、时间、请求 ID、结果），并在 `SCOPE_DENIED` 分支记录拒绝 |
| 🟡 **P2** | R7-N6 | `delete_contact_file` 仍以 **read** 权限授权破坏性操作（R6-N5 名义未修）。当前之所以安全，是因为 Contact File 的 Sales scope 恰好被收窄成「Account 负责人」——是**巧合而非设计**；scope 一旦再放宽，删除即随之放宽 | `services/contact_files.py:143-158`：`assert_capability("contact:write")` + `has_permission(..., "read", ...)` | 与 upload 的 `resolve_write_owner` 对称，显式判定 Account owner / Manager |
| 🟡 **P2** | R7-N7 | **PRD FR-08 的下载令牌条款与实现不符**。PRD 要求「令牌绑定 fileId/accountId/用户/过期时间」，实现里 **不存在任何令牌**：`download_contact_file` 每次按会话身份重新 `has_permission` + 写审计，无静态 URL。安全属性其实更强，但 v1.1 修订时没有同步这段文字，留下第二处规格漂移 | `api/v1/contact_files.py:download_file`；file_security / contact_files / api 三处 `token` 检索 0 命中 | 改写 FR-08 为「无令牌、逐次会话内重校验」并记录决策；否则下一轮仍会被判为不合规 |
| 🟡 **P2** | R7-N8 | CI 范围与成本未动（R6-N7 原样）：`release-gate.yml` 为 `on: pull_request, push`，无 `concurrency` 取消、无 `paths-ignore`，`timeout-minutes: 90` 且含 docker 后端全量 | `.github/workflows/release-gate.yml` | 加 `concurrency`（`cancel-in-progress: true`）+ `paths-ignore`（文档/报告） |
| 🟢 **P3** | R7-N9 | 仓库卫生：**无 `.gitattributes`**，全部文本 blob 以 CRLF 入库（`scope.py` 501/501、`README.md` 61/61、`frappe-adapter.ts` 529/529 —— 现在是「统一 CRLF」而非 R6 的「混杂」，但 CI 跑 ubuntu，任何未来的 `.sh` 都会踩坑）；`probe.txt` 第 7 轮仍被跟踪且未入 `.gitignore`；`.playwright-cli/` 15 个抓取快照入库（正是 `bdabc1b` 那批密文的载体） | 各 blob 的 CR 行数 == 总行数；`git check-ignore probe.txt` 无命中 | 加 `.gitattributes`（`* text=auto eol=lf`）；`git rm --cached probe.txt` 并入 `.gitignore`；`.playwright-cli/` 移出版本库 |

---

## 本轮确认已修复（对照 R6）

| R6 项 | 结论 | 证据 |
|---|---|---|
| **R6-B3 实现与 PRD 正面冲突** | ✅ **已关闭（走 ② 方案）** | PRD 升 v1.1 / 2026-08-30 /「产品口径已确认」；术语表拆为「基础共享数据 / 受限关联数据 / 独立业务数据」；FR-10 改写为「Private 父级边界与独立业务权限」，并给出统一读取公式 `child_owner_scope AND (account.owner == user OR account.visibility == Public)`；AC-02/03/12/13/14 全部同步改写 |
| **R6-B2 权限语义回滚** | ✅ 已修正并强化 | `scope.py` 新增 `_sales_parent_account_condition` / `_sales_child_condition`，对 Lead / Opportunity / Booking / Installed Tool / Demo Request / Evaluation / Demo Artifact / Visit / Quotation ×3 / RFQ ×2 全部叠加父级门；`account` 字段 `reqd=1` 的 6 个 DocType 不给 `allow_unlinked`，`reqd=0` 的 Demo Request / Evaluation 给 `allow_unlinked=True`——**一一对应，无可用性缺口也无绕过缺口** |
| **R6-N4 后端掩蔽不完整** | ✅ 已修 | `serialize_account` 对非 owner Sales 清零 `siteCount` + `pipelineAmount` / `intentScore` / `risk` / `nextAction` / `nextActionDue`；`serialize_contact` 新增 `siteId` / `siteName` 掩蔽；`get_account_360` 以 `can_read_business_data` 关掉 `sites` |
| **R6-B4 工作树密文-at-rest** | ✅ 本轮静默 | 全库 offset-0 扫描无命中（20 个 `TSD-Header` 文本命中经逐个核验均为文档/代码中的字面量引用）；`probe.txt` node 视图与 git 视图同为 4 B `ok\r\n` |
| **R6-N1 无可部署制品** | ⚠️ 部分 | zip 已存在且含父级修复，但内容受污染且非受控产出 → 转为 N1 |

## 本轮交叉攻击未攻破

| 攻击假设 | 结论 |
|---|---|
| 「除 RFQ 外还有服务自建授权」 | 证伪：13 个业务服务的 `_require_*` 全部走 `frappe.has_permission` → `has_crm_permission` → `conditions_for_doctype`，逐个核对无第二个例外 |
| 「`frappe.get_all` 被广泛用于主查询」 | 证伪：其余 `get_all` 命中均为**已受守卫的主对象之下的子记录**（quotation version/approval、contact reports-to、visit 附件）或调度任务，模式正当 |
| 「Dashboard / 导出因 Public 放大业务口径」 | 证伪：`get_dashboard` 先取可见 Account 集合，业务行来自已 scope 的 `list_pipeline` / `list_*`，再做交集；`actions_for_account` 完全派生自已 scope 的 opportunities |
| 「Site 有独立读接口可绕过 owner-only」 | 证伪：`api/v1/accounts.py` 只暴露 site 的 create/update/delete，读路径仅 `get_account_360`，已被 `can_read_business_data` 关闭 |
| 「mock adapter 泄漏进生产包」 | 证伪：79 个构建产物 grep 无 `createMockApi` / `canAccessBusinessAccount`，README 第 52 行的声明成立 |
| 「文件下载存在静态 URL / 可复用令牌」 | 证伪：无令牌机制，逐次会话内 `has_permission` + 五分支审计（capability / not found / deleted / scope / allowed） |
| 「仓库含提交密钥」 | 证伪：全量正则扫描仅命中 `compose.yaml` 从 `/run/crm-local-secrets/` 读取的变量名，无字面量 |
| 「`allow_unlinked` 是绕过口子」 | 证伪：4 处 `allow_unlinked=True` 对应的父字段 `reqd` 均为 0，且真实无父记录；`reqd=1` 的对象一律不给 |
| 「TypeScript 已漂移」 | 证伪：`vue-tsc --noEmit` 通过 |

---

## 上线 Gate（第七轮，顺序执行）

1. 🔴 **TipRay 白名单化**（B1 前置，连续第七轮要求）——任何 git / 打包操作之前
2. 🔴 **修 B3**：`services/rfqs.py` 接回 `conditions_for_doctype` / `has_permission`；**同时修 B4**：行为级父级边界测试补齐 6 个漏掉的 DocType，断言打在服务函数上
3. 🔴 **B1 密文处置决策**：历史重写 或 作废远端密文分支 + 正式记录隔离决定
4. 🔴 **B2 推送**：把含修复的明文 commit 推上 `origin/main`，让远端主干不再是易受攻击版本
5. 🟠 N1 重出制品（受控脚本）+ 把「制品 == HEAD」纳入 package contract；N4 稳住前端门禁并加「应跑文件数」断言
6. 🟠 N2 提醒收件人加 scope 过滤；N3 mock 双端对齐；N5 §7.3 审计日志
7. 🟡🟢 N6–N9 排期

## 方法论说明

本轮三个核心攻击假设：①「重建仓库解决了密文历史」——**证伪**，初始提交自带 16 个密文 blob，随后 `7f23b2e` 又推了 5 个上公网；②「PRD 修订 + scope.py 改造 = 语义已落地」——**部分证伪**，SQL 层确实与 v1.1 逐条吻合，但 RFQ 的 SQL 从未被调用，且守卫测试只验字符串不验行为；③「绿灯制品可发布」——**证伪**，制品内含密文 PNG 且不是受控脚本产出。后端因需拉起完整 Frappe 栈未做全量实跑，改以**运行时镜像内取证**（直接读 `frappe/__init__.py` 的 `get_all` 语义）替代推断，避免把「框架行为」当成假设来用；这也是本轮唯一的覆盖缺口，B3 的服务级回归必须在真实后端栈上复验。
