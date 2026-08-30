# CRM FAT 全量 QA / Playwright E2E 总结

**测试日期**：2026-08-27  
**系统**：PLANCK CRM / `rayher_crm`  
**环境**：staging，真实 Frappe runtime  
**入口**：`http://203.0.113.58:4174`（本轮 Playwright 通过 staging 会话访问）  
**结论**：**部分通过，核心业务链通过；不满足 Product 发布前全量放行条件**

## 1. 证据范围与口径

本报告将证据分为三层：

| 层级 | 方式 | 本轮用途 |
|---|---|---|
| L1 | Playwright 浏览器 UI | 真实登录身份、页面访问、表单提交、状态变化、列表与看板展示 |
| L2 | staging API / service | 权限、分页、关联、状态门禁和深链参数消费 |
| L3 | 本地 Vitest、类型检查、Python 编译、Frappe 隔离测试 | 回归和代码级验证，不替代真实浏览器验收 |

浏览器中出现的 `演示员工24 / 销售经理` Mock 身份不纳入 staging 结论。本报告中的 staging UI 证据均以页面实际显示的 Frappe 登录身份为准。

## 2. 测试数据与账号

### 2.1 测试数据

验收数据统一使用以下前缀，测试期间保留以便审计：

- `E2E26-0826-A-CIS-20260826194704`
- `E2E26-0826-B-PKG-20260826194704`
- `E2E26-0826-C-SVC-20260826194704`
- `E2E26-0826-D-SELF-20260826194704`
- `E2E26-0826-E-LOSS-20260826194704`
- RFQ 测试账号/客户前缀：`E2E26-0826-RFQ-92f33dc2`

本轮新增或推进的关键记录：

| 业务对象 | 编号 | 最终状态 |
|---|---|---|
| Demo Request | `CRM-DR-00176` | Demo Test 主链完成 |
| Evaluation | `CRM-EVAL-00182` | Demo Test 主链完成 |
| Test Run | `CRM-RUN-00190` | Test Execution 完成 |
| RFQ | `CRM-RFQ-00166` | Approved |
| Opportunity | `CRM-OPP-00165` | 报价 |
| Quotation | `CRM-QTN-00198` / `PK20260827-A2` | Published / Approved |
| Booking | `CRM-BKG-00210` | Confirmed |

### 2.2 角色

- Manager：演示员工21
- Sales：演示员工155（此前真实 staging 浏览器补测）
- Engineer：演示员工158（此前真实 staging 浏览器补测）

不在报告中保存账号密码、Cookie、Token 或登录态文件。

## 3. 今日 Playwright 真实浏览器结果

### 3.1 Manager：报价审批与发布

**页面**：Quotation 列表及 `PK20260827-A2` 详情页。  
**身份证据**：页面右上角显示 `演示员工21 / Manager`。

验证内容：

1. Quotation 列表可看到测试报价 `PK20260827-A2`。
2. 详情页显示客户、Device 类型、版本 V1、金额 CNY 1,880,000.00。
3. 发布后状态为 `Published`，审批状态为 `Approved`。
4. 审批历史显示 `Approved for E2E FAT`。
5. ATTN、Site、付款比例等发布前门禁已在此前回放中验证：缺少 ATTN 或 Site 时提交返回 422；补齐后才进入审批。
6. PDF 预览 iframe 加载成功，下载/预览入口可见。

**结果：通过。**

### 3.2 Manager：Booking 新建与确认

**页面**：Booking 列表、新增 Booking、编辑 Booking。  
**业务类型**：Upsell / Equipment。

实际操作：

1. 新建 Booking，选择客户 `E2E26-0826-D-SELF-20260826194704`。
2. 选择联系人 `E2E26-0826-D-SELF-20260826194704 buy`（页面最终记录为该客户的 `buy` 联系人）。
3. 设备需求填写 `E2E-FAT-Device`，数量 1。
4. 客户 DDL 为 `2026-09-30`，金额为 CNY 1,880,000.00。
5. 备注为 `E2E FAT Manager Booking`，先保存为 `Pending`。
6. 列表新增 `CRM-BKG-00210`，客户、联系人、设备、金额、DDL 和 Owner 均展示正确。
7. 编辑同一记录，将状态从 `Pending` 更新为 `Confirmed`。
8. 列表最终显示 `Confirmed`，Confirmed 金额看板同步增加。

**结果：通过。**

> 注：本轮后续已补测合法 Won Opportunity 来源路径。当前仓库中的 Playwright 快照未保留该条记录编号，需从 staging 操作日志或会话导出补录。

### 3.3 Visit 全流程补测

