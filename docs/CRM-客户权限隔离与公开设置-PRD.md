# CRM 客户权限隔离与公开设置 PRD

**版本**：v1.0  
**日期**：2026-08-28  
**状态**：待评审  
**参考模型**：Salesforce Account 私有记录 + 显式共享

## 1. 背景

当前系统中，Sales 之间可以互相查看并编辑其他 Sales 负责的客户公司及联系人。该行为不符合销售数据隔离的目标，也会造成客户名单、客户规模、负责人和联系人信息的过度暴露。

本需求将客户公司（业务对象：Account；后端 Frappe 中由 Customer DocType 承载）调整为默认私有，并在 Account 写入时增加“权限设置”，允许创建人选择“私有”或“公开”。Manager 保持最高权限，可查看、编辑和管理全部 Account，无论 Account 权限设置为何。

## 2. 目标与非目标

### 2.1 目标

- Sales 默认只能查看和编辑自己负责的私有客户。
- 客户创建或编辑时可设置客户可见性：`Private`（私有）或 `Public`（公开）。
- 公开客户及其全部业务关联信息对所有 Sales 可见，但其他 Sales 默认只读。
- Manager 对全部客户拥有完整查看、创建、编辑、删除和权限变更能力。
- Account 下的 Contact、Site、客户文件等关联资料继承 Account 的访问范围。
- 后端强制执行权限，前端隐藏或禁用不能替代后端校验。
- Dashboard 聚合必须覆盖当前角色有权访问的全部分页数据，不能因单页上限导致 KPI 或图表静默少算。

### 2.2 非目标

- 本期不实现 Salesforce 完整的 Account Team、Territory Management 或复杂 Sharing Rule。
- 本期不改变 Manager、Engineer 的既有角色定义。
- 本期不改变 Lead、Opportunity、Demo、Evaluation 等对象的独立负责人权限模型，除非其访问客户数据时需要继承 Account 权限。

## 3. 术语与权限语义

| 术语 | 定义 |
|---|---|
| Account（客户公司） | 系统中的客户公司业务对象；后端可映射到 Frappe `Customer`，代表一家公司，不是联系人个人 |
| 私有 Private | 仅客户负责人和 Manager 可查看；客户负责人可编辑 |
| 公开 Public | 所有 Sales 可查看该 Account 及其全部业务关联信息；非负责人 Sales 默认只读 |
| 客户负责人 | Account 的 `owner/custom_crm_owner`，负责客户经营的人 |
| Manager | 管理角色，拥有全部客户的完整权限，不受 Private/Public 限制 |
| 关联数据 | Contact、Site、客户文件及以客户为主对象的资料 |

“公开”表示对内部 Sales 全量开放该 Account 的业务信息，不等同于可编辑。密码、Token、系统权限字段等安全数据不属于业务信息，不得因 Public 设置而返回。

## 4. 角色权限矩阵

| 操作 | Sales：私有且本人负责 | Sales：私有且他人负责 | Sales：公开且本人负责 | Sales：公开且他人负责 | Manager |
|---|---:|---:|---:|---:|---:|
| 在客户列表看到 | 是 | 否 | 是 | 是 | 是 |
| 查看客户详情 | 是 | 否 | 是 | 是 | 是 |
| 编辑客户资料 | 是 | 否 | 是 | 否 | 是 |
| 修改公开/私有设置 | 是 | 否 | 是 | 否 | 是 |
| 修改客户负责人 | 否，提交后由 Manager 处理 | 否 | 否，提交后由 Manager 处理 | 否 | 是 |
| 创建客户 | 是，默认 Private | 是，不能代他人创建 | 是，可选择 Public | 是，不能代他人创建 | 是 |
| 删除客户 | 否 | 否 | 否 | 否 | 是 |
| 查看关联联系人 | 是 | 否 | 是 | 是 | 是 |
| 编辑关联联系人 | 是 | 否 | 是 | 否 | 是 |

