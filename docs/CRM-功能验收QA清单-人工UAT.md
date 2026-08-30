# Semiconductor CRM 功能验收清单（Frappe 运行时）

| 文档信息 | 内容 |
| --- | --- |
| 文档版本 | V2.0（2026-08-14） |
| 适用系统 | Semiconductor CRM / Frappe v15 |
| 数据模式 | 共享 Frappe Site 与数据库；不是 Mock/localStorage |
| 测试角色 | CRM Manager、CRM Sales、CRM Engineer |
| 证据要求 | 实际业务 ID、Request ID、截图、下载文件名 |

> 失败时记录“角色、URL、业务 ID、操作、预期、实际、Request ID”。本清单只验收正常用户路径，不包含伪造 Frappe 通用 REST 请求的攻击用例。

## 0. 安全环境与质量门

| # | 操作 | 预期 | 结果 |
| --- | --- | --- | --- |
| 0.1 | 确认 Site | 自动化只可运行于带 `CRM_TEST_SITE=true` 且名称以 `.test` 结尾的 Site | ☐ |
| 0.2 | 前端全量 | `vitest run --pool=threads --maxWorkers=2`：102 files / 659 tests 通过 | ☐ |
| 0.3 | 类型与生产构建 | `vue-tsc --noEmit`、`vite build --mode frappe` 均通过 | ☐ |
| 0.4 | Frappe 资源构建 | 先 `npm.cmd run build:frappe`，再生成受检 ZIP 和镜像 | ☐ |
| 0.5 | 后端全量 | 包装器解析摘要；219 tests 通过，任一 failure/error 时外层退出非零 | ☐ |
| 0.6 | 残留 | File、Notification、Audit、History 与唯一 run ID 无残留 | ☐ |

## 1. 登录、导航与角色

| # | 角色 | 操作 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| 1.1 | 全部 | 使用真实 Frappe 账户登录 `/crm` | 显示当前 Frappe 姓名和 CRM 角色；不可在页面切换身份 | ☐ |
| 1.2 | Manager | 查看导航 | 可见管理、Sales、Demo、设备与知识模块 | ☐ |
| 1.3 | Sales | 查看导航 | 可执行 Sales 业务与 Demo Request；无 Manager 审批动作 | ☐ |
| 1.4 | Engineer | 查看导航和页头 | Sales 模块和不可用的全局客户搜索均隐藏 | ☐ |
| 1.5 | 全部 | 访问旧 URL `/pipeline`、`/stakeholders`、`/service-calendar` | 重定向到现行页面，不白屏 | ☐ |
| 1.6 | 全部 | 制造受控接口失败 | 页面显示标准错误和 Request ID，无未处理 Promise | ☐ |

## 2. 列表、分页与精确详情

对 Accounts、Contacts、Leads、Opportunities、Demo Requests、Evaluations、Visits、Requirements、Contracts、Installed Tools 逐项执行：

| # | 操作 | 预期 | 结果 |
| --- | --- | --- | --- |
| 2.1 | 准备 `total > pageSize` 的数据并翻到下一页/末页 | 显示当前页、总数、上一页/下一页；末页记录可访问 | ☐ |
| 2.2 | 在非第一页改变搜索或筛选 | 自动回到第一页，旧请求不得覆盖新结果 | ☐ |
| 2.3 | 删除当前页最后一条 | 回到仍有效的页；失败时原记录保留 | ☐ |
| 2.4 | 访问不存在的详情 ID | 显示 Not Found，不展示或修改第一条记录 | ☐ |
| 2.5 | 快速切换两个详情 ID/focus | 最终只显示最后一个 ID，慢响应不能回写旧记录 | ☐ |
| 2.6 | 在选择器中搜索第 201 条客户/联系人/Site/Opportunity | 服务端搜索或继续加载后可选，不依赖 `pageSize:500` | ☐ |

## 3. Opportunity × Demo 自动门禁

这是状态机逻辑，不在 Opportunity 页面展示 Demo Request/Test 内容。

| # | 角色 | 操作 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| 3.1 | Sales | 新建 Opportunity | 阶段固定且只读为“需求发现”，不能直接创建为其他阶段 | ☐ |
| 3.2 | Sales | 打开新建 Demo Request | “关联 Opportunity”为必填；选择后派生客户/Site/联系人范围 | ☐ |
| 3.3 | Sales | 创建并提交 Request | Opportunity 自动从“需求发现”进入“技术确认” | ☐ |
| 3.4 | Engineer | 确认可做 | Request 进入 Manager Approval；商机仍为“技术确认” | ☐ |
| 3.5 | Manager | 批准并创建 Evaluation | 唯一创建 Evaluation；商机自动进入“Demo验证” | ☐ |
| 3.6 | Engineer | 完成报告、Completed Test Run，并推进 Accepted | 商机自动进入“预算审批” | ☐ |
| 3.7 | Sales/Engineer | 尝试从 Opportunity 手工推进自动门禁 | 页面无入口；正常接口稳定拒绝 | ☐ |
| 3.8 | Manager | 回退商机，填写原因 | 仅允许合法目标，生成审计；无理由、旧版本或活动 Request 冲突时拒绝 | ☐ |
| 3.9 | Sales/Engineer | 查看同一商机 | 无 Manager 回退按钮 | ☐ |
| 3.10 | 全部 | 查看 Opportunity 详情 | 只显示阶段、策略、Action、Stakeholder、商业信息；无 Demo 内容板块 | ☐ |

## 4. Sales 正常流程

