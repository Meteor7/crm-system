# RAYHER CRM P0/P1 后端与数据库设计

**日期：** 2026-07-20  
**状态：** 已由用户授权按推荐方案实施  
**依据：** `semiconductor-crm-implementation-plan.md`、P0 领域决策、现有 Vue API 契约  
**范围：** 本地 Docker 开发环境；不包含 Staging 或生产部署

## 1. 目标与交付边界

本轮交付一个运行在 `http://localhost:2223` 的单 Site Web 系统。系统安装 Frappe v16、ERPNext v16 和自定义 `rayher_crm` App，使用 MariaDB 保存真实业务数据，使用 Frappe Session、CSRF、权限、Workflow、私有文件、队列和审计能力。现有 Vue 前端作为登录后的 RAYHER CRM 工作台运行。

本轮只落地实施 Plan 的 P0/P1：

- 共享主数据、编码、角色、权限、审批与审计基础。
- 核心 Sales CRM。
- Demo Request、Wafer Sample、Demo Execution、Test Run 和 Demo Conclusion。
- Controlled Documents MVP，包括目录可见、内容访问、访问申请、私有文件、水印 PDF 和下载审计。
- 最小版 Installed Tool。
- P0/P1 前端页面接入真实 Frappe API。

Field Service、Procedure Run、智能排期、客户门户和离线文档包不在本轮实施，但数据模型保留后续关联字段。

## 2. 技术架构

### 2.1 版本与容器

- 固定镜像：`frappe/erpnext:v16.28.0`，不使用 `latest` 或浮动 `v16` 标签。
- 自定义镜像：在固定 ERPNext 镜像中安装本项目 `rayher_crm` Python App。
- Site：`rayher.localhost`。
- App：`rayher_crm`。
- 入口：宿主机 `localhost:2223` 映射到 Frappe frontend 容器。
- 时区：`Asia/Shanghai`。
- 数据库：MariaDB，UTF-8，命名卷持久化。
- 队列：Redis queue/cache、short/default/long worker、scheduler。
- 实时能力：Frappe websocket。
- 文件：Frappe Site 私有文件目录使用命名卷持久化。

### 2.2 本地密钥

数据库 Root 密码和 Administrator 密码由一次性初始化容器随机生成，保存在 Docker 命名卷，不写入源码、文档、Compose 文件或命令输出。管理员密码只在需要登录时复制到本机剪贴板，不在终端或回复中显示。

### 2.3 前端承载

Vue 生产构建由 `rayher_crm` 提供，用户先通过 Frappe 登录，再进入 RAYHER CRM 工作台。前端和 API 同源，不启用跨域；写请求携带 Frappe CSRF Token。生产本地构建固定 `VITE_API_ADAPTER=frappe`，运行时不回退 Mock。

## 3. 主数据复用策略

ERPNext 提供通用主数据和未来服务模块基础：

- Customer、Contact、Address。
- Item、Item Group、Currency。
- User、Employee、Department、Sales Person。
- Contract。
- 后续可复用的 Issue、SLA、Serial No、Maintenance 和 Stock 能力。

`rayher_crm` 只创建半导体销售、Demo、设备生命周期和受控文档专用对象。客户、人员、型号、币种不在业务模块内重复建主档。

## 4. P0 数据与编码

| 对象 | DocType | 唯一规则 |
|---|---|---|
| Customer | ERPNext Customer + 自定义 `rayher_customer_code` | `客户简称-年份-三位序号`，唯一且创建后不可修改 |
| Customer Site | `CRM Site` | `{customer_code}-SITE-{两位序号}` |
| Product / Tool Model | ERPNext Item + 自定义 Tool Model 字段 | 正式型号全局唯一 |
| Opportunity | `CRM Opportunity` | `OPP-YYMM-#####` |
| Demo Request | `CRM Demo Request` | `DEMO-YYMM-#####` |
| Demo Execution | `CRM Demo Execution` | `{demo_request}-EXE-##` |
| Installed Tool | `CRM Installed Tool` | `INST-{serial_number}`，Serial Number 全局唯一且不可修改 |
| Controlled Document | `CRM Controlled Document` | Document ID 全局唯一 |
| Document Version | `CRM Document Version` | `document + version + revision` 组合唯一 |