说明：Sales 创建客户时负责人必须是本人；Manager 可以指定任意有效的 Sales 负责人。若后续增加 Account Team，本矩阵中的“共享成员”可作为额外例外范围。

## 5. 功能需求

### FR-01 客户权限字段

在 Account/Customer 增加持久化字段：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `visibility` / `custom_crm_visibility` | Select | `Private` | 可选值：`Private`、`Public` |

后端 DTO、创建接口、更新接口、详情接口和列表接口均需返回该字段。数据库已有客户迁移时，所有存量客户默认设为 `Private`，避免上线后意外扩大可见范围。

### FR-02 创建客户

- Sales 创建客户时，权限设置默认为 `Private`。
- Sales 可将新客户设置为 `Public`，但负责人必须是当前 Sales。
- Manager 可选择负责人和权限设置。
- 创建成功后记录创建人、负责人、权限设置和时间。

### FR-03 编辑客户

- 私有客户：只有负责人和 Manager 可查看；只有负责人和 Manager 可编辑。
- 公开客户：所有 Sales 可查看；只有负责人和 Manager 可编辑。
- Sales 不得通过请求参数伪造负责人、用户 ID 或 visibility 绕过校验。
- Sales 不得直接修改客户负责人；Manager 可修改。
- 客户从 Private 改为 Public 时立即生效；从 Public 改为 Private 时立即撤销其他 Sales 的访问。

### FR-04 客户列表与搜索

- 列表、分页、搜索、城市筛选和分部筛选只能返回当前用户有权查看的客户。
- 私有客户对无权 Sales 不应通过搜索、详情 URL、导出或接口响应泄露名称、负责人、城市、规模等信息。
- 公开客户对所有 Sales 可见，并显示当前负责人和“公开”标识。

### FR-05 关联数据继承

- Contact 必须继承所属 Account 的记录权限，不单独按 Contact Owner 决定可见范围。
- Site、客户文件等 Account 关联资料默认继承 Account 的查看范围。
- 私有 Account 的 Contact、Site、客户文件仅负责人和 Manager 可查看/编辑。
- 公开 Account 的 Contact、Site、客户文件对其他 Sales 全量可读，但默认不可编辑。
- 公开 Account 下的 Opportunity、Booking、Visit、Demo、Evaluation、Quotation 等业务关联信息对其他 Sales 全量可读，但默认不可编辑；写入仍需满足各对象的负责人权限。

### FR-06 Manager 全量权限

Manager 无论 Account 为 Private 还是 Public，均可：

- 查看全部客户及全部关联数据；
- 创建、编辑、删除客户；
- 修改负责人和 visibility；
- 处理 Sales 的负责人转移申请；
- 查看权限变更审计记录。

### FR-07 Dashboard 聚合必须读取全部作用域分页

**优先级**：P0  
**关联文件**：`backend/apps/rayher_crm/rayher_crm/services/dashboard.py`、`backend/apps/rayher_crm/rayher_crm/services/pipeline.py`

#### 问题描述

当前 Dashboard 先通过 `list_accounts({"pageSize": 200})` 获取客户 ID，再用这些 ID 过滤 Pipeline、Demo Request、Evaluation 和 Visit。Sales 或 Manager 可见 Account 超过 200 条时，只读取第一页，后续客户及其业务记录不会进入聚合范围，造成 KPI、漏斗、分布和 Top Account 结果静默少算。Demo Request、Evaluation、Visit 当前也只读取第一页 200 条。

`services/pipeline.py` 已存在 `_read_all_pages` 模式，Dashboard 应复用同样的分页读取原则。

#### 修复要求