| # | 模块 | 操作 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| 4.1 | Account | 新建客户、Site、三类联系人并从 Account 360 核对 | 数据一致；错误时页面不移除原数据 | ☐ |
| 4.2 | Contact | 上传、查看、下载联系人附件 | 文件名/字节正确；失败显示 Request ID | ☐ |
| 4.3 | Lead | New→Working→Qualified→Converted | 生成/复用正确 Account、Contact、初始 Opportunity | ☐ |
| 4.4 | Visit | Planned→Visited→Minutes Submitted→Manager Reviewed | Opportunity 关联保留；纪要后的行动字段不可清空 | ☐ |
| 4.5 | Visit | 指定行动负责人并完成行动 | 负责人具备实际处理能力，通知与状态一致 | ☐ |
| 4.6 | Quotation | 创建、自动保存、版本、预览、发布、Accepted | 金额/日期错误为 422；版本冲突 409；下载文件正常 | ☐ |
| 4.7 | Opportunity | 预算审批→报价→采购流程→Won | 只允许顺序推进；Rejected/Won 不被定时过期覆盖 | ☐ |
| 4.8 | Booking | 从 Won Opportunity 创建 Confirmed Booking | 同一商机只允许一个非 Cancelled Booking；重复为 409 | ☐ |

## 5. Demo Request、Evaluation 与档案

| # | 角色 | 操作 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| 5.1 | Sales | Draft 保存、提交、工程退回后修改重提 | 状态和表单数据正确，已创建 Request 不可更换 Opportunity | ☐ |
| 5.2 | Engineer | Engineer Review→Manager Approval | 必填 Test Plan、负责人、日期、风险与答复 | ☐ |
| 5.3 | Manager | Approve/Reject 重复点击 | 只允许一个终态，不重复创建 Evaluation | ☐ |
| 5.4 | Engineer | Requested→Scope Confirmed→Sample Received→Scheduled→Testing | 仅允许相邻状态 | ☐ |
| 5.5 | Engineer | 完成 Wafer/Test preparation，上传报告，新增 Test Run | 文件、12 片 wafer、指标和摘要进入档案 | ☐ |
| 5.6 | Engineer | 无 Completed Run 或无报告时进入 Internal Review | 被稳定拦截并明确提示缺项 | ☐ |
| 5.7 | Engineer | Internal Review→Customer Review→Accepted/Rejected | Accepted 自动推进商机；终态进入 Demo Archive | ☐ |
| 5.8 | 全部 | 从 Calendar 第 21/201 条 Evaluation 打开详情 | 精确 focus 到目标 ID，不选第一条 | ☐ |
| 5.9 | 全部 | 从 Demo Archive 打开记录和 Artifact | 聚合 Request/Evaluation/Test Run/报告，且保持只读 | ☐ |

## 6. Calendar、Dashboard 与通知

| # | 操作 | 预期 | 结果 |
| --- | --- | --- | --- |
| 6.1 | 月/周切换并翻页 | 按当前日期范围请求，不截断每类前 200 条 | ☐ |
| 6.2 | 点击 Visit、Demo Request、Evaluation、Booking 四类事项 | 跳转后显示同一真实业务 ID；Visit 高亮并滚动 | ☐ |
| 6.3 | 快速翻月、切 scope/筛选 | 旧请求不覆盖新视图，仍可见的选中项保留 | ☐ |
| 6.4 | 核对 Dashboard | Pipeline、Weighted、Confirmed Booking、Won 与真实数据一致 | ☐ |
| 6.5 | 单条已读、全部已读制造失败 | 原通知保留、按钮恢复、显示 Request ID | ☐ |

## 7. Installed Tool 与 Document Center

| # | 模块 | 操作 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| 7.1 | Installed Tool | Booking 转设备 | Serial 唯一；重复并发一个成功、一个 409 | ☐ |
| 7.2 | Installed Tool | FAT→Shipment→Installation→SAT→Warranty | 日期单调且不得未来；版本、服务、历史一致 | ☐ |
| 7.3 | Installed Tool | 补录旧服务 | 历史新增，但 `lastService` 不回退 | ☐ |
| 7.4 | Document Center | 文档库成功、某审批列表失败 | 已加载文档仍显示，各板块独立错误 | ☐ |
| 7.5 | Manager | 批准访问/上传 | Pending 项立即移除，badge 收敛；重复点击不产生第二终态 | ☐ |
| 7.6 | 全部 | 申请、审批、预览、下载受控文档 | 水印/原件策略、文件名、Audit 正确 | ☐ |
| 7.7 | 全部 | Quotation PDF、客户 XLSX、其他二进制下载 | 均使用统一下载行为，无空文件或过早 revoke | ☐ |

## 8. 真实半导体全流程数据

固定业务语义：

- 客户：示例企业035有限公司；Site：苏州 12 英寸特色工艺厂。
- 联系人：设备采购负责人、良率工程经理、工艺整合工程师。
- Lead/Opportunity：300mm CIS 晶圆缺陷检测，CNY 4,860,000。
- Demo：12 片 300mm CIS wafer；Capture 96.8%、False Positive 1.1%、WPH 18.5。
- Quotation Accepted、Opportunity Won、Booking Confirmed。
- Installed Tool 完成 FAT→Shipment→Installation→SAT→Warranty，并追加版本和服务记录。
- 验证联系人附件、Demo 报告、受控文档、通知、Account 360、Dashboard、Calendar、Demo Archive。

每次运行必须带唯一 `runId` 和 `dataOrigin=test-acceptance`。测试结束后精确核对零残留；需要人工查看的保留数据只能使用 `dataOrigin=local-acceptance`，并在验收后执行配套精确清理。

## 9. 缺陷登记

| 缺陷 ID | 用例 # | 角色 | URL / 业务 ID | 复现步骤 | 预期 | 实际 | Request ID | 严重度 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BUG-001 |  |  |  |  |  |  |  | P0/P1/P2 | 新建 |

验收结论：P0 全部通过 ☐　P1 全部通过 ☐　验收人：__________　日期：__________
