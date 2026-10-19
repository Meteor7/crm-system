# 对抗性审查报告 R5 — Semiconductor CRM（上线前第五轮）

**审查日期：** 2026-08-28 晚（继全量 QA 之后；审查对象为 commit `51fe8dd`「fix(crm): harden CRM permissions and workflows」+ 当前工作树）
**上一轮基线：** `ADVERSARIAL-REVIEW-R4.md`（R4）、`CRM-全量QA报告-2026-08-28.md`（QA：后端 254 例 6 失败 + 97 错误）
**本轮方法：** 逆向验证新提交 51fe8dd 的每一处实质变更（剥离 CRLF 噪音取内容级 diff）→ 在重建镜像上重跑全量后端测试 → 前端全量 vitest → TipRay 跨进程取证（活跃集扩大检测）→ 制品-HEAD 对账

**实测基线：**

| 门禁 | 结果 |
|---|---|
| `vue-tsc --noEmit`（QA 已验，本轮无类型层变更） | ✅ |
| `vitest run` | ✅ **691/691 全绿**（R4/QA 时 4 红 → 夹具已随新权限模型重写） |
| `run-backend-tests.ps1`（重建镜像后） | ❌ **254 例：6 失败 + 97 错误（与 QA 完全同集）** |
| `backend/build/rayher_crm.zip`（`08CEEDF4…`） | 内容 ≈ HEAD（括号缺陷与 lostReason 两个标记均在）——**可对账但 HEAD 本身是坏的** |

---

## 执行摘要

`51fe8dd`（19:02）把整套权限隔离特性提交进了 git。前端夹具同步重写后 **691/691 全绿**，lostReason 服务端强制落地——这两点是真实进步。但该提交是在**后端大红灯（97 错误 + 6 失败）状态下**做出的：**scope.py 的括号缺陷（QA-P0-1）被原样写进了 git 历史**，工作树亦未修复（实测内容 == HEAD，仅 CRLF 差异）。任何人从 HEAD 构建部署，Sales 视角的商机/Booking/装机查询即刻 SQL 1064 全灭。

同时本轮取证发现 **TipRay 加密活跃集扩大**：`permissions/scope.py`（权限核心）与 `tests/test_api_foundation.py` 新进入密文-at-rest 状态（node 视图与 HEAD 一致、git 视角为密文）——下一次 `git commit` 即把权限核心文件的密文写入历史。

---

## 优先级总表

| 优先级 | 编号 | 问题 | 本轮证据 | 修复建议 |
|---|---|---|---|---|
| 🔴 **P0** | R5-B1 | **括号缺陷已进 git 历史（QA-P0-1 升级为已提交状态）**：`51fe8dd` 在后端 97 错误全红时提交；scope.py 三个 Sales 分支 4 开 3 关，Sales 视角 Opportunity/Booking/Installed Tool 查询全部 SQL 1064；工作树未修（内容==HEAD，仅 CRLF） | 重建镜像重跑：6 失败 + 97 错误，错误日志仍现 `…'Public'))) AND account=%s` 不平衡 SQL；`git show 51fe8dd` diff 确认演示员工122以 `+` 入库 | 三处各补 1 个 `)` → 重跑后端门禁（97 错误应归零）→ 单独提交修复 |
| 🔴 **P0** | R5-B2 | **红灯提交流程失控**：`51fe8dd` 提交时后端门禁为红（97+6），提交者只验了前端 | 提交时间 19:02；QA 于 ~18:45 已实测该内容 103 红；提交不含 test_scope/test_api_foundation/test_stage5b_schema 任何 re-baseline | 建立「后端门禁绿 = 提交前置条件（且必须来自重建镜像）」；补 pre-commit 钩子 |
| 🔴 **P0** | R5-B3 | **TipRay 第五轮活跃，范围扩大到权限核心**：`scope.py`、`test_api_foundation.py` 新入加密集；连同 `document_access.py`、`document_uploads.py`、2 个测试文件共 6 个文本文件 git 视角为密文（node 视图==HEAD，纯加密态旋转） | `git diff --numstat` 6 个 `.py` 为 `-`；跨进程 md5：git≠node、node==HEAD | IT 白名单化 → 验证恢复文本 diff → 加密态 pre-commit 闸门（连续第五轮要求） |
| 🟠 **P1** | R5-N1 | **后端 6 失败全部未修**：① bootstrap 越权测试（已提交回归，`@api_endpoint` 吞 PermissionError）② 4 个 test_scope 仍断言「Sales 全员共享」旧语义 ③ schema 冻结契约未纳入 `custom_crm_visibility` | 隔离复跑 bootstrap 仍失败；三者均不在 51fe8dd 变更集 | re-baseline 6 个测试（bootstrap 改断言 PERMISSION_DENIED 信封；scope 4 例改 owner+Public 语义；schema 契约加新字段） |
| 🟠 **P1** | R5-N2 | **delete_contact_file 仅做了前端修补**：51fe8dd 给 ContactFilesCard 加 `canDelete`（按 owner 隐藏按钮），但后端接口仍只查 read 权限——API 直调仍可删除公开客户他人文件（QA-P1-1 半修复） | `services/contact_files.py` delete 分支与 QA 时逐字相同，无 owner 守卫 | 后端补 owner/Manager 守卫（与 upload 对称），前端隐藏只是 UX 不是授权 |
| 🟠 **P1** | R5-N3 | **阶段白名单产生新分歧（N2′ 变形未除）**：mock 改为 `{设备规格确认→报价, 采购流程→Won}`；后端 MANUAL 仍为 `{预算审批→设备规格确认, 采购流程→Won}`。mock 允许的（设备规格确认→报价）后端仅事件触发；后端允许的（预算审批→设备规格确认）mock 拒绝 | HEAD opportunities.py:41-44 vs mock-adapter.ts:2463 | 将 `(当前,目标)` 矩阵提为共享常量；mock 模拟 rfq_approved/quotation_published 事件 |
| 🟠 **P1** | R5-N4 | Visit/Demo/Evaluation/Quotation/RFQ 的 Public 传播仍缺；Visit mock↔后端相反（AC-07）——与 R4-N2 相同，且补写该传播的尝试即 R5-B1 的坏代码 | scope.py 相应分支与 R4 逐字相同 | 补 5 组条件（经 demo_request/父客户关联）或修订 PRD |
| 🟡 **P2** | R5-N5 | mock evaluation run/deadline 乐观锁仍可选（后端必填）→ 契约分歧（R4-N5） | mock-adapter.ts:2223/2255 `!== undefined` 仍在 | mock 改必填 |
| 🟡 **P2** | R5-N6 | 必填参数缺失 → TypeError → 500 `retryable=true`（R4-N6）；必填 `expectedModified` 扩大触发面 | errors.py wrapper 未变 | 捕获 TypeError → 422 |
| 🟡 **P2** | R5-N7 | visibility/owner 变更无审计（PRD §7.3，R4-N7） | accounts.py 仍 0 audit | 复用 contact_files 审计模式 |
| 🟡 **P2** | R5-N8 | 历史残留全集未动（F8/F9/F11/F12/F15、soffice 并发闸、TSD 前缀信任 claimed_mime、PDF 页数上限）；部署清单 SHA 仍未更新（当前 `08CEEDF4…` 含括号缺陷**不可发布**） | 与 R4 相同行级证据 | 按 R4 排期；括号修复后重打包再录 SHA |
| 🟢 **P3** | R5-N9 | 仓库卫生：`probe.txt` 未跟踪未忽略（内容明文）；PRD、R3/R4/QA 报告等 7 个未跟踪文件未归档；`opportunities.py`/`package.json` 全文件 CRLF 重写产生 1408/74 行噪音 diff（掩盖真实 +2 行变更，本次审查需人工剥离） | git status / 51fe8dd stat | 统一 `.gitattributes` `* text=auto` 或 `eol=lf`；归档报告 |

