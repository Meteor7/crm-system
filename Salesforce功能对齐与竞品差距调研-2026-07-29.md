# Semiconductor CRM Demo 与 Salesforce 功能对齐及竞品差距调研

| 项目 | 内容 |
| --- | --- |
| 调研日期 | 2026-07-29 |
| 我方验收地址 | `http://203.0.113.10:4173/dashboard` |
| 对标对象 | Salesforce Sales Cloud 标准销售能力，以及与本 Demo 相关的 Sales Engagement、Sales AI、Field Service、Salesforce Files / Flow 等扩展能力 |
| 调研目的 | Demo 功能验收、竞品功能校对、后续版本优先级讨论 |
| 调研口径 | 只依据当前 Demo 页面实际可见、可打开或可操作的功能，不审查代码、权限配置、后端、性能和生产安全 |

> **重要说明：** Salesforce 的能力会随 Edition、许可证和附加产品不同而变化。本文将“Sales Cloud 标准销售能力”“需要配置的 Salesforce 平台能力”“额外付费产品”分开标注，避免把 Salesforce 全家桶误认为基础 Sales Cloud 默认功能。

## 1. 执行摘要

### 1.1 总体判断

当前 Demo 已经具备一条较完整、可用于业务演示的半导体设备销售主线：

`Lead → Account / Contact / Opportunity → Booking / Visit / Action → Demo Request → Demo Test → Installed Tool / Document`

对照 Salesforce，当前 Demo 的特点如下：

- **销售主数据和商机推进已经基本对齐：** 客户、联系人、Lead、Lead 转换、Opportunity 列表、Opportunity Path、金额、赢率、Forecast Category、下一步行动等，都已经有明确页面。
- **半导体售前验证流程具有行业差异化：** Demo Request、工程评估、经理审批、Demo Test、Wafer 指标、客户评审和 Demo 档案，不是 Salesforce Sales Cloud 的标准开箱页面；在 Salesforce 中通常需要自定义对象、Flow、审批和文件能力组合实现。
- **销售运营深度仍明显弱于 Salesforce：** 当前缺少产品与价目表、Opportunity Product、报价单、协同预测、Pipeline Inspection、可配置报表、营销归因、自动化外联、邮件活动捕获、重复数据治理、销售区域和团队分摊。
- **Installed Tools 和 Document Center 已有良好概念展示，但还没有达到 Salesforce Field Service / Salesforce Files 的完整作业闭环。**

### 1.2 本次可验收范围结论

| 分类 | 数量 | 说明 |
| --- | ---: | --- |
| 强对齐 | 6 | 已具备与 Salesforce 相近的核心页面结构和主要用户动作 |
| 部分对齐 | 6 | 已有概念或页面，但缺少 Salesforce 的通用化、协作或运营深度 |
| 行业差异化 | 3 | 我方已形成半导体专用流程；Salesforce 需要平台定制或相关产品组合 |
| 主要未对齐项 | 19 | 建议按 P0 / P1 / P2 分批评估，不建议一次性照搬 |

### 1.3 最值得保留的我方差异化

以下能力不应为了“长得像 Salesforce”而被削弱：

1. Demo Request 的 Sales 准备、Engineer Review、Manager Approval 三段式业务语义。
2. Demo Test 的 Test Preparation、Test Execution、Customer Review 业务分段。
3. Wafer 数量、Capture、False Positive、Test DDL 等半导体验证指标。
4. Demo 项目的健康状态、停滞天数、客户预期时间与测试 DDL 联动。
5. Installed Tool 以 Serial Number 为核心的一机一档。
6. FAT → Shipment → Installation → SAT → Warranty 的设备交付链。
7. Current Version、文档分类、访问申请、下载审计等受控文档概念。

这些功能是我方 Demo 相对通用型 CRM 的行业价值，不属于简单的 Salesforce 功能缺失。

## 2. 对齐等级定义

| 等级 | 判定标准 |
| --- | --- |
| 强对齐 | 当前 Demo 已有清晰入口、主要字段、列表或详情，并具有关键动作 |
| 部分对齐 | 当前 Demo 已表达业务概念，但覆盖面、联动或通用能力弱于 Salesforce |
| 行业差异化 | 我方已经有行业专用流程；Salesforce 通常依赖自定义对象、Flow、审批或相关产品实现 |
| 未对齐 | 当前 Demo 页面未看到该能力，或只有提示/占位而没有可验收流程 |

