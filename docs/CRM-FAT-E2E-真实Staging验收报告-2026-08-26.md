# CRM FAT E2E 真实 Staging 验收报告

**测试日期**：2026-08-26  
**系统**：PLANCK CRM / rayher_crm  
**目标环境**：staging  真实 Frappe runtime  
**构建版本**：`v15-staging-9ab287c`  
**报告结论**：**部分通过，暂不满足 Product 发布条件**

## 1. 证据口径

本报告将测试证据分为三类，避免混淆：

| 证据类型 | 环境 | 可证明内容 | 是否作为 staging UI 证据 |
|---|---|---|---|
| 真实浏览器验收 | staging Frappe 构建 | 登录身份、页面访问、筛选、深链、真实数据展示 | 是 |
| API / 服务层验收 | staging 后端 | 权限、状态链、分页、业务关联和数据过滤 | 是 |
| 前端 Vitest / Mock adapter | 本地测试运行时 | 组件交互、页面逻辑、回归行为 | 否，仅作自动化回归证据 |

此前出现的“演示员工24 / 销售经理”页面属于 Mock 默认身份，不纳入本报告的 staging 权限结论。

## 2. 测试数据

本轮 staging 数据使用统一前缀，验收期间保留，不执行无条件全表删除：

- `E2E26-0826-A-CIS-20260826194704`
- `E2E26-0826-B-PKG-20260826194704`
- `E2E26-0826-C-SVC-20260826194704`
- `E2E26-0826-D-SELF-20260826194704`
- `E2E26-0826-E-LOSS-20260826194704`
- RFQ：`E2E26-0826-RFQ-92f33dc2`

RFQ 关键记录：`CRM-RFQ-00166`，关联 Opportunity `CRM-OPP-00165`。

## 3. 自动化测试结果

### 3.1 后端 Frappe 隔离测试栈

- Compose project：`rayher-crm-e2e-20260826`
- Site：`rayher-crm-e2e-20260826.test`
- 覆盖：43 个测试文件、253 个测试方法
- 结果：`Ran 253 tests ... OK`
- 退出码：`0`
- 说明：使用一次性隔离测试库，未把 staging 业务库作为后端测试库。

### 3.2 前端自动化

- Vitest：106 files / 689 tests passed
- 相关回归测试：3 files / 48 tests passed
- `vue-tsc --noEmit`：通过
- Python 编译检查：通过
- 说明：这些测试使用本地 Mock adapter 或服务层模拟，不替代真实 staging 浏览器验收。

## 4. 真实 staging API / 服务层验收

### 4.1 RFQ 状态链

按业务门禁完成：

`Opportunity -> 设备规格确认 -> Sales Upload -> Engineer Comment -> Manager Approve -> 报价`

验证结果：

- RFQ `CRM-RFQ-00166` 最终状态为 `Approved`。
- `opportunityId` 筛选只返回对应 Opportunity 的 RFQ。
- 非法 Opportunity ID 被拒绝，不泄漏其他客户数据。
- Opportunity 自动推进到“报价”阶段。
- Engineer 可预览 PDF，不可下载原始文件。

**结果：通过。**

### 4.2 Contact 360 -> Demo Request 深链

- `list_demo_workflows(contactId=...)` 已消费 `contactId` 并按 `CRM Demo Request.primary_contact` 精确过滤。
- A-CIS 联系人在线查询返回 `DEMO_TOTAL=1`，唯一记录为 `CRM-DR-00123`。
- 分页元数据保持正确。
- 不存在或无匹配联系人返回标准空结果。

**结果：通过。**

### 4.3 角色权限服务层

| 模块 | Manager | Sales | Engineer |
|---|---:|---:|---:|
| Account | 3 | 3 | 0 |
| Contact | 5 | 5 | 拒绝 |
| Lead | 4 | 2 | 0 |
| Opportunity | 2 | 1 | 0 |
| Quotation | 5 | 3 | 拒绝 |
| Booking | 2 | 2 | 0 |
| Visit | 2 | 1 | 拒绝 |
| Demo Request | 3 | 1 | 3 |
| Evaluation | 2 | 1 | 2 |
| Controlled Document | 2 | 2 | 2 |