根据本轮 staging Playwright 回放结果，Visit 已完成新建、Customer/Contact 关联、拜访记录填写、Sales 提交、Manager 审核、Calendar 联动以及取消/异常分支验证。

**结果：已补测通过（用户确认）。** 当前工作区未找到包含 Visit 编号和最终状态的 Playwright 快照，审计归档时应补存该快照或请求响应。

### 3.4 Installed Tools 生命周期补测

已从 Completed Booking 转入 Installed Tool，并按顺序完成：

`FAT -> Shipment -> Installation -> SAT -> Warranty`

已验证阶段不可跳级、不可回退或重复完成；每次推进后看板和详情时间轴同步；Manager 与已分配 Engineer 可操作，Sales 和未分配 Engineer 无推进权限；Warranty 完成后不再显示下一阶段按钮。

**结果：已补测通过（用户确认）。** 当前工作区未找到该条 Installed Tool 序列号和五次推进快照，需在 QA 归档中补录。

### 3.5 Booking Opportunity 来源补测

已使用合法 Won Opportunity 创建 Booking，未绕过 Won 门禁。已验证 Booking 正确带出 Opportunity、Customer、Contact，报价和 Booking 金额一致，Opportunity/Quotation/Booking 状态联动正确，且 Manager、Sales 与无权限角色的操作范围符合预期。

**结果：已补测通过（用户确认）。** 当前仓库未保留该条 Booking、Won Opportunity 和关联 Quotation 的具体编号，需从 staging 操作记录补录。

## 4. 历史真实 staging Playwright 结果

### 4.1 Sales

- 真实 staging 登录身份为 `演示员工155 / Sales`。
- Leads：状态筛选、结果数量和“重置条件”可用。
- Account：业务领域筛选、数量变化和“重置条件”可用。
- Contact 360：Demo Requests 入口带 `contactId`，无匹配联系人显示标准空结果。
- 禁止范围和可编辑范围与 Sales 权限矩阵一致。

**结果：已覆盖项通过。**

### 4.2 Engineer

- 真实 staging 登录身份为 `演示员工158 / Engineer`。
- Demo Request、Demo Test / Evaluation、RFQ Center 可访问。
- Engineer Review、Comment、Evaluation 相关操作入口可见。
- Contact 显示标准无权限状态；Visit、Quotation、Booking 等禁止模块隐藏或直达后回到 Dashboard。
- Installed Tools 可访问分配设备 `CRM-SN-00142`。

**结果：已覆盖项通过。**

### 4.3 Opportunity、RFQ、Contact 360、分页

- `CRM-OPP-00165` 最终阶段显示“报价”，不再停留在说明性文字。
- RFQ `CRM-RFQ-00166` 按门禁完成 Sales Upload、Engineer Comment、Manager Approve，最终 Approved。
- RFQ 批准后 Opportunity 自动推进到“报价”。
- Contact 360 -> Demo Request 深链消费 `contactId`，列表只返回该联系人的 Demo Request。
- 不存在或无匹配联系人返回标准空结果；分页元数据保持正确。
- 多个模块筛选后的右侧操作统一显示“重置条件”。

## 5. Demo Request / Evaluation 主链

真实 staging 已完成以下成功链：

`Sales Preparation -> Engineer Review -> Manager Approval -> Demo Test`

Wafer Test 子链：

`Wafer Preparation -> Test Preparation -> Test Execution -> Internal Review -> Customer Review -> Accept Demo`

已验证：

- Engineer “确认可做”和 Manager 审批接口返回成功。
- 缺少测试报告或 Test Run 时，“完成 Test Execution”正确禁用。
- Internal / External 报告上传成功，测试模板为 `public/templates/demo-request-form-v2.docx`。
- 新增 Test Run 成功，Test Execution、Internal Review、Customer Review、Accept Demo 均成功。
- Accept 后进行中项目数量正确减少。

### 5.1 异常与权限分支

本轮已使用独立测试记录和对应角色完成异常回放：

| 场景 | 验证动作 | 结果 |
|---|---|---|
| Engineer 退回 | Engineer 选择“退回 Sales”并填写退回原因 | 状态回到 Sales Preparation，Sales 可继续修改 |
| Manager 驳回 | Manager 选择驳回并填写审批意见 | 状态回到 Sales Preparation，未生成可执行 Evaluation |
| Reject Demo | 对进行中的 Demo 执行 Reject Demo | Demo 进入拒绝终态，进行中看板数量同步减少 |
| 缺少报告或 Test Run | 在缺少必需报告/Test Run 时尝试完成 Test Execution | 操作按钮禁用，未发生状态变更 |
| 无权限操作 | 使用非当前负责人或禁止角色尝试 Review、Approve、Reject | 页面不显示操作入口或服务端返回权限错误，数据未被修改 |

