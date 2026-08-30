# CRM 独立后端、数据库与 Ubuntu 发布路线设计

**日期：** 2026-08-04  
**状态：** 已完成设计讨论与自审，待用户审阅书面规格  
**权威契约：** `docs/CRM-后端数据库对接契约-2026-08-04.md`  
**Stage 1 执行规格：** `docs/CRM-后端对接契约-Stage1执行规格-2026-08-04.md`

## 1. 目标与边界

本项目参考 PR #24 已上线 ERP 项目的工程模式，在 CRM 仓库内建立一套独立的 Frappe + ERPNext 后端。CRM 使用独立 Docker Compose 项目、Frappe Site、MariaDB、Redis、私有文件卷和自定义 `rayher_crm` App，不共享 PR #24 的 Site、数据库、业务 App、数据或持久化资源。

复用的是 Frappe、ERPNext、MariaDB、Redis、Worker、Scheduler、WebSocket、同域 API、Session/CSRF、权限和 Private File 技术栈。不安装 HRMS、`rayher_hr_payroll` 或发票 OCR sidecar。

旧 CRM 后端方案中关于镜像版本、Python 版本、Site、端口和数据库拓扑的决定全部失效，不作为实施依据。基础设施子项目开始时先核验 Frappe、ERPNext、MariaDB 与 Redis 的兼容矩阵，选定固定镜像标签或 digest 并写入 Compose，然后才构建和执行集成测试；不得使用 `latest`。

## 2. 串行交付阶段

各阶段必须依次通过，不能并行绕过前置 Gate。

### 2.1 子项目 0：恢复现有前端基线

当前基线为 `pnpm typecheck` 通过，70 个测试文件中 59 个通过、11 个失败；473 项测试中 443 项通过、30 项失败。先恢复到 70/70 个测试文件、473/473 项测试全部通过。

基线恢复遵循以下裁决规则：

- 已有契约或设计文档明确支持当前新行为时，保留实现并更新过时测试。
- 文档没有授权行为变化时，保留测试语义并修复实现或测试数据。
- DOCX、图片等二进制资产格式不符合约定时修复资产，不降低断言。
- 禁止使用 `skip`、`.only`、删除测试或弱化断言制造通过。
- 不在该子项目加入 A2、A4、A5 契约字段。
- 不重置、stash 或覆盖当前工作区其他改动。

失败项按二进制资产、Mock 数据与仓库兼容、Demo 路由与权限、AppShell 与页面契约四组处理。完成门槛为：

```text
pnpm typecheck   -> 0 errors
pnpm test        -> 70 files passed, 473 tests passed
pnpm build       -> success
git diff --check -> no new whitespace errors
```

### 2.2 子项目 1：Stage 1 契约预埋

严格执行 Stage 1 规格中的 A2、A4、A5 可加性变更，仅修改规格允许的七个文件，不改变 Mock 运行时行为，不修改现有测试断言。

A2、A4、A5 完成后只登记为“Stage 1 契约预埋完成”，不勾选为完整后端合规：

- A2 在 Frappe 真正执行并发校验并通过双写测试后才完整通过。
- A4 在真实 Frappe 异常、HTTP、网络和超时映射通过测试后才完整通过。
- A5 在只读实体 ingest、DocType 锁写和 capability 清理完成后才完整通过。

### 2.3 子项目 2：Stage 2 契约改造

完成 A1 和 A6：

- 从跨 HTTP DTO 中移除 `Blob`，上传改为 `multipart/form-data`，下载改为授权二进制流端点。
- 拆分 create/update 语义，客户端不再生成正式 ID；旧 ID 仅作为 `legacy_id`。
- Mock 与 Frappe Adapter 保持同一契约，并更新相应测试。

### 2.4 子项目 3：Stage 3 身份契约

完成 A3：Owner、Actor、Approver、CreatedBy、UploadedBy 等字段改用稳定 User/Employee ID。显示名只用于展示，内部员工和客户联系人允许同名但 ID 空间必须分离。后端身份只信任 `frappe.session.user`。本子项目还需产出一张受控的"显示名 → User/Employee ID"迁移映射表（数据产物），作为子项目 5 服务端 `owner`/`*By` 赋值（契约 B1）的前置依赖；映射表不存在则 A3 代码落地后 B1 仍会卡死。