---

## 本轮确认已修复（对照 QA/R4）

| 项 | 证据 |
|---|---|
| 前端全量 691/691 绿（QA 时 4 红） | vitest 实测；夹具随新权限模型重写（app/seven-page/manager-delete/personnel-sync/mock-adapter.test 共 74 行） |
| Lost Reason 服务端强制（QA-P1-4 / R3-N3′ 关闭） | opportunities.py +2 行：`Lost Reason is required when closing…`，含 field_errors |
| 前端 ContactFilesCard 删除按钮按 owner/Manager 显隐 | `canDelete` prop + `canDeleteContactFiles` computed（注意：后端缺口仍在 → R5-N2） |
| 文档中心路由修正 `/documents` → `/document-center` | 51fe8dd diff |
| 权限特性入库，HEAD 与制品内容趋同 | ZIP 两标记（括号缺陷、lostReason）均与 HEAD 一致——终于可对账（但内容含 P0 缺陷） |
| mock 去掉了两条非法转移（预算审批→报价、无条件报价→采购流程） | whitelist 收窄为 2 条（但与后端集合仍互有出入 → R5-N3） |

## 本轮交叉攻击未攻破（新增确认）

| 领域 | 结论 |
|---|---|
| 51fe8dd 是否夹带密文入库 | 6 个加密态文件在提交时以**明文小 diff** 入库（4-6 行级），历史干净；加密发生在提交之后（旋转加密）✅ |
| opportunities.py 1408 行改写是否藏私货 | 剥离 CRLF 后实质变更仅 +2 行（lostReason 强制）✅ |
| package.json 74 行改写 | 仅依赖排序调整 + CRLF，无依赖增删 ✅ |
| ZIP↔HEAD 对账 | 内容标记一致，制品不再是「第四态」✅（修复括号后重打包即为可发制品） |

---

## 上线 Gate（第五轮，顺序执行）

1. 🔴 修 R5-B1 三个括号 → 重建镜像重跑后端（预期 97 错误归零，剩 6 失败）
2. 🔴 re-baseline 6 个后端测试（R5-N1）→ 后端全绿
3. 🔴 TipRay 白名单化（R5-B3）——**必须赶在任何下一次提交之前**，否则 scope.py 密文入库
4. 🟠 后端 delete 守卫（R5-N2）+ 阶段矩阵共享常量（R5-N3）+ Public 传播决策（R5-N4）
5. 🟡 从最终 commit 重打包 → 部署清单录新 SHA → P2/P3 排期

## 方法论说明

本轮核心攻击假设：「新提交是对 QA 发现的修复」。逐文件剥离 CRLF 噪音后取内容级 diff 验证：确认修复了 lostReason/前端夹具，同时证伪「括号已修」（内容==HEAD）；发现「前端隐藏按钮冒充后端授权」（N2）与「白名单收窄但仍错位」（N3）；跨进程哈希证明加密活跃集扩大至权限核心 scope.py。后端测试在重建镜像上重跑，杜绝 QA 揭露的「容器跑旧代码」假绿。
