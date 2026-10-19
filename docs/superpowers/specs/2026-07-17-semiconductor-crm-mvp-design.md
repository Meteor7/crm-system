# 半导体 CRM 本地前端 MVP 设计

## 原型事实

- 当前目录只有 `semiconductor-crm-demo.html` 与架构需求文档，不是 Frappe Bench，也没有现成前端工程或 Git 仓库。
- 原型已验证 9 个页面和主要业务语义：经营看板、客户、关键人、商机/Booking、拜访、采购需求、Demo Request、产品验证、合同。
- 原型把样式、数据和交互集中在单个 HTML，并用 `localStorage` 作为演示数据源；生产化文档明确禁止继续采用该结构。
- 正式技术边界已确定为 Vue 3、TypeScript、Vite、Pinia、Vue Router `createMemoryHistory`、Element Plus 与 ECharts；根节点必须使用 `.semicrm-app` 隔离样式。
- 文档要求深海军蓝 `#123B4A`、青绿 `#147C72`、暖白灰 `#F5F7F7`、正向黄绿 `#B8CC5A`、关注琥珀 `#D6A84B`，并覆盖 loading、empty、error、permission denied、partial/stale、disabled/read-only 和 success 状态。

## 方案比较与决定

1. **独立 Vue MVP + 类型化适配器（采用）**：当前即可本地运行；Mock Adapter 支持视觉和交互验证，Frappe Adapter 保留后续接入点。代价是本次不验证真实会话与后端权限。
2. **继续扩展单文件 HTML（不采用）**：启动最快，但继续放大全局状态、无类型、无测试和 `localStorage` 生产化风险。
3. **直接创建完整 Frappe App（本次不采用）**：最终形态最完整，但目录缺少 Bench、Site、Frappe CRM 版本和标准 DocType 实例，强行搭建会违背需求文档的环境约束。

## MVP 目标

交付一个可在本地启动、可构建、可测试的企业级前端，让用户能够从经营看板识别风险，进入客户档案，查看采购需求与商机，并把客户情报转成下一步行动。所有数据通过统一 `apiClient` 获取；本地模式使用内存 Mock，不写入 `localStorage`。

## MVP 范围

### 完整实现

- AppShell：品牌、分组导航、角色/团队上下文、搜索、刷新时间、移动端收起导航。
- Dashboard：经营摘要、KPI、销售漏斗、月度趋势、重点客户、本周行动、客户情报摘要、数据完整度。
- Accounts：筛选/搜索列表、客户等级与业务领域、Pipeline、关键人、Site 与 360 详情抽屉。
- Requirements：采购需求状态、设备/应用、预算、完整度、负责人、Next Action、关联业务。
- Pipeline：商机与 Booking 分栏口径、阶段、概率、意愿分、金额、加权金额与下一步行动。
- Intelligence：事件来源、事件类型、机会分、复核状态、关联客户和“转行动”交互。
- 全局数据状态：loading、empty、error、permission denied、stale/partial、retry 与成功反馈。

### 合并表达

- 关键人和 Site 合并进 Account 360，避免 MVP 阶段出现两个信息稀疏的独立页面。
- 拜访、Demo/Evaluation 与合同以 Dashboard/Account 360 的摘要和风险入口表达，保留后续模块关系。

### 暂缓

- Frappe 后端、DocType、真实登录/权限、队列任务、RSS 抓取和数据库持久化。
- Demo 工程评估/经理审批、Test Run 录入、合同文件、Booking 写入等完整写流程。
- 独立 SPA 登录、客户门户、外部消息发送、全文抓取与 AI 自动创建销售任务。

## 信息架构与路由

- `/dashboard`：经营与行业分析。
- `/accounts`：客户档案与 Account 360。
- `/requirements`：采购需求。
- `/pipeline`：商机与 Booking。
- `/intelligence`：客户情报复核。

路由使用 `createMemoryHistory`，避免未来嵌入 Frappe Desk 时与 Desk 路由冲突。侧栏保持分组语义，但只暴露 MVP 路由；暂缓模块以“即将接入”摘要而非失效导航出现。

## 前端边界

- `src/app`：应用入口、路由、布局和全局上下文。
- `src/api`：`CrmApi` 接口、Mock/Frappe Adapter、统一错误模型。
- `src/types`：稳定 DTO；不直接镜像未来 DocType 的所有字段。
- `src/stores`：只保存跨组件状态和 API 状态；页面局部筛选保留在页面。
- `src/design-system`：token、状态标签、KPI、空/错/加载组件。
- `src/charts`：只接收干净 DTO 的纯函数 option builder 和 ECharts 容器。
- `src/pages`：页面编排，不直接访问数据源。
- `src/features`：客户抽屉、筛选条、情报卡片等领域 UI。

## 数据契约

统一响应为 `{ data, meta, warnings }`，错误映射为 `{ code, message, fieldErrors, requestId, retryable }`。核心方法：

- `getBootstrap(): BootstrapDto`
- `getDashboard(filters): DashboardDto`
- `listAccounts(query): PageResult<AccountSummaryDto>`
- `getAccount360(id): Account360Dto`
- `listRequirements(query): PageResult<RequirementDto>`
- `listPipeline(query): PipelineDto`
- `listIntelligenceEvents(query): PageResult<IntelligenceEventDto>`
- `createActionFromEvent(id): ActionDto`

Mock Adapter 模拟延迟并返回可解释演示数据；Frappe Adapter 使用同样接口和 POST 写约定。生产模式不读写 `localStorage`。

## 视觉与交互

- 1366px 起提供完整双栏工作区，最大内容宽度 1600px；低于 1200px 收窄侧栏，低于 840px 使用抽屉导航和单列内容。
- 卡片圆角 14px，边框优先、阴影克制；表格数字启用 tabular numbers。
- 主操作置于页面右上；详情保留在抽屉中，不丢失列表上下文。
- 金额、日期和状态全局统一；状态用文字、图标与颜色共同表达。
- 图表不使用 3D、无意义饼图或虚假零数据；tooltip 明确人民币和数量口径。
- 可点击元素具备 hover、focus-visible、disabled 与 `aria-label`。

## 状态与失败策略

- 首次请求显示骨架；零记录显示下一步操作；失败显示 request ID 和重试按钮。
- 无权限时页面不渲染敏感内容，并显示权限说明。
- `warnings` 或过期时间触发 stale/partial 提示条。
- “情报转行动”仅更新 Mock 内存状态并显示成功反馈；不自动向客户发送任何消息。

## 测试与验收

- Vitest：DTO/格式化、筛选、状态映射、图表 option builder、Mock 写操作。
- Vue Test Utils：AppShell 导航、Dashboard 数据状态、Account 360 抽屉、情报转行动。
- 浏览器检查：1366、1440、1920 和 820 宽度；无水平溢出、遮挡和错误换行。
- 质量门：typecheck、unit test、build 通过；页面无明显控制台错误；关键按钮产生真实 UI 状态变化。

## 明确假设

- 本地 MVP 默认角色为 Sales Manager，可查看所有 Mock 客户；权限控制只用于展示体验，不替代后端权限。
- 金额币种为人民币；Dashboard 金额口径分别展示 open pipeline、weighted pipeline 与 confirmed booking。
- 情报数据为合规演示摘要，保留来源 URL 字段但不抓取或存储全文。
- 因当前目录没有 Git 仓库，设计与实现文件会落盘但无法按流程创建提交。