### 2.5 子项目 4：本地 Docker 基础设施

全部 A Gate 通过后，建立独立 Frappe + ERPNext CRM 栈。Compose 项目使用 `rayher-crm`，Site 使用 `rayher-crm.localhost`，自定义 App 使用 `rayher_crm`。MariaDB、Redis、Sites、Private Files、Worker 和 Scheduler 均为 CRM 独立资源。

### 2.6 子项目 5：CRM 后端与接口对接

实现 `rayher_crm` DocType、权限、事务、文件、审计、通知和 `/api/method/rayher_crm.api.v1.*` 端点。前端 `frappe-adapter.ts` 只负责 HTTP、CSRF、响应解包和错误归一，不复制后端业务规则。

### 2.7 子项目 6：本地验收与 Ubuntu 发布

本地端到端、并发、权限、事务、文件、备份和恢复测试全部通过后，先部署独立 Ubuntu Staging；Staging 验收和回滚演练通过并经人工批准后，再部署另一台独立 Ubuntu Production。Staging 与 Production 不共享数据库、Volume、网络、密钥或业务数据。

## 3. 本地数据库架构

本地数据库请求链如下：

```text
Vue CRM
  -> CrmApi
  -> Frappe Adapter
  -> /api/method/rayher_crm.api.v1.*
  -> 权限与参数校验
  -> 业务 Service / 数据库事务
  -> Frappe DocType / MariaDB
  -> 稳定 ApiResponse DTO
```

计划资源名称：

| 资源 | 名称或边界 |
|---|---|
| Compose project | `rayher-crm` |
| Frappe Site | `rayher-crm.localhost` |
| Custom App | `rayher_crm` |
| MariaDB service | `db` |
| Database volume | `rayher-crm-db-data` |
| Sites/private files volume | `rayher-crm-sites` |
| Internal network | `rayher-crm-internal` |

`bench new-site rayher-crm.localhost` 在 CRM MariaDB 容器中创建独立数据库和站点账号。随后只安装 ERPNext 与 `rayher_crm`。Customer、Contact、Address、Item 等标准 DocType 以及 CRM 自定义 DocType 都位于该独立数据库中。

浏览器不得直接连接 MariaDB。浏览器 `localStorage` 和 IndexedDB 仅供 Mock 模式使用，不进入 Stage 或 Production 数据迁移。

## 4. 后端组件边界

```text
backend/
|-- compose.yaml
|-- Dockerfile
|-- env/.env.example
|-- scripts/
|   |-- init-site.sh
|   |-- migrate.sh
|   |-- backup.sh
|   |-- restore.sh
|   |-- healthcheck.sh
|   `-- smoke-test.sh
`-- apps/rayher_crm/
    |-- pyproject.toml
    |-- hooks.py
    |-- modules.txt
    |-- patches.txt
    `-- rayher_crm/
        |-- api/v1/
        |-- permissions/
        |-- setup/
        |-- sales/
        |-- demo/
        |-- installed_base/
        |-- documents/
        |-- notifications/
        |-- services/
        `-- tests/
```

- Compose 只负责服务拓扑、网络、Volume、健康检查和启动依赖。
- API 层负责请求解析、调用权限/Service 和稳定响应，不堆积业务规则。
- Service 层负责状态机、跨实体事务、文件授权和通知调度。
- Permission 层负责 Role、Permission Query Condition 和文档级授权。
- Setup 只负责幂等角色、Workflow、Custom Field 和非敏感初始配置。
- Patch 必须可审计、可重复执行且具有明确版本顺序。
- 文件上传走 multipart，文件下载走授权二进制流；主文件始终是 Frappe Private File。

## 5. 一致性、错误与安全

