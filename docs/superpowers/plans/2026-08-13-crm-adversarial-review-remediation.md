# CRM 对抗性审查问题统一修复与全流程验收计划

> **执行要求：** 使用 TDD 逐项实施；先复现、再最小修复、最后运行完整质量门。不得覆盖工作区既有未提交改动。

## 执行状态（2026-08-17）

- [x] Opportunity × Demo 自动门禁已完成：Request 创建、Manager Approval、Evaluation Accepted 分别由服务端推进到“技术确认 / Demo验证 / 预算审批”。
- [x] Opportunity 页面不承载 Demo Request/Test 内容；新建和编辑均只读显示阶段，自动门禁没有手工入口。
- [x] Manager 专用回退已完成，要求原因、并发版本和审计；Sales/Engineer 无入口且服务端拒绝。
- [x] 详情错记录、Calendar/focus 精确定位、分页不可达、Document Center 局部失败、下载与删除错误反馈等前端 P0/P1 已修复。
- [x] Bench 假绿门禁已修复；最终后端全量 `219/219` 通过。
- [x] 前端全量 `102 files / 659 tests`、类型检查、生产构建通过。
- [x] 真实“示例企业035有限公司”业务链已纳入自动化，测试结束后 User、Booking、Notification、Audit、History、File 六类残留计数均为 0。
- [x] 桌面和 390px 移动视口已复验 Opportunity/Request 关键入口，页面控制台无 warning/error。
- [x] Manager、Sales、Engineer 三个真实 Frappe 会话已完成关键导航/权限验收；Engineer 无 Sales 导航和全局搜索，页面实时连接无 console error。
- [x] Frappe WebSocket 反向代理已修复：Origin/Host 使用 Docker 可解析的内部 frontend 地址，Site 仍由 `X-Frappe-Site-Name` 指定。
- [x] Quotation Manager 审批流已实现：Sales 只能提交审批，任一 Manager 可批准发布或填写原因驳回；Manager 自建报价可直接发布。
- [x] Quotation 业务状态与内部审批状态已拆分；客户 Rejected 不再与 Manager 驳回混用，同版本重复驳回/重提保留不可变审批记录。
- [x] Quotation Pending 状态锁定编辑/删除/新版本/客户决策，审批发布采用行锁、乐观锁、savepoint 和孤立 File 清理。
- [x] Quotation 列表增加审批状态筛选，详情增加 Manager 审批动作、驳回原因和审批历史，通知精确跳转报价详情。

### 交付顺序门禁

Frappe 静态资源不是 Docker 镜像构建时自动从 `src/` 生成。任何前端变更交付前必须严格按以下顺序执行，否则容器可能继续展示旧逻辑：

1. `npm.cmd run build:frappe`
2. `backend/scripts/prepare-app-build-context.ps1`
3. 构建并重建目标 `frontend` 容器
4. 浏览器强制刷新后复验静态资源 hash 与关键交互

## 目标与边界

- 修复正常用户操作会触发的错记录、错跳转、分页不可达、错误状态、事务残留、竞态和测试假绿。
- 使用真实半导体业务语义的数据跑通当前 Frappe 前后端全流程。
- 不处理必须主动伪造 Frappe 通用 REST 请求才能触发的鉴权绕过、横向攻击或注入。
- 不增加无关功能、新角色或新业务模块。

## 当前优先批次：Opportunity × Demo 自动门禁

详细 TDD 任务见 [`2026-08-14-opportunity-demo-auto-gates.md`](./2026-08-14-opportunity-demo-auto-gates.md)。本批次先于下列全项目批次执行，边界如下：

- 新 Demo Request 强制关联同 Account 的 Opportunity，创建后自动进入“技术确认”。
- Request Manager Approval 成功创建 Evaluation 后自动进入“Demo验证”。
- Evaluation Accepted 后自动进入“预算审批”。
- 三个自动门禁不能由普通 Opportunity 编辑或推进接口干预。
- 回退使用 Manager-only 专用动作；Sales/Engineer 不可回退。
- Opportunity 不新增 Demo Request/Test 展示板块，关联只用于状态机。
- 完成该链路后，继续执行全项目前端 P0/P1 对抗性审查与修复。