**结果：主成功链和异常/权限分支均已补测通过（用户确认）。** 当前仓库未找到这些异常记录的完整编号和逐步快照，归档时需补存以形成可审计证据。

## 6. API、服务层和自动化补充证据

### 6.1 后端隔离测试

- 独立测试站点：`rayher-crm-e2e-20260826.test`
- 覆盖：43 个测试文件、253 个测试方法
- 结果：`Ran 253 tests ... OK`
- 退出码：0
- 测试库与 staging 业务库隔离。

### 6.2 前端与静态检查

- Vitest：106 files / 689 tests passed
- 重点回归：3 files / 48 tests passed
- `vue-tsc --noEmit`：通过
- Python 编译检查：通过

这些结果证明代码和服务层回归通过，但不能单独证明真实角色浏览器流程全部完成。

### 6.3 健康检查与部署

- `/api/method/ping`：HTTP 200
- `/crm`：HTTP 301 登录重定向
- 应用、数据库、Redis、ClamAV 容器：healthy
- Contact 360 深链修复构建：`v15-staging-9ab287c`

## 7. 结果矩阵

| 范围 | 结果 | 证据级别 | 发布影响 |
|---|---|---|---|
| Demo 主成功链 | 通过 | L1 + L2 | 无 |
| Demo 异常与权限分支 | 已补测通过（用户确认） | 真实 UI 回放；异常记录快照待归档 | 需补齐审计附件 |
| RFQ 状态链 | 通过 | L1 + L2 | 无 |
| Quotation 门禁、审批、发布 | 通过 | L1 + L2 | 无 |
| Booking Upsell 新建 Pending | 通过 | L1 | 无 |
| Booking Pending -> Confirmed | 通过 | L1 | 无 |
| Booking Opportunity 来源 | 已补测通过（用户确认） | 真实 UI 回放；编号快照待归档 | 需补齐审计附件 |
| Contact 360 Demo 深链 | 通过 | L1 + L2 | 无 |
| Sales 页面与筛选 | 已覆盖项通过 | L1 | 无 |
| Engineer 页面与禁止模块 | 已覆盖项通过 | L1 | 无 |
| Frappe 43 文件 / 253 方法 | 通过 | L3 | 无 |
| Product 前测试账号清理 | 未执行 | 发布控制 | 阻塞 |
| Product 前测试数据清理 | 未执行 | 发布控制 | 阻塞 |

## 8. 仍需补齐的测试项

1. **Visit 全流程**：已补测通过；待归档 Visit 编号和最终快照。
2. **Installed Tools 全流程**：已补测通过；待归档序列号及五阶段推进快照。
3. **Booking Opportunity 来源**：已补测通过；待归档 Won Opportunity、Quotation、Booking 编号。
4. **权限边界扩展**：Sales/Engineer 对每个模块的允许、禁止、直达路由和 owner 隔离。
5. **数据边界**：多页完整翻页、刷新恢复、空结果、无效 ID、跨客户数据泄漏。
6. **自动化套件**：`e2e/crm.spec.ts` 仍需在安全注入真实账号后运行；不能把无凭据跳过描述为全量自动化通过。

## 9. 发布前控制

Product 发布前必须完成以下 Gate：

1. 备份 staging。
2. 禁用或删除专用系统测试账号，移除角色。
3. 复查测试账号未出现在 Comment `@` 提及成员中。
4. 按反向依赖顺序精确清理 `E2E26-0826-`、`E2E-FAT-` 和 RFQ 测试数据。
5. 复查 Customer、Contact、Lead、Opportunity、Visit、Demo Request、Evaluation、Quotation、Booking、Installed Tool、RFQ 均无测试前缀残留。
6. 禁止无条件全表删除，不能影响已有业务数据。

## 10. 最终结论

今天的 Playwright 真实 staging 回放已覆盖并通过 Manager 的报价审批、报价发布、Booking 新建和 Pending -> Confirmed 状态流程；结合此前 Sales、Engineer、Demo、RFQ、Contact 360 和分页筛选证据，CRM 核心 FAT 链路具备可复现通过结果。

Visit、Installed Tools 完整状态链、Booking Opportunity 来源以及 Demo 异常/权限分支均已完成补测（用户确认），但这些补测的可审计记录编号和快照尚未全部归档；扩展权限隔离和 Product 发布前清理仍需完成。由于真实账号自动化套件尚未在本轮用凭据全量回放，仍不能称为“全量自动化 E2E 通过”。最终判定保持：

**部分通过；核心业务链通过；在剩余项目补测并完成账号/数据清理前，不得发布 Product。**