- 新增或复用统一的“读取全部分页”辅助函数：先读取第 1 页，依据 `total` 计算页数，再依次读取后续页面，合并为完整的当前权限作用域快照。
- Dashboard 聚合前，Account 必须读取全部符合 segment 条件且当前用户有权访问的记录。
- Demo Request、Evaluation、Visit 必须读取全部当前用户有权访问的记录，再按 Account ID 过滤。
- Pipeline 和 Booking 继续使用 `list_pipeline({})` 的全分页结果，不得重新引入单页截断。
- 分页读取必须保留服务端权限过滤；不能通过提高单次 `pageSize` 绕过分页上限，也不能在前端补算。
- 保持现有返回结构不变，修复仅改变聚合数据的完整性。

#### 受影响的聚合结果

- `kpis`：Open Pipeline、Weighted Pipeline、Confirmed Booking、Cumulative Won、待处理 Demo、活跃 Evaluation；
- `funnel`：阶段金额、加权金额和数量；
- `ownerPerformance`：Sales 维度的 Pipeline、Booking；
- `topAccounts`：客户维度的 Pipeline、Booking；
- `segmentDistribution`、`regionDistribution`、`tierDistribution`、`riskDistribution`；
- `bookingByMonth`、`process` 下的 Demo、Evaluation、Visit 统计；
- Dashboard 上依赖上述数据的图表和排行榜。

#### 性能与一致性要求

- 单次 Dashboard 请求应在同一请求上下文内读取数据快照，避免分页过程中出现明显的跨页数据不一致。
- 继续使用当前每页最多 200 条的限制，避免一次请求返回过大结果。
- 当总数为 0、恰好 200、超过 200 或跨越多个页面时，结果均应正确。
- 读取失败时返回明确错误，不得返回看似成功但被截断的聚合结果。

### FR-08 Private 变更后的文件访问撤销

**优先级**：P0

- 文件下载不得使用绕过权限的永久静态 URL。每次下载必须由服务端根据文件所属 Account 重新执行 Account 访问判定。
- 文件下载令牌必须绑定 `fileId`、`accountId`、授权用户和过期时间，默认短时有效；令牌不能跨 Account 或跨用户复用。
- Account 从 Public 改为 Private 后，其他 Sales 的既有下载令牌立即失效；已生成的预览地址也必须在服务端再次校验，不能仅依赖前端隐藏入口。
- 文件元数据列表、预览、下载、批量下载和导出均需执行相同权限检查。
- 禁止把私有客户文件复制到无鉴权的公共目录、CDN 或浏览器长期缓存；响应应设置合理的禁止缓存策略。
- Manager 不受 Private/Public 限制，但仍需通过受控下载接口访问文件并记录审计日志。

### FR-09 Dashboard 与导出必须复用 Account 权限范围

**优先级**：P0

- Dashboard 的所有 KPI、图表、排行榜和分布必须先建立当前用户可见的完整 Account ID 集合，再聚合关联业务数据。
- Dashboard 中的 Account、Contact、Opportunity、Booking、Demo、Evaluation、Visit、Quotation 和文件统计不得调用未带权限条件的全局查询。
- 所有导出接口（Account、Contact、Opportunity、Booking、Visit、文件元数据及报表）必须复用同一套服务端 Account scope 判定和全分页读取逻辑。
- 导出结果的总数、分页总数、文件名和汇总金额也不得包含当前用户无权访问的 Private Account 信息。
- 当 Account visibility 在聚合或导出过程中发生变化时，以请求开始时的权限快照为准；下一次请求必须按新权限重新计算。

### FR-10 关联对象强制继承 Account 权限

**优先级**：P0

- Contact、Site、客户文件、Opportunity、Booking、Visit、Demo、Evaluation、Quotation 等关联对象必须通过关联的 `accountId/account` 解析父 Account，再执行 Account 权限检查。
- 关联对象自身的 owner 权限只能收紧权限，不能扩大对 Private Account 的访问范围。
- Public Account：所有 Sales 可读全部关联业务信息；仅关联对象负责人和 Manager 可写。
- Private Account：仅 Account 负责人和 Manager 可读写关联对象；Engineer 继续受现有分配范围约束。
- 所有单条详情、列表、搜索、批量读取、批量写入、导出、文件预览和下载接口必须执行继承校验。
- 创建或更新关联对象时，服务端必须校验其 `accountId` 与实际父 Account 一致；禁止通过伪造 accountId、contactId 或动态链接把记录挂到其他客户下。
- 删除、归档、合并和迁移 Contact 等操作同样必须先校验父 Account 权限；禁止只按 Contact Owner 放行。