## 3. 已对齐和部分对齐功能

| # | 我方 Demo 可见功能 | Salesforce 对应能力 | 对齐结论 | 验收观察 |
| ---: | --- | --- | --- | --- |
| 1 | 信息中心：Open Pipeline、Weighted Pipeline、Confirmed Booking、Closed Won、客户贡献、Demo 状态、近期事项 | Sales Dashboards、Reports、Forecast 汇总 | **部分对齐** | 已具备管理层经营看板和口径说明；但属于固定看板，未看到用户自助报表、Dashboard Builder、订阅和钻取报表 |
| 2 | 客户档案与 Account 360：客户等级、Site、关键人、Pipeline、Booking、合同、拜访、Demo | Accounts、Contacts、Related Lists、Account Planning | **强对齐** | 已形成客户主档和跨对象聚合视图，能够保留客户上下文 |
| 3 | 联系人主档：客户、厂区、职位、部门、电话、邮箱、Owner、状态 | Contacts、Account Contact Relationships | **强对齐** | 列表、筛选、新增、编辑和状态字段齐全；Opportunity 影响力在商机详情单独处理 |
| 4 | Leads：来源、状态、Owner、下一步、日期、搜索和筛选 | Leads、Lead Status、Lead Source、List Views | **强对齐** | New、Working、Qualified、Nurturing、Disqualified、Converted 等状态已可见 |
| 5 | Lead 360 与 Lead 转换：复用或新建 Account、Contact，并创建 Opportunity | Salesforce Lead Conversion | **强对齐** | 转换表单已支持复用现有 Account、创建 Contact、填写 Opportunity 名称、金额、成交日、Owner 和产品；结构与 Salesforce 的 Lead → Account / Contact / Opportunity 转换接近 |
| 6 | Opportunity 列表：Stage、Close Date、Amount、Probability、Forecast、Owner、Updated | Opportunities、List Views、Forecast Category | **强对齐** | 支持搜索和 Stage / Forecast / Owner 筛选，记录可进入独立详情页 |
| 7 | Opportunity 详情：Path、阶段推进、About、Status、Action Plan、Change History、Commercial Forecast | Opportunity Record、Sales Path、Activity、Opportunity History | **强对齐** | 已展示六阶段 Path、推进下一阶段、金额、概率、Forecast Category、Next Step、变更历史和商业预测信息 |
| 8 | Buying Influence、Strength、Red Flag、Information Needed | Opportunity Contact Roles、Account Plans、Deal Insights | **部分对齐** | 已有商机策略框架和新增 Buying Influence 入口；但未看到标准化 Contact Role、关系图、影响力覆盖度或 AI Deal Insights |
| 9 | Booking：类型、来源、设备需求、客户 DDL、金额、状态、Owner | Orders、Opportunity Products、Contracts，或企业自定义 Booking 对象 | **部分对齐** | 已能表达确认订单预期以及 Renewal / Maintenance；但不是 Salesforce 标准“产品—报价—订单—合同”链路 |
| 10 | 拜访与 Action、Calendar、个人/全员安排、客户预期、Demo Test DDL、Booking DDL | Tasks、Events、Calendars、Activity Timeline | **部分对齐** | 已有拜访计划、完成、纪要、审核、Action 和日历联动；但活动类型仍偏业务专用，未形成通用电话、邮件、会议、任务时间线 |
| 11 | Demo 档案：项目周期、生命周期、健康状态、停滞与临期提醒 | Custom Objects、Flow、Reports / Dashboards | **行业差异化** | Salesforce Sales Cloud 无同名标准模块；可通过自定义对象和自动化配置，但我方行业语义更直接 |
| 12 | Demo Request：Sales Preparation、Engineer Review、Manager Approval、Word 下载 | Custom Objects、Flow Approval Processes、Salesforce Files | **行业差异化** | 已形成售前样品测试申请和跨部门审批模型；Salesforce 需要平台定制，不属于标准 Opportunity 流程 |
| 13 | Demo Test：Preparation、Execution、Customer Review，关联 Request、Engineer、Wafer 和计划完成时间 | Custom Objects、Flow、Tasks / Events、Files | **行业差异化** | 已形成半导体验证项目的独立执行对象；Salesforce 通常需要定制数据模型 |
| 14 | Installed Tools：Serial Number、Customer/Site、软件版本、交付节点、Warranty | Assets、Locations、Service Contracts、Field Service | **部分对齐** | 一机一档和交付生命周期表达良好；未看到 Work Order、Service Appointment、Maintenance Plan 和现场移动作业 |
| 15 | Document Center：Current Version、Classification、Access Request、Version History、Download Audit | Salesforce Files、ContentVersion、ContentDocumentLink、Approval | **部分对齐** | 文档目录和受控访问概念清楚；当前“受控下载由服务端生成”仍为不可执行按钮，也未看到上传新版本、协作和全局文件搜索 |