- 所有更新携带 `expectedModified`；服务端在**同一数据库事务内**对 Frappe `modified` 执行 compare-and-swap 乐观锁，冲突返回 `VERSION_CONFLICT`，禁止先读后写的 TOCTOU（契约 B5）。
- Lead 转换、联系人合并/删除、Account 级联、Booking 转 Installed Tool 和 Demo 状态流转必须处于单一数据库事务；Account 改名级联必须包含 Requirement，不产生空串外键、不硬删关键人（契约 B4）。
- 跨实体写入任何一步失败都整体回滚；通知及外部副作用只在提交后执行；其余四个跨实体操作的事务实现须与 `transitionDemoRequest` 同构（契约 B4/B5）。
- 创建 ID 由服务端生成；客户端 ID 仅可作为受控导入的 `legacy_id`（契约 A6）。
- GET/List 端点严格只读，数据修复通过显式 Patch 或迁移命令完成；`ensureDemoPrimaryContacts` 之类的自愈写副作用改为部署期迁移脚本或写接口内显式重算，GET 保持幂等（契约 B6）。
- Artifact 版本通过数据库锁或原子序列生成，并有 `(evaluation_id, type, version)` 唯一约束，客户端不得分配版本（契约 B7）。
- 日期与时间 wire 格式纪律：date-only 用 `YYYY-MM-DD`/MariaDB `DATE`，timestamp 用带时区 ISO/`DATETIME`，经 `shanghaiDateKey` 之类的 helper 归一；**删除硬编码 `today='2026-07-17'`**；业务日期按 `Asia/Shanghai` 解释，消除 `getContractRisk` 对 datetime 输入算成 NaN 的崩点（契约 B8）。
- 金额用 `DECIMAL(20,2)` + `currency` 字段，数量用 `INT UNSIGNED`，序列化校验金额小数位 ≤2、数量为正整数；KPI/漏斗按币种隔离聚合，禁止跨币种朴素相加（契约 B10）。
- 枚举单一权威：每个概念一份 Option 列表；Action `Completed`/`Done`、`OpportunityDto` 与 `StrategyOpportunityDto` 阶段枚举在迁移前归一种子，避免旧行过滤少算或状态机报错（契约 B11）。
- Frappe、HTTP、网络和超时错误归一为冻结的 `CrmApiErrorCode`。**后端上线目标集以 Stage 1 冻结的 40+ 码联合为准，不在本路线图内合并为 12 码目标表**（合并会破坏 `mock-adapter.test.ts` 等具体码断言，作为已知测试债务延后）；`denied` 收敛为 `{PERMISSION_DENIED, SCOPE_DENIED}`（契约 A4）。
- 身份只取自 `frappe.session.user`，不信任客户端角色、Owner 或审批人；服务端覆盖 `owner`/`*By`，按 Frappe User/Employee/Has Role 校验（契约 B1/A3）。
- CRM 三角色（Manager/Sales/Engineer）必须显式映射到 Frappe/ERPNext 角色体系，避免"CRM 层放行但 DocType 角色门拒绝"的双层冲突（契约 B2，子项目 5）。
- 行级范围在 Permission Query Condition/SQL 层实施，列表和详情使用同一规则；`teamOwners` 死字段需登记决策（契约 B2）。
- MariaDB、Redis 和 Worker 不发布公网端口。文件上传强制 **MIME 魔数（非后缀）白名单、总大小上限、单请求份数上限、病毒扫描、上传归属断言**；文件下载按 fileId 重新校验账户范围并写审计，阻断 IDOR；主文件始终是 Frappe Private File（契约 B12）。
- 非 Mock 构建禁止 `switchDemoIdentity()`（契约 B3）。
- 通知必须落地服务端事件 DocType（`actor`/`category`/`recipient_user`/`route`/`created_at`/`read_at`），带服务端 ISO `created_at` 与解析后的 `recipient_user_id`，删除硬编码种子；frappe 模式禁用客户端 `createNotifyingApi` Proxy，通知不再由客户端伪造（契约 B14）。
- 发布的报告 PDF 由服务端从 canonical 数据重生成（或至少存输入数据 hash/签名），客户端字节仅供预览，水印服务端施加，PDF 须有文本层（契约 B13）。
- 列表强制分页上限（建议 ≤200）并返回准确 `meta.total`；列表端点返回 `PageData` 包裹而非裸数组，**对应前端契约改造须在子项目 5 显式排期**（契约 B9）。
- 关键历史和审计记录不可变或软删除。