## 6. 前端交互要求

### 6.1 客户创建/编辑表单

增加“访问权限”选择控件：

- `私有：仅负责人和 Manager 可见`（默认）
- `公开：所有 Sales 可见，其他 Sales 只读`

Sales 编辑他人客户时不显示编辑入口；Manager 可完整编辑。创建表单中负责人字段对 Sales 固定为当前用户，对 Manager 可选择。

### 6.2 列表与详情

- 客户列表增加权限状态列或标签：`私有` / `公开`。
- 无权私有客户不出现在列表、搜索结果、统计数字和客户选择器中。
- 公开客户详情显示负责人，但不显示编辑入口给非负责人 Sales。
- 无权限访问详情时返回统一的无权/不存在提示，不暴露客户是否存在。

## 7. 后端与接口要求

### 7.1 访问判定

建议统一使用以下规则：

```text
Manager                         -> 全部 Account
Sales + account.owner == user   -> 可读写
Sales + visibility == Public    -> 只读
其他情况                         -> 无权访问
Engineer                        -> 沿用现有 assigned account 规则
```

所有列表、详情、关联查询、导出、文件下载和写入接口必须调用同一套服务端判定，不允许仅在前端过滤。

### 7.2 写入校验

- `visibility` 必须校验为合法枚举值。
- Sales 写入 Account 时只能使用本人作为 owner。
- Sales 修改 Account 时必须是 owner；Manager 可修改任意 Account。
- 非负责人 Sales 对 Public Account 的编辑、负责人变更、删除请求统一返回 `SCOPE_DENIED` 或 `PERMISSION_DENIED`。
- 返回错误不得包含私有客户的敏感字段。

### 7.3 审计日志

至少记录以下事件：

- 客户创建；
- visibility 从 Private/Public 的变更；
- 客户负责人变更；
- Manager 删除客户；
- 越权访问或写入拒绝。

审计字段包括：操作者、客户 ID、旧值、新值、操作时间、请求 ID、结果。

## 8. 数据迁移与兼容

1. 新增 visibility 字段，默认值为 `Private`。
2. 为所有存量 Account 回填 `Private`。
3. 前端旧数据没有 visibility 时按 `Private` 读取。
4. Mock API 与 Frappe 后端保持相同判定规则和错误码。
5. 迁移完成后验证：Sales 之间私有客户不可互见，Manager 仍可查看全部客户。

## 9. 验收标准

### AC-01 默认私有

Sales A 创建客户且不修改权限设置，客户为 Private。Sales B 无法在列表、搜索、详情、客户选择器或导出中看到该客户。

### AC-02 公开可见

Sales A 将客户设为 Public 后，Sales B 可以在列表中看到并查看客户详情，但不能编辑客户资料、联系人或负责人。

### AC-03 权限撤销

Public 客户改回 Private 后，Sales B 立即无法继续访问客户详情、联系人、文件和关联数据。

### AC-04 Manager 全量权限

Manager 可以查看、编辑、删除任意 Private/Public 客户，并可修改负责人和 visibility。

### AC-05 越权接口防护

Sales B 直接调用 Account、Contact、Site、文件和导出接口访问 Sales A 的 Private 客户时，服务端拒绝请求，不返回客户敏感信息。

### AC-06 负责人约束

Sales 不能创建负责人为其他 Sales 的客户，也不能直接修改客户负责人；Manager 可以完成上述操作。

### AC-07 数据一致性

Mock API、Frappe API、前端列表、详情页和 Dashboard 对 Private/Public 的可见结果一致。

