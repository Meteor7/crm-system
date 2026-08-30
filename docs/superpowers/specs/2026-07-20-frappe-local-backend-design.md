# RAYHER CRM 本地 Frappe 后端设计

**日期：** 2026-07-20  
**状态：** 用户已确认  
**范围：** 本地 Docker 开发环境、Frappe v16 后端、现有 Web 前端完整接入；不包含 Staging 或生产部署

## 1. 目标与边界

- 使用独立 Frappe CRM App，不安装 ERPNext。
- 仅提供浏览器 Web 端；现有 Vue 前端作为 Frappe Desk 工作台运行。
- 本地环境使用 Docker Desktop 当前用户安装模式和 WSL 2 后端。
- Frappe 使用 v16 稳定版并固定具体补丁版本及镜像。
- 本地统一入口为 `http://localhost:2223`。
- 当前全部业务页面接入真实后端，不保留运行时 Mock 接口。
- 本地测试数据来自现有 Mock 数据和 CUSTOMER06 Customer 360 Excel。
- 本阶段不考虑 Staging、生产迁移、多币种、SMTP 或第三方电子签署。

## 2. 运行架构

浏览器先通过 Frappe 登录，再进入 RAYHER CRM Desk 页面。Vue 前端与 Frappe API 同域，使用 Frappe Session、CSRF、权限和私有文件机制。Docker 环境包含 Frappe Web/Backend、MariaDB、Redis、Scheduler、后台任务队列和 WebSocket，并为站点、数据库和附件配置持久化存储。

## 3. 数据模型

- `CRM Account`：客户主档。客户编号由业务人员填写，格式为 `客户简称-年份-三位序号`；年份由录入人员确定，完整编号唯一且建档后不变。
- `CRM Site`：客户厂区，关联客户。
- `CRM Stakeholder`：关键人，关联客户，通过 `reports_to` 建立组织关系。
- `CRM Requirement`：客户需求，关联客户和厂区。
- `CRM Opportunity`：销售商机，可来源于需求。
- `CRM Booking`：成交记录；商机进入 Won 后幂等地自动创建。
- `CRM Demo Request`：Demo 申请，使用 Frappe Workflow。
- `CRM Evaluation`：Wafer Test 主任务，由已批准 Demo 幂等地创建。
- `CRM Test Run`：独立测试批次，可挂载多张图片、原始数据和报告附件。
- `CRM Contract`：合同台账，只关联客户。
- `CRM Visit`：拜访、纪要和经理审阅记录。
- `CRM Action`：后续行动，可关联需求、拜访、商机、Demo、测试或合同。

Dashboard 不存储重复快照值，而是在权限过滤后由后端实时聚合。业务记录原则上不物理删除，只允许停用、取消或归档，并保留审计历史。

## 4. 权限

- CRM 管理员：管理全部数据和配置。
- 管理者权限：查看全部客户、经营驾驶舱和业务记录。
- 销售经理：查看和维护本团队数据，审批 Demo，审阅拜访纪要。
- 销售人员：查看和维护本人负责的客户及销售流程数据。
- FAE/应用工程师：查看分配给自己的 Demo 和 Wafer Test，提交技术方案及测试结果。

权限由 Frappe Role、User Permission、团队关系、Permission Query 和写接口共同执行，不能依赖前端隐藏按钮。

## 5. 业务流程

- Demo：销售提交 → FAE 审核或退回 → FAE 确认 → 销售经理批准或拒绝 → 批准后创建 Evaluation。
- Wafer Test：待确认 → 范围确认 → 样品接收 → 测试排期 → 测试中 → 数据分析 → 客户确认 → 通过/未通过；支持暂停和恢复。
- 商机：需求发现 → 技术确认 → Demo 验证 → 预算审批 → 报价 → 采购流程 → 成交/失单；成交后创建 Booking。
- 拜访：计划 → 已拜访 → 提交纪要 → 经理审阅；下一步行动进入驾驶舱。
- 合同：草稿、未签署、生效、到期、终止；支持私有附件和系统内到期提醒，不启用电子签署。

## 6. API 与报表

- 查询使用 GET，写操作使用 POST；写操作重新检查用户、团队、负责人和流程状态。
- 响应统一为 `data + meta + warnings`，错误包含代码、可读消息、字段错误和 Request ID。
- 前端继续使用现有 `CrmApi` 契约及 `frappe-adapter.ts` 方法边界。
- Dashboard 使用自然季度和人民币口径，由后端聚合。
- 客户 360 Excel 由后端按现有原型格式实时生成。
- 时区固定为 `Asia/Shanghai`。

## 7. 本地初始化与验收

- 创建管理员、管理者、销售经理、销售人员和 FAE 五种本地测试账号；密码不写入源码或文档。
- 导入现有 Mock 和 CUSTOMER06 演示数据，并标记为开发测试数据。
- 本地关闭邮件发送，只验证系统内通知。
- 验证角色权限、全部 CRUD、审批状态机、附件、Dashboard、客户报告、错误模型和容器重启后的持久化。

## 8. 当前环境结论

- Windows 11 Pro、WSL 2.7.10、相关 Windows 虚拟化组件、Git、Node 和 pnpm 已具备。
- 内存约 32 GB，C 盘剩余约 210 GB。
- 端口 `2223` 当前可用。
- Docker Desktop、Docker Engine 和 Compose v2 尚未安装。
- 首次启动 Docker 后验证虚拟化；只有 Docker 明确报告固件虚拟化异常时才需要调整 BIOS/UEFI。