所有关键对象保留 Frappe 标准创建人、创建时间、修改人、修改时间，并对审批人、审批时间和状态变化建立显式审计记录。

## 5. 角色与数据范围

| 角色 | 范围 | 主要责任 |
|---|---|---|
| CRM Administrator | 全部 | 主数据、字典、权限和异常处理 |
| 管理者权限 | 全部只读 | 驾驶舱、跨团队业务和审计查看 |
| Sales Manager | 本团队 | 商机复核、Demo 最终审批、拜访与 Action 审阅 |
| Sales User | 本人和被分配 Account Team | 客户、商机、Stakeholder、Action、Demo 申请 |
| FAE / Application Engineer | 被分配 Demo、Execution、Test Run 和关联客户 | Scope Review、执行与结果 |
| Document Manager | 被授权文档域 | 发布、作废、Restricted 复核、原始文件访问 |

权限必须同时落实在 DocType Permission、User Permission、Permission Query Condition、`has_permission` 和写 API 状态校验。前端隐藏按钮不构成权限控制。

## 6. Sales CRM 模型

### 6.1 `CRM Site`

关联 Customer，保存 Site/Fab/OSAT 类型、地区、地址、Line/Bay 信息和启用状态。

### 6.2 `CRM Opportunity`

关联 Customer、Site、Owner、Sales Team、来源需求和可选 Demo Request。字段包括：阶段、Forecast Category、Tool Type、Sale Type、Sub Region、原币金额、币种、汇率、人民币报表金额、概率、预计 PO/Shipment/FAT 日期、竞争状态、Win/Lost Reason、Strength、Red Flag、Information Needed、最近更新和阶段进入时间。

Forecast Category 固定为：`Pipeline`、`Best Case`、`Commit`、`Closed`、`Omitted`。

### 6.3 `CRM Opportunity Stakeholder`

Opportunity 与 ERPNext Contact 多对多关联。关联记录保存 Buying Role、Influence、Attitude、Coverage Evidence、Win Result、是否 Coach 和机会内备注，不覆盖 Contact 主档。

### 6.4 `CRM Action`

通用 Action 可关联 Opportunity、Demo Request、Demo Execution、Test Run、Visit、Contract 或 Installed Tool，保存负责人、截止日期、优先级、状态、完成证据和逾期信息。

### 6.5 历史

金额、概率、阶段、Forecast Category 和关键日期变化写入 `CRM Opportunity Change`，供阶段停留和预测变化分析使用。

## 7. Demo 与验证模型

### 7.1 `CRM Demo Request`

保存 Plan 指定的 Company、Contact、Industry、Sales Contact、Demo Owner、Wafer 数量与形态、Material、Specific Request、Detect/Measure、Expected Results、Other Tools、Primary/Complementary Tool、Timing、Success Factors、Internal Questions、Customer Questions、Prepared/Approved 信息。

Workflow：

`Draft → Submitted → Scope Review → Manager Approval → Approved / Rejected / Returned`

固定审批链：Sales 提交 → FAE Scope Review/退回 → FAE 确认 → Sales Manager 批准/拒绝。

### 7.2 `CRM Wafer Sample`

属于 Demo Request。保存 Slot ID、WID、Lot、Specificity、Material、Layer Stack、Thickness、Diameter、Notch/Flat、DOI/Metrology、Result File Required、污染/安全/保密说明和收发/存放/返还/销毁状态。

### 7.3 `CRM Demo Execution`

一个 Demo Request 可有多个 Execution。保存设备、计划/实际时间、执行人员、地点、状态和使用 Wafer 的关联记录。

执行状态：

`Sample Awaiting → Sample Received → Scheduled → Testing → Analysis → Customer Review → Accepted / Rejected / On Hold / Closed`

### 7.4 `CRM Test Run`

必须属于一个 Demo Execution 并引用实际 Wafer Sample。保存 Run ID、Recipe、软件/硬件配置、Capture、False Positive、WPH、结果、原始数据、图像和报告附件。

### 7.5 `CRM Demo Conclusion`

汇总 Execution/Test Run 结论、客户反馈、接受状态和后续 Action。只有完成客户确认的 Conclusion 才允许通过服务方法更新 Opportunity 阶段或 Action。

## 8. Controlled Documents MVP