## 4. 当前未对齐功能：Salesforce 功能与典型运用场景

### 4.1 P0：建议优先补齐的竞品基线

| # | 当前未对齐项 | Salesforce 上的功能 | Salesforce 典型运用场景 | 对我方 Demo 的建议 |
| ---: | --- | --- | --- | --- |
| 1 | 产品目录、价目表与 Opportunity Product | Salesforce 使用 Product、Price Book、Price Book Entry 和 Opportunity Products；同一产品可存在于不同价目表，并可配置产品计划。[官方文档](https://help.salesforce.com/s/articleView?id=sales.products_def.htm&language=en_US&type=5) | 同一检测设备面向中国区、全球区、代理商使用不同价格；在 Opportunity 中选择设备、软件、服务和数量，自动形成交易金额结构 | 增加 Product / Price Book / Opportunity Line Item 最小闭环；至少支持设备、软件、服务、数量、单价、折扣和交付计划 |
| 2 | 报价单、报价版本、报价 PDF 与商机同步 | Salesforce Quotes 支持一个 Opportunity 多份 Quote、选定一份与 Opportunity 同步、使用模板生成 PDF 并邮件发送。[官方文档](https://help.salesforce.com/s/articleView?id=sf.quotes_overview.htm&language=en_US&type=5) | 同一设备项目输出“标准配置”“高配方案”“含三年维保”三版报价；客户选择后将正式报价同步回 Opportunity | 增加 Quote 列表、版本、Line Items、折扣、有效期、同步标记和 PDF 预览；这是从“管商机”走到“管商务方案”的关键 |
| 3 | Collaborative Forecasts、Quota 和经理调整 | Salesforce Forecasts 提供团队预期收入、Forecast Category、层级汇总、周变化、Quota 对比和经理视角。[官方文档](https://help.salesforce.com/s/articleView?id=sf.forecasts3_basic_tasks_intro.htm&language=en_US&type=5) | 销售经理按月/季度查看 Pipeline、Best Case、Commit、Closed；对销售提交的 Commit 做管理判断并与团队目标比较 | 在固定 KPI 看板之外增加 Forecast 工作台：期间、团队/Owner、Quota、Commit、Best Case、Pipeline、经理调整和提交快照 |
| 4 | 用户自助 Reports 与 Dashboards | Salesforce 支持创建、筛选、分享、导出、订阅 Report，并用 Report 组成 Dashboard。[官方文档](https://help.salesforce.com/s/articleView?id=analytics.analytics_overview.htm&language=en_US&type=5) | 管理者临时建立“Q3 中国区先进封装商机”“30 天内无 Action 的机会”“不同设备型号赢单率”等报表，而不等待开发新页面 | 当前固定看板保留，同时增加最小可演示的 Report Builder：选择对象、字段、筛选、分组、图表、保存视图和导出 |
| 5 | 通用 Activity Timeline、邮件/会议自动关联 | Salesforce Activities 将 Task、Event、Calendar 统一关联到 Account、Contact、Lead、Opportunity 等记录；Sales Engagement 还可自动关联相关邮件和日历活动。[Activities 官方文档](https://help.salesforce.com/s/articleView?id=sales.activities.htm&language=en_US&type=5) / [Sales Engagement 官方文档](https://help.salesforce.com/s/articleView?id=sales.hvs_user_intro.htm&language=en_US&type=5) | 销售发送邮件、安排会议、记录电话、创建跟进任务后，所有活动自动出现在客户和商机时间线上 | 将当前“拜访与 Action”扩展为通用 Activity：Call、Email、Meeting、Task、Visit；在 Account、Contact、Lead、Opportunity 详情统一展示时间线 |
| 6 | 标准订单与合同链 | Salesforce 的产品能力可继续关联 Quote、Order、Contract / Service Contract；当前 Booking 只是业务预期记录。[产品概念官方文档](https://help.salesforce.com/s/articleView?id=sales.products_def.htm&language=en_US&type=5) | Opportunity Won 后生成订单；按设备和服务拆分交付内容，再关联合同、付款节点和服务期限 | 明确 Booking 与正式 Order 的边界；Demo 下一版至少演示 `Won Opportunity → Booking/Order → Contract → Installed Tool` |

### 4.2 P1：明显提升销售运营成熟度

| # | 当前未对齐项 | Salesforce 上的功能 | Salesforce 典型运用场景 | 对我方 Demo 的建议 |
| ---: | --- | --- | --- | --- |
| 7 | Pipeline Inspection | Salesforce Pipeline Inspection 集中展示 Pipeline 指标、Opportunity、周环比变化、Close Date/Amount/Stage/Forecast 变化、重要商机和风险洞察。[官方文档](https://help.salesforce.com/s/articleView?id=sf.pipeline_inspection.htm&language=en_US) | 周会前查看哪些项目金额下降、成交日后移、Stage 未更新、Next Step 过期，并聚焦高风险交易 | 增加“Pipeline Review”工作台，不只看静态 Opportunity 列表；突出 Push Count、过去 7 天变化、无下一步和停滞天数 |
| 8 | Campaign、Campaign Member 与营销归因 | Salesforce Campaigns 管理营销活动、成员、层级和绩效；Campaign Influence 将营销触点与 Opportunity 收入关联。[Campaigns 官方文档](https://help.salesforce.com/s/articleView?id=sf.campaigns_def.htm&language=en_US&type=5) / [Campaign Influence 官方文档](https://help.salesforce.com/s/articleView?id=sales.campaign_influence_parent.htm&language=en_US&type=5) | 追踪 SEMICON China 展会、线上 Webinar、代理商转介带来的 Leads、Opportunities 和收入贡献 | 增加 Campaign、Member Status、响应、预算、成本、来源转化和 Opportunity Influence；当前 Lead Source 只能说明来源，不能做营销 ROI |
| 9 | 重复数据检测、合并与数据质量治理 | Salesforce 使用 Matching Rules、Duplicate Rules、Duplicate Jobs 和 Duplicate Sets 检测及处理 Lead、Account、Contact 重复项。[官方文档](https://help.salesforce.com/s/articleView?id=sf.duplicate_detection_and_handling.htm&language=en_US&type=5) | 导入展会名单或执行 Lead 转换时，识别“CUSTOMER06 / 示例企业015中国 / 示例企业014有限公司”可能是同一客户，避免重复主档 | 当前转换表单可以人工选择复用 Account/Contact，但还需要保存前重复提示、相似记录比较和合并动作 |
| 10 | Sales Engagement：Cadence、Work Queue、Dialer、模板 | Sales Engagement 提供 Work Queue、销售 Cadence、电话、邮件模板、自动动作和互动提醒；属于指定 Edition 或额外费用能力。[官方文档](https://help.salesforce.com/s/articleView?id=sales.hvs_user_intro.htm&language=en_US&type=5) | 新展会 Leads 自动进入 10 天跟进节奏：第 1 天邮件、第 3 天电话、第 6 天案例、第 10 天二次电话；销售每天从 Work Queue 执行 | 不建议一次做完整销售自动化；可先演示“跟进序列模板 + 今日工作队列 + 步骤完成状态” |
| 11 | Einstein Lead / Opportunity Scoring | Einstein Opportunity Scoring 使用历史商机、Account、Activity、Product、Quote 和 Price Book 数据给出 1–99 分及正负因素。[官方文档](https://help.salesforce.com/s/articleView?id=sf.einstein_sales_opportunity_scoring.htm&language=en_US&type=5) | 从大量 Pipeline 中优先识别更可能成交或快速恶化的项目；解释评分受阶段速度、活动、历史相似交易等因素影响 | 当前 Strategy Score 应明确是规则分还是 AI 分；若无足够历史数据，先做“可解释规则评分”，不要把固定分数包装成 AI |
| 12 | Opportunity Team 与 Revenue / Product Split | Salesforce Opportunity Teams 支持多人协同；Opportunity Splits 可将收入或产品贡献分配给不同成员并进入配额与报表。[官方文档](https://help.salesforce.com/s/articleView?id=sales.teamselling.htm&language=en_US&type=5) | 一个设备项目由销售、区域经理、FAE、总部产品经理和渠道共同推进，需要明确角色和销售业绩归属 | 在单一 Owner 之外增加 Opportunity Team；如有跨区或代理商销售，再增加 Revenue Split / Overlay Split |
| 13 | Sales Territories 与区域预测 | Salesforce Sales Territories 支持区域层级、Account 分配规则、历史分配和 Territory Forecast。[官方文档](https://help.salesforce.com/s/articleView?id=release-notes.rn_sales_features_core_territory_management.htm&language=en_US&release=236&type=5) | 按华东、华南、台湾、先进封装行业组或 Named Account 分配客户；调整区域后重新对齐客户和预测 | 当销售人数和区域复杂度上升后再做；Demo 可先增加 Territory 字段和按 Territory 汇总的 Pipeline |
| 14 | Sales Account Plans 与标准化 Action Plan | Salesforce Account Plans 在一个工作区记录客户需求、优势劣势、目标和可量化指标；Sales Action Plans 用模板组织任务与事件。[Account Plans 官方文档](https://help.salesforce.com/s/articleView?id=sf.account_plans.htm&language=en_US) / [Action Plans 官方文档](https://help.salesforce.com/s/articleView?id=sales.sales_action_plans.htm&language=en_US&type=5) | 为 CUSTOMER06、CUSTOMER07 等战略客户建立 12–24 个月发展目标、项目地图、关系覆盖、收入目标和标准化拜访计划 | 当前 Account 360 是信息聚合，建议后续增加“客户计划”：目标、机会缺口、关系覆盖、关键举措、Owner、指标和复盘日期 |
| 15 | 完整 Field Service 作业闭环 | Salesforce Field Service 使用 Asset、Maintenance Plan、Work Order、Service Appointment 和 Work Plan 管理维护与现场执行。[维护计划官方文档](https://help.salesforce.com/s/articleView?id=sf.fs_create_maintenance.htm&language=en_US&type=5) / [Work Plan 官方文档](https://help.salesforce.com/s/articleView?id=service.fs_work_plans_intro.htm&language=en_US&type=5) | 根据设备、质保和 PM 周期自动生成工单，分派工程师和服务预约，现场按步骤执行并回传结果 | Installed Tools 下一步应优先补 Service Work Order、PM 计划、故障、预约和完成回执，而不是继续增加只读字段 |
| 16 | Flow 自动化、统一审批工作项和通知 | Salesforce Flow 可自动创建任务、发提醒、更新记录并提供引导式表单；Flow Approval Process 可创建审批提交、审批步骤和工作项。[Flow 官方文档](https://help.salesforce.com/s/articleView?id=flow.htm&language=en_US) / [Approval Steps 官方文档](https://help.salesforce.com/s/articleView?id=platform.automate_automated_approvals_concepts_approval_step.htm&language=en_US&type=5) | Demo Request 工程评估完成后自动通知经理；审批超时升级；批准后创建 Demo Test、任务和日历事项 | 当前业务流程已经可演示，但通知中心明确显示“暂未接入”；下一步应把审批待办、超时提醒和业务通知统一到工作队列 |

### 4.3 P2：规模化和体验增强能力

| # | 当前未对齐项 | Salesforce 上的功能 | Salesforce 典型运用场景 | 对我方 Demo 的建议 |
| ---: | --- | --- | --- | --- |
| 17 | Salesforce Mobile 与离线作业 | Salesforce Mobile 可缓存常用记录、任务和 Dashboard，并支持离线创建/编辑/删除后同步及冲突提示。[官方文档](https://help.salesforce.com/s/articleView?id=sf.salesforce_app_offline.htm&language=en_US&type=5) | 销售在客户工厂、飞机或网络受限区域查看客户资料、记录拜访；工程师现场填写服务结果 | 如果一线团队强依赖手机，优先做响应式移动操作；真正离线同步可作为后续独立项目 |
| 18 | 完整文件上传、版本协作和记录关联 | Salesforce Files 使用 ContentDocument、ContentVersion、ContentDocumentLink 管理文件、版本以及与用户、记录和 Library 的关联。[官方文档](https://help.salesforce.com/s/articleView?language=en_US&nocache=https%3A%2F%2Fhelp.salesforce.com%2Fs%2FarticleView%3Flanguage%3Den_US%26id%3D005314319%26type%3D1) | 在 Account、Opportunity、Demo Test、Installed Tool 下上传并维护方案、测试数据、验收单和客户文件版本 | Document Center 应补上传新版本、替换 Current、关联业务记录、文件预览和检索；受控 PDF/水印可以继续作为我方差异化 |
| 19 | Report / Dashboard 订阅与条件通知 | Salesforce 支持订阅 Report 和 Dashboard，并按计划或条件推送；订阅数量受 Edition 限制。[订阅官方说明](https://help.salesforce.com/s/articleView?id=000317981&language=en_US&type=1) | 每周一自动发送销售预测；当逾期 Action 或高价值商机发生变化时通知经理 | 在自助报表之后再做订阅；当前可先实现“保存视图 + 每周摘要 + 到期提醒” |

## 5. 按业务域的竞品差距结论

| 业务域 | 当前水平 | 相对 Salesforce 的主要差距 | 建议 |
| --- | --- | --- | --- |
| Lead-to-Opportunity | 高 | 重复数据治理、营销归因、自动分配、Lead Scoring | 保持现有转换体验，优先补重复提示和 Campaign |
| Account / Contact 360 | 高 | Account Plan、关系图、跨客户关系、数据质量 | 为战略客户增加 Account Plan，不必大改现有 360 |
| Opportunity Execution | 中高 | Pipeline Inspection、团队协作、分摊、AI 风险洞察 | 先做 Pipeline Review 和 Opportunity Team |
| Revenue Management | 低 | Product、Price Book、Quote、Order、Contract、Forecast、Quota | 这是当前最大竞品短板，应作为下一轮重点 |
| Activities & Productivity | 中 | 通用 Activity Timeline、邮件/会议同步、Work Queue、Cadence | 统一 Visit / Action / Call / Email / Meeting 数据口径 |
| Analytics | 中低 | 自助 Report、Dashboard Builder、订阅、钻取、历史趋势 | 固定管理看板保留，增加最小 Report Builder |
| Marketing-to-Sales | 低 | Campaign、Campaign Member、Influence、ROI | 如果销售线索主要来自展会，Campaign 应进入 P1 前排 |
| Demo / Validation | 高且差异化 | Salesforce 无标准开箱模块 | 继续深耕行业流程，不需要照搬 Salesforce |
| Installed Base / Service | 中 | Work Order、Maintenance Plan、Service Appointment、移动现场执行 | 从只读设备档案推进到服务工单闭环 |
| Document Management | 中 | 上传、版本更新、记录关联、协作和完整审批执行 | 保留受控输出设计，补文件实际操作闭环 |
| AI / Automation | 低 | Lead/Opportunity Scoring、Deal Insights、Flow 工作队列 | 先积累结构化数据和历史，再做可解释 AI |

## 6. 建议的功能路线图

### 6.1 第一批：让 Demo 达到 Salesforce 销售主链竞品基线

建议优先完成以下 5 项：

1. **Product + Price Book + Opportunity Products**
2. **Quote + Quote PDF + Opportunity 同步**
3. **Forecast 工作台：Quota / Commit / Best Case / Pipeline**
4. **统一 Activity Timeline：Call / Email / Meeting / Task / Visit**
5. **最小 Report Builder：筛选、分组、图表、保存和导出**

这一批完成后，Demo 才真正从“销售项目展示系统”提升为“完整的销售运营 CRM Demo”。

### 6.2 第二批：提升管理和规模化能力

1. Pipeline Inspection 和周变化。
2. Campaign 与营销归因。
3. Duplicate Management。
4. Opportunity Team 和 Split。
5. Account Plan。
6. 通知、待办和审批工作队列。

### 6.3 第三批：按真实业务需求选择，不建议为了竞品清单全部照搬

1. Sales Engagement Cadence。
2. Einstein / AI Scoring。
3. Sales Territories。
4. Mobile Offline。
5. 完整 Field Service。
6. Report / Dashboard 订阅。

## 7. Demo 验收建议

### 7.1 已具备的推荐演示脚本

1. 从 Leads 打开一条 Qualified Lead。
2. 点击“转换 Lead”，选择创建或复用 Account / Contact，同时创建 Opportunity。
3. 在 Opportunities 中按 Stage、Forecast、Owner 筛选。
4. 打开 Opportunity，展示 Path、概率、Forecast、Next Step、Action Plan、Strength 和 Red Flag。
5. 由销售创建 Demo Request，进入 Engineer Review 和 Manager Approval。
6. 批准后进入 Demo Test，并在 Demo 档案查看全生命周期和健康状态。
7. 在 Calendar 查看客户预期、Test DDL 和 Booking DDL。
8. 在 Installed Tools 查看 Serial Number 和 FAT → Warranty 交付链。
9. 在 Document Center 查看 Current Version、访问申请、版本历史和下载审计概念。

### 7.2 竞品演示中容易被追问、当前需要明确回答的问题

| 可能被问到的问题 | 当前建议回答 |
| --- | --- |
| 能否配置产品、价目表和多行报价？ | 当前 Demo 尚未对齐，列为 P0 |
| 能否生成正式报价 PDF 并同步商机？ | 当前 Demo 尚未对齐，列为 P0 |
| 销售经理能否提交/调整 Forecast 并对比 Quota？ | 当前只有管理 KPI 看板，尚未形成 Collaborative Forecasts |
| 用户能否自己建报表和 Dashboard？ | 当前为固定看板，尚未提供自助 Report Builder |
| 邮件、电话和会议是否自动进入客户时间线？ | 当前以拜访、Action 和日历业务事项为主，尚未对齐邮件活动捕获 |
| 是否支持 Campaign ROI？ | 当前只有 Lead Source，尚未形成 Campaign Member / Influence |
| 如何避免重复客户和联系人？ | 转换时可人工复用现有记录，但尚未展示 Matching / Duplicate Rules |
| Opportunity 能否多人协作并分摊业绩？ | 当前以 Owner 为主，尚未展示 Opportunity Team / Split |
| 能否自动生成 PM 工单并派工程师？ | Installed Tools 当前是设备与交付档案，尚未形成 Field Service 工单闭环 |
| 是否支持移动端离线？ | 当前验收范围未展示 |

## 8. 最终结论

当前 Demo **已经能够验收“半导体销售 + Demo 验证 + 设备交付档案”的核心业务叙事**，在 Demo Request、Demo Test、Wafer 验证、客户预期与 Test DDL 联动方面具有清晰行业特色。

但是，如果验收目标是“与 Salesforce Sales Cloud 的主流销售能力竞争”，当前最大缺口不是页面风格，而是以下五个运营闭环：

1. **产品与价目**
2. **报价与订单**
3. **预测与配额**
4. **通用活动与邮件捕获**
5. **自助报表与 Pipeline Inspection**

因此建议采用“保留行业差异化 + 补齐销售运营基线”的路线，而不是逐项复制 Salesforce：

```text
保留：Demo Request / Demo Test / Wafer / Installed Tool / Controlled Document
补齐：Product / Quote / Forecast / Activity Timeline / Reports
增强：Pipeline Inspection / Campaign / Duplicate / Account Plan / Team Selling
选配：Sales Engagement / Einstein / Territory / Mobile Offline / Field Service
```

## 9. Salesforce 官方资料索引

### 销售主数据与交易

- [Convert Qualified Leads](https://help.salesforce.com/s/articleView?id=sales.leads_convert.htm&language=en_US&type=5)
- [Considerations for Converting Leads](https://help.salesforce.com/s/articleView?id=sales.leads_notes.htm&language=en_US)
- [Opportunity Contact Roles](https://help.salesforce.com/s/articleView?id=sales.sales_core_opp_contact_roles.htm&language=en_US&type=5)
- [Products Concepts](https://help.salesforce.com/s/articleView?id=sales.products_def.htm&language=en_US&type=5)
- [Quotes](https://help.salesforce.com/s/articleView?id=sf.quotes_overview.htm&language=en_US&type=5)
- [Opportunity Teams and Opportunity Splits](https://help.salesforce.com/s/articleView?id=sales.teamselling.htm&language=en_US&type=5)

### 预测、分析与效率

- [Managing Pipeline Forecasts](https://help.salesforce.com/s/articleView?id=sf.forecasts3_basic_tasks_intro.htm&language=en_US&type=5)
- [Pipeline Inspection](https://help.salesforce.com/s/articleView?id=sf.pipeline_inspection.htm&language=en_US)
- [Reports and Dashboards](https://help.salesforce.com/s/articleView?id=analytics.analytics_overview.htm&language=en_US&type=5)
- [Activities: Tasks, Events, and Calendars](https://help.salesforce.com/s/articleView?id=sales.activities.htm&language=en_US&type=5)
- [Sell Faster with Sales Engagement](https://help.salesforce.com/s/articleView?id=sales.hvs_user_intro.htm&language=en_US&type=5)
- [Einstein Opportunity Scoring](https://help.salesforce.com/s/articleView?id=sf.einstein_sales_opportunity_scoring.htm&language=en_US&type=5)

### 营销、客户规划与治理

- [Get to Know Salesforce Campaigns](https://help.salesforce.com/s/articleView?id=sf.campaigns_def.htm&language=en_US&type=5)
- [Campaign Influence](https://help.salesforce.com/s/articleView?id=sales.campaign_influence_parent.htm&language=en_US&type=5)
- [Duplicate Detection and Handling Process](https://help.salesforce.com/s/articleView?id=sf.duplicate_detection_and_handling.htm&language=en_US&type=5)
- [Sales Account Plans](https://help.salesforce.com/s/articleView?id=sf.account_plans.htm&language=en_US)
- [Sales Action Plans](https://help.salesforce.com/s/articleView?id=sales.sales_action_plans.htm&language=en_US&type=5)
- [Enterprise Territory Management](https://help.salesforce.com/s/articleView?id=release-notes.rn_sales_features_core_territory_management.htm&language=en_US&release=236&type=5)

### 平台、服务与文件

- [Automate Tasks with Flows](https://help.salesforce.com/s/articleView?id=flow.htm&language=en_US)
- [Approval Steps](https://help.salesforce.com/s/articleView?id=platform.automate_automated_approvals_concepts_approval_step.htm&language=en_US&type=5)
- [Set Up Field Service Maintenance Plans](https://help.salesforce.com/s/articleView?id=sf.fs_create_maintenance.htm&language=en_US&type=5)
- [Learn About Work Plans in Field Service](https://help.salesforce.com/s/articleView?id=service.fs_work_plans_intro.htm&language=en_US&type=5)
- [Understanding Salesforce Files](https://help.salesforce.com/s/articleView?language=en_US&nocache=https%3A%2F%2Fhelp.salesforce.com%2Fs%2FarticleView%3Flanguage%3Den_US%26id%3D005314319%26type%3D1)
- [Work Offline with the Salesforce Mobile App](https://help.salesforce.com/s/articleView?id=sf.salesforce_app_offline.htm&language=en_US&type=5)

---

**文档使用建议：** 本报告适合用于 Demo 验收会、竞品对照会和下一版需求评审。若要进入正式产品规划，应再把 P0 / P1 项拆成业务价值、用户角色、数据模型、页面流程和验收用例。