## 实施批次

### 1. 可靠测试门

- Vitest 固定使用 threads pool 和 2 workers。
- Manager 受控文档预览保持干净原文件名；普通受控副本才使用 `-Controlled.pdf`。
- Bench 通过 JUnit XML 包装器传播真实失败状态。
- HTTP acceptance 默认使用独立 `.test` site，并硬拒绝 operational site。

### 2. 精确详情与跨模块定位

- 增加 `getStrategyOpportunity(id)`，Opportunity 详情禁止首条兜底。
- Evaluation 的 `focus` 使用 `getEvaluation(id)` 精确加载。
- 增加 `getVisit(id)`，Calendar 跳转后精确加载、高亮目标拜访。
- Loading、Not Found、Denied、Error 互斥；旧请求不得覆盖新路由。

### 3. 分页与选择器

- Accounts、Contacts、Leads、Opportunities、Demo Requests、Evaluations、Visits、Requirements、Contracts、Installed Tools 消费真实分页元数据并提供翻页。
- 筛选变化回到第一页；删除页末记录后回到有效页。
- 业务选择器使用服务端搜索/继续加载，不依赖超大 pageSize。
- Calendar 按当前日期范围查询，不固定截断前 200 条。

### 4. 用户可见状态

- Document Center 的文档、访问审批、上传审批独立加载；局部失败不得隐藏文档库；审批后待办数量收敛。
- Engineer 不显示无法使用的客户全局搜索。
- 所有二进制下载统一使用 `downloadBlob`。
- 通知和删除类动作失败时保留原数据、恢复按钮并显示 Request ID。

### 5. 业务完整性

- 所有 mutation 的受控错误也必须 rollback；多表/文件操作使用 savepoint 和文件清理。
- Evaluation 进入 Internal Review 前必须有 Completed Test Run 和报告。
- Visit 的行动负责人必须可实际处理；提交纪要后行动必填字段不可清空；保存 Opportunity 关联。
- Quotation 校验金额/日期，锁定发布、决策与过期竞态，清理孤立文件，稳定返回 409/422。
- Document Upload 的 Request、File、Document、Audit 原子化，审批只能有一个终态。
- Installed Tool 日期单调且不允许未来日期；旧服务补录不得回退 lastService；serial 冲突返回 409。
- 同一 Won Opportunity 只允许一个非 Cancelled Booking。
- Opportunity 正常接口按顺序推进，普通创建不得直接为 Won/Lost。

### 6. Quotation Manager 审批流

- Sales 流程固定为 `Draft → Pending Approval → Manager Approved → Published → Customer Accepted/Rejected`，Sales 不再拥有 `quotation:publish`。
- Quotation Version 使用独立的 `Not Submitted / Pending / Approved / Rejected / Not Required` 审批状态；每次提交写入独立 `CRM Quotation Approval` 记录。
- Manager 驳回必须填写原因，原版本重新开放编辑并允许重提；批准时才生成正式 PDF，审批和文件发布在同一事务内完成。
- 多 Manager 采用任一人处理，审批记录行锁保证首个决定生效，重复决定稳定返回 409；提交和决定通过 Quotation 通知路由回详情。
- 既有正式版本迁移为 `Not Required`，既有草稿迁移为 `Not Submitted`，不改变报价编号、版本号和客户决策流程。

## 真实验收数据

使用唯一 run ID 构造“示例企业035有限公司”业务链：Lead → Customer/Site/Contacts → Opportunity → Visit → Demo Request → Evaluation/Test Run/Report → Quotation Draft → Sales 提交审批 → Manager 批准发布 → Customer Accepted → Won → Confirmed Booking → Installed Tool FAT/Shipment/Installation/SAT/Warranty → Version/Service，并核对附件、受控文档、通知、Account 360、Dashboard、Calendar 和 Demo Archive。