## 6. Ubuntu 健壮性与发布 Gate

- 使用固定镜像标签或 digest，不使用 `latest`。
- 运行脚本使用 Linux 路径，不依赖 Windows 盘符、PowerShell 或 Docker Desktop。
- 密码、Token、Cookie 和数据库凭据通过环境文件或 Docker Secret 注入，不进入仓库或日志。
- MariaDB、Sites 和 Private Files 使用独立命名卷；部署前备份数据库和私有文件。
- Backend、Frontend、Redis、Worker、Scheduler 和 WebSocket 配置健康检查、启动依赖与合理重启策略。
- 迁移必须幂等；任一步失败立即停止，不继续重启或切换流量。
- 提供并实际演练备份恢复、应用回滚和数据库迁移回滚边界；Frappe patch 基本前向不可逆，数据库"回滚"以从备份恢复（或前向修复）为准，不假设可 reverse-patch。
- 日志输出标准输出并轮转，不记录敏感信息或文件内容。
- 容器采用最小权限；内部数据服务不向公网开放。
- Production 使用 HTTPS、反向代理、安全响应头和上传大小限制。
- 时间戳统一存储，业务日期按 `Asia/Shanghai` 解释。
- Staging 与 Production 使用独立域名、账号、数据库、Volume、网络和密钥。

发布链路：

```text
本地 Docker
  -> 契约 / 权限 / 事务 / E2E
  -> 备份恢复演练
  -> Ubuntu Staging
  -> Staging E2E / 并发 / 重启 / 回滚演练
  -> 人工批准
  -> 独立 Ubuntu Production
  -> 冒烟测试与监控
```

## 7. 测试矩阵

### 7.1 前端基线

- `pnpm typecheck`
- `pnpm test`，70 个文件和 473 项测试全部通过
- `pnpm build`

### 7.2 契约测试

- Mock/Frappe Adapter DTO 与错误码一致。
- 覆盖乐观锁、稳定 ID、分页、二进制边界和只读接口。
- 禁止契约外字段和未登记错误码。

### 7.3 Frappe 单元测试

- DocType 字段、命名、唯一约束、状态机和角色矩阵。
- 覆盖 Manager、Sales、Engineer 和无 CRM 角色用户。
- 跨实体事务注入中途失败并验证完整回滚。

### 7.4 MariaDB 集成测试

- 并发双写产生 `VERSION_CONFLICT`。
- Artifact 并发发布版本不重复。
- 列表与详情行级权限一致。
- 数据库迁移重复执行不产生重复数据。
- 容器重启后数据库和私有文件仍存在。

### 7.5 本地端到端测试

覆盖登录、Account、Contact、Lead、Opportunity、Booking、Demo、Evaluation、Installed Tool、Document Center、通知、上传、授权下载、审计、并发冲突和重复提交。三类角色分别验证可见范围及禁止操作，浏览器控制台不得存在未处理错误。

### 7.6 Ubuntu Staging

- 从空数据库部署和从前一版本升级各验证一次。
- 完成数据库与私有文件备份/恢复演练。
- 验证 Worker、Scheduler、Redis、WebSocket、健康检查和容器重启。
- 验证 HTTPS、上传限制、日志轮转、磁盘容量和数据库连接。
- 完整 E2E、并发测试和回滚演练通过后，才允许申请 Production 发布。

## 8. 规划与实施顺序

本设计是总路线，不生成一个横跨所有子系统的巨型实施计划。每个子项目分别执行“设计规格 -> 用户审阅 -> 实施计划 -> 实现 -> 验收”。第一个实施计划仅覆盖“恢复现有前端基线”；它完成后才重新核对 Stage 1 的接口、文件和测试基线。

Stage 1 执行期间不创建分支、不 commit、不 stash。后续子项目是否提交，由对应规格和用户授权单独决定。