Engineer 对 Contact、Quotation、Visit 的拒绝符合权限边界；Account、Contact、Booking 当前数据量不足以证明 Sales owner 隔离。

## 5. 真实 staging 浏览器验收

### 5.1 Manager 会话

访问入口：`http://127.0.0.1:44174/login?redirect-to=%2Fcrm`  
身份：`演示员工21 / Manager`  
页面运行时：真实 Frappe runtime，非 Mock。

| 功能 | 操作 | 结果 |
|---|---|---|
| Dashboard | 查看五组 E2E 客户数据 | 通过 |
| Account 筛选 | 业务领域=CIS，显示 `1 个客户` | 通过 |
| Account 重置 | 点击“重置条件”，恢复 `9 个客户` | 通过 |
| Leads 筛选 | 状态=Qualified，显示 `6 条 Leads` | 通过 |
| Leads 重置 | 点击“重置条件”，恢复 `19 条 Leads` | 通过 |
| Contact 360 | Demo Requests 入口 URL 含 `contactId` | 通过 |
| Contact 360 空结果 | 无匹配时显示“没有匹配的 Demo Request” | 通过 |
| RFQ Center | `CRM-RFQ-00166` 显示 Approved、三步工作流 Completed | 通过 |

### 5.2 Sales 会话

旧的 Sales 浏览器样本使用过 Mock 构建，不能作为当前 staging 证据。Sales 需要在 `v15-staging-9ab287c` 入口重新登录并完成至少一个真实业务流程后，才可关闭该项。

**结果：待补测。**

### 5.3 Engineer 会话

Engineer 的服务层权限已验证，但尚未取得可用的真实 Engineer 浏览器会话。此前独立浏览器连接曾因端口丢失跳转到无端口 `/crm`，该问题属于 URL/网络链路阻塞，不能误判为账号权限失败。

待补测范围：Demo、Evaluation、RFQ 可访问范围；Contact、Visit、Quotation、Booking 的标准无权限状态；Engineer Review、Comment、Evaluation 操作。

**结果：环境阻塞 / 待补测。**

## 6. 部署与健康检查

- 部署前备份：`backups/pre-update-9ab287c-20260826-124754`
- 应用、数据库、Redis、ClamAV 容器均 healthy。
- `/api/method/ping` 返回 HTTP 200。
- `/crm` 返回 HTTP 301 登录重定向。
- 浏览器当前通过 SSH 隧道访问：`127.0.0.1:44174 -> 203.0.113.58:4174`。

## 7. 遗留问题与发布门槛

| 项目 | 当前结果 | Product 影响 |
|---|---|---|
| 后端 43 文件 / 253 方法 | 通过 | 无 |
| 前端 689 测试 | 通过，但为 Mock/自动化证据 | 无法替代 UI 验收 |
| RFQ 状态链 | 通过 | 无 |
| Contact 360 Demo 深链 | 通过 | 无 |
| Manager 真实浏览器 | 通过已覆盖项 | 无 |
| Sales 真实浏览器 | 待补测 | 发布前必须完成 |
| Engineer 真实浏览器 | 环境阻塞 / 待补测 | 发布前必须完成 |
| 测试账号清理 | 未执行 | 发布前必须禁用或删除 |
| 测试数据清理 | 未执行 | 发布前按前缀精确清理并复查 |

Product 发布前必须：

1. 使用真实 Sales、Engineer 账号完成浏览器流程。
2. 禁用或删除专用系统测试账号，移除其角色并复查 Comment `@` 提及成员。
3. 反向依赖顺序精确清理 `E2E26-0826-` 和 RFQ 前缀数据。
4. 复查 Customer、Contact、Lead、Opportunity、Visit、Demo Request、Evaluation、Quotation、Booking、Installed Tool、RFQ 无前缀残留。

## 8. 最终结论

后端隔离测试、前端自动化、RFQ 状态链、Contact 360 深链和 Manager 真实 staging 浏览器验收均已有可复现证据并通过。由于 Sales 真实浏览器流程尚未重测，Engineer 浏览器流程仍受连接/会话条件限制，且测试账号和测试数据尚未执行发布前清理，本轮整体结论为：

**部分通过，不得标记为 Product 发布前全量通过。**