- `.test` 模式必须自动回滚或精确清理并验证零残留。
- 本地查看模式使用 `dataOrigin=local-acceptance`，幂等创建并提供精确清理命令。
- 脚本必须拒绝 staging、production 或未显式标记的站点。

## 2026-08-17 Quotation 关联 Account 作用域回归

- 线上复现数据：`CRM-QTN-00247` 与 `CRM-OPP-00246` 的业务 owner 为演示员工201，但关联 Account owner 为其他 Sales。
- 根因：Quotation 主记录已按 `quotation_owner` 正确放行，详情页随后加载 Account 360 时把关联资料的 `SCOPE_DENIED` 错误提升成整页 Denied。
- 修复原则：主记录成功加载后，Account、联系人、站点等辅助资料失败只能显示局部错误和 Request ID，不得遮蔽报价、审批历史、PDF 预览或下载。
- 回归覆盖：Sales 拥有 Quotation 但不拥有 Account 时，Quotation 详情仍可见，关联资料错误保持局部状态。

## 2026-08-18 Quotation 类型、来源与付款比例

- Quotation Type 增加 `Device / Service`。历史主记录与版本通过 patch 回填为 `Device`；Service 面向售后服务、维修和配件订购，使用独立简版行项目编辑器与 PDF 模板，同时复用版本、审批、发布和客户决定流程。
- 新建报价来源增加 `Others`。Opportunity 来源仍保持一条 Opportunity 一张 Quotation；Others 不关联 Opportunity，必须直接选择 Account，且同一 Account 可创建多张报价。
- Others 报价可在详情页随时补关联同一 Account 下尚未被其他报价占用的 Opportunity。关联不改变状态、版本号、审批或正式 PDF；当前 Draft（含 Pending）同步来源，已发布历史版本保持不可变，数据库唯一索引和行锁保证并发时只有一个关联成功。
- Payment Terms 保持四期结构和默认 `30 / 30 / 30 / 10`，四个比例均可在草稿中编辑；说明文字、预览 PDF、正式 PDF 和历史版本必须读取各版本实际保存值。
- 草稿保存不限制比例合计；Sales 提交 Manager 审批、Manager 直接发布、Manager 批准并发布时统一要求合计为 `100%`，不满足时返回稳定业务校验错误且不得生成正式 PDF 或改变审批状态。
- 列表展示并筛选 Type；详情展示 Type 和 Opportunity/Others 来源。Service 隐藏 Device 专用的父子配件层级、Incoterm、交期、Warranty 和 Installation/Training 区块。
- 真实半导体验收链显式使用 `quotationType=Device` 与 `30/30/30/10` Payment Terms，随后执行 Sales 提交、Manager 批准发布和客户 Accepted，避免依赖隐式默认数据。

## 完成门

- `pnpm typecheck`
- 稳定配置下的前端全量 Vitest
- `pnpm build`

## 2026-08-19 Trackability adversarial review

This review follows normal SPA collaboration paths and excludes forged generic REST requests, injection, and lateral attacks. The acceptance criterion is not merely that a notification center exists: every ownership or workflow handoff must notify the responsible person, open the exact record, and leave immutable evidence.

### Collaboration notification matrix

| Business action | Recipient | Exact route | Tracking guarantee |
| --- | --- | --- | --- |
| Account / Contact / Lead / Booking assigned or reassigned | New owner | Matching detail page | Mutation and notification share a savepoint; notification failure rolls back the handoff |
| RFQ created or revised | Engineer | `/rfqs/{id}` | Current version and notification are atomic |
| RFQ Engineer Comment | All enabled Managers | `/rfqs/{id}` | Comment remains in version history |
| RFQ Approved / Returned | Sales and Engineer | `/rfqs/{id}` | Decision, state, and notifications remain consistent |
| Document Access / Upload Request submitted | All enabled Managers | `/documents?workspace=approvals` | Pending decision uses a row lock; approval queues are no longer capped at 200 |
| Document Access / Upload decision | Requester or submitter | `/documents` | Request, File, Document, Audit, and notification are atomic |
| Opportunity Action created or reassigned | Action owner | `/opportunities/{id}` | History stores complete before/after snapshots |
| Visit Action assigned / Minutes reviewed | Action owner / Visit owner | `/visits?focus={id}` | Recipient must be able to read the focused Visit |
| Demo Comment mention | Mentioned user | `/demo-workflow/{id}?tab=comment` | Comment and notification share a savepoint |
| Evaluation status, Internal Review, Test Run DDL | Sales, Managers, related Engineer | `/demo-workflow/{requestId}?tab=information` | `CRM Evaluation History` records Created, Status, Preparation, Test Run, Deadline, and Report events |
| Booking conversion, service next action, Engineer reassignment | Engineer / Action owner / New Engineer | `/installed-tools?surface=detail&tool={id}` | Action owner must have read access; Engineer Assignment is versioned |
| Quotation submitted, approved, or rejected | Managers / Quotation owner | `/quotations/{id}` | Approval history is immutable and separate from customer decision state |