### 8.1 主档与版本

`CRM Controlled Document` 保存 Document ID、Title、类型、Technical/Commercial 分类、产品/型号/设备/客户/项目关联、Owner 和访问策略。

`CRM Document Version` 保存 Version、Revision、Language、状态、Reviewer、Approver、Effective/Review/Expiry Date、SHA-256 Checksum、私有 File、Current 标志和 Superseded 关联。

发布规则：同一 Document 同时只能有一个 `Released + Current` 版本。新版本发布事务中自动将旧版本标记 Superseded。Obsolete/Superseded 文件不向普通用户提供内容访问。

### 8.2 两层权限

- Catalog Visibility 决定能否看到标题、Document ID、类型、Current Version 和 Owner。
- Content Access 决定能否预览或下载。
- Internal 技术文档目录对员工可见，相关工程角色可直接访问。
- Commercial 目录仅 Sales、Sales Manager、管理者权限和 Document Manager 可见。
- Restricted、价格、合同和客户专属目录仅 Account Team、管理者权限和 Document Manager 可见。

### 8.3 访问申请与下载

`CRM Document Access Request` 状态：

`Requested → Manager Review → Document Review（Restricted 时）→ Approved / Rejected → Active → Expired / Revoked`

获批普通用户默认只能下载服务端生成的 PDF。下载时每页写入下载人姓名/员工代码、时间、Document ID、Version/Revision、保密标记和 Download ID。主文件始终为私有文件，API 不返回永久主文件 URL。每次下载写入 `CRM Document Download Audit`，保存申请、审批、用户、时间、IP、版本、Checksum 和结果。

## 9. Installed Tool MVP

`CRM Installed Tool` 保存不可变 Serial Number、Tool Model、Customer、Site、Line/Bay、来源 Opportunity/Contract、Prequalification/FAT/Shipment/Installation/SAT/Final Acceptance 日期、软件/固件/OS/配置版本、Warranty、PM 周期、状态、最近服务时间和适用 Current Document。

本轮 Ownership Type 只启用 `Customer Sold`，字段保留 `Company Demo` 和 `Rental` 枚举供后续使用；不建设库存、固定资产折旧或完整 Field Service。

## 10. API 契约

- 路径统一在 `/api/method/rayher_crm.api.v1.*`。
- GET 只查询，POST 执行创建、修改、Workflow 和下载。
- 成功响应：`{"data": ..., "meta": ..., "warnings": [...]}`。
- 失败响应含稳定错误代码、用户可读消息、字段错误和 Request ID。
- 列表、详情、聚合和写 API 全部按服务端权限过滤。
- Dashboard 使用自然季度和人民币报表金额实时聚合，不保存重复快照。
- 客户 360 Excel 由后端按当前原型结构生成。

## 11. 初始数据

提供幂等开发种子命令：

- 导入现有 Mock 客户、联系人、Site、需求、商机、Demo、测试、合同、拜访和 Action。
- 导入 CUSTOMER06 Customer 360 Excel 中可映射的数据。
- 导入 P1 Opportunity Strategy、Demo Workflow、Installed Tool 和 Document Center 演示数据。
- 所有记录标记 `is_development_data`，重复执行不重复创建。

## 12. 验收与测试

- Python 单元测试覆盖编码不可变、唯一性、金额换算、状态机、Demo 一对多、文档 Current 唯一、水印和审计。
- 权限测试覆盖六类角色的列表、详情、写入、审批和私有文件访问。
- API 契约测试验证成功/错误格式、Request ID 和 CSRF 写入。
- Vue 测试验证 Frappe Adapter 与 P0/P1 页面契约，不使用运行时 Mock。
- 浏览器烟雾测试覆盖登录、列表、详情、Demo 审批、Test Run、Installed Tool 和文档申请/下载。
- Docker 验证覆盖健康状态、端口 2223、后台队列、Scheduler 和容器重启后的数据库/文件持久化。

## 13. 明确不做

- Staging、生产域名、HTTPS、SMTP、MFA 配置。
- 智能派工、路线优化和技能匹配。
- 完整 Field Service、Procedure Run、备件成本和客户门户。
- 声称能够阻止截图或移除水印。
- 运行时 Mock 回退和公开永久文件链接。