### AC-08 Dashboard 全分页聚合

构造超过 200 个 Account 的 Manager 数据集，且第 201 个及之后的 Account 存在商机、Booking、Demo Request、Evaluation 和 Visit。Dashboard 的 KPI、漏斗、分布、Top Account 和流程统计必须包含这些记录。

### AC-09 角色作用域下的全分页聚合

Sales 只能在其有权访问的 Account 及关联记录范围内聚合；超过 200 条时仍需完整统计，不能读取其他 Sales 的 Private Account。

### AC-10 多页边界

分别验证 0、1、200、201、400 条 Account/关联记录，聚合数量和金额与完整数据集逐条计算结果一致。

### AC-11 回归验证

验证 `services/pipeline.py` 的全分页读取继续生效，Dashboard 不得因修复 Account、Demo、Evaluation、Visit 分页而改变现有 Pipeline、Booking 的权限范围或返回字段结构。

### AC-12 文件访问撤权

Sales A 将 Account 设为 Public，Sales B 获取联系人文件列表并下载文件；Account 改回 Private 后，Sales B 使用旧文件 URL、旧下载令牌、预览地址和批量下载接口均被拒绝，且不返回文件内容或元数据。Manager 仍可正常访问并产生审计记录。

### AC-13 Dashboard 与导出作用域一致

为 Sales A、Sales B 分别准备 Private/Public Account 及关联业务数据。两人的 Dashboard、Account/Contact/Opportunity 导出结果必须与各自完整可见 Account 集合逐条计算一致；任何总数、金额、排行榜或导出文件都不能包含对方的 Private Account。

### AC-14 关联对象继承 Account 权限

Sales B 通过直接 ID、搜索、批量接口、详情 URL、导出和文件接口访问 Sales A 的 Private Account 下的 Contact、Site、Opportunity、Booking、Visit、Demo、Evaluation、Quotation，全部被拒绝。Account 改为 Public 后，Sales B 可读全部关联信息但不能写入。

### AC-15 关联关系防篡改

提交伪造的 `accountId`、`contactId`、动态链接或跨客户关联参数时，服务端返回校验错误或 `SCOPE_DENIED`，不得创建或更新跨 Account 的关联记录。

## 10. 发布与风险

### 发布顺序

1. 后端字段和权限判定；
2. 存量数据回填 Private；
3. Mock API 和自动化测试同步；
4. 前端表单、列表、详情和错误状态；
5. Manager/Sales 双角色 UAT；
6. 生产发布后检查审计日志和权限拒绝指标。

### 主要风险

| 风险 | 应对措施 |
|---|---|
| 存量客户默认私有导致 Sales 看不到原有客户 | 上线前由 Manager 批量将确需共享的客户改为 Public |
| 关联数据接口遗漏权限校验 | 以 Account 为入口覆盖详情、文件、导出和所有关联接口测试 |
| 前端显示与后端权限不一致 | 将服务端权限测试作为发布门禁 |
| Public 被误解为可编辑 | 在表单和标签中明确“公开可见，其他 Sales 只读” |
| Private 变更后旧文件链接继续有效 | 下载接口每次校验 Account scope，令牌短时有效并可按 Account/用户撤销 |
| Dashboard 或导出使用全局查询 | 统一使用 scoped read model 和全分页 helper，并增加角色隔离对账测试 |
| 关联对象绕过 Account 继承权限 | 所有子对象先解析父 Account，再执行统一 scope 校验；禁止只按子对象 owner 放行 |

## 11. 本期决策待确认

- Public 是否允许其他 Sales 编辑：本 PRD 默认 **不允许**。
- 是否需要在本期实现指定 Sales 的定向共享：本 PRD 暂不实现，后续可通过 Account Team 扩展。
- 是否允许 Sales 提交负责人转移申请：本 PRD只定义 Manager 直接转移，申请流程可作为后续需求。