### Notification center delivery

- Bootstrap reads the first page plus the server-side unread total, so the badge is not limited by page size.
- Opening the panel, window focus, visibility restore, and a 30-second low-frequency poll refresh server state.
- Load-more pagination is available and the notification entry remains visible on mobile.
- Navigation happens before mark-as-read; API failure preserves unread state and displays the Request ID.
- Contact scope accepts explicit Contact ownership, so a reassigned Contact can be opened even when its Account belongs to another Sales user.

### Added regression gates

- Visit dead-link reproduction: a second Sales user received `Visit action assigned` but `get_visit(id)` returned `SCOPE_DENIED`. Sales Visit scope now permits `visit_owner OR action_owner`; the action owner can open the focused record, see it in the list, and complete the action. Manager review and delete permissions are unchanged.
- Booking notification fault injection proves creation and reassignment roll back completely.
- Contact reassignment across Account scope keeps list and detail permissions consistent.
- Demo Report fault injection compares against the pre-existing notification baseline.
- Installed Tool Version History schema includes `Engineer Assignment`.
- Stage 5E authenticated HTTP acceptance passed with Opportunity `需求发现 -> Wafer Demo确认 -> 预算审批` automatic gates, dual Internal/External reports, a Completed Test Run, workflow projection, restart persistence, and exact cleanup.
- Stage 5F authenticated HTTP acceptance passed with a required linked Opportunity, contact and Demo artifacts, dual report byte-for-byte downloads, Sales/Engineer recipient isolation, exact report routes, mark-read persistence, and exact cleanup.
- Stage 5G authenticated HTTP acceptance passed with linked Opportunity persistence, Visit action/review notification identity and exact routes, recipient `get_visit(id)` reachability, Pipeline, Account 360, per-currency Dashboard aggregation, and paginated controlled-document reads.
- All HTTP acceptance scripts default to project `rayher-crm-stage1-tests`, site `rayher-crm.test`, URL `http://127.0.0.1:2225`, and `backend/test.env.example`; they reject non-`.test` sites before Docker or HTTP writes.
- Frontend full suite: `104 files / 671 tests`; typecheck passed.
- Backend JUnit gate: `239 tests`, `0 failures`, `0 errors`; the real semiconductor flow and its run-specific zero-residual assertions passed.
- Production build: Vite transformed `2666 modules` and completed successfully.
- Zero-residual audit passed on the `.test` site: no `crm-stage5*` temporary Users, `Stage 5* Account` Customers, or notifications for those recipients remain.
- Operational rollout completed for `rayher-crm-stage1-local`: migrated `rayher-crm.localhost`, recreated only backend/frontend/websocket/queue/scheduler services, kept MariaDB and Redis running, and verified healthy containers plus HTTP 200 for the deployed `index-ChQrwgo1.js` asset at `http://203.0.113.10:2224`.
- Pending final delivery gate: authenticated Manager/Sales/Engineer browser acceptance. The only available in-app browser session is currently at the Frappe Login page; no credentials were read or guessed.
- 后端全量 JUnit 门且失败能返回非零
- 真实 HTTP 全流程
- Manager、Sales、Engineer 浏览器验收
- 测试站点零残留
