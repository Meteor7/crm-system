# CRM R4–R6 更新设计

**日期：** 2026-08-10  
**范围：** R4 Manager 权限加固、R5 Demo Test Report 上传与 Article、R6 Installed Tools 流程看板

## 1. 设计目标

- Manager 对 Sales 模块全部数据拥有真实的全局读写与删除能力；Sales 仍只能操作自己的数据；Engineer 边界不变。
- 用用户上传的 Test Report 取代固定模板生成。上传成功后才能离开 Test Execution。
- Demo 详情页用 Article 集中展示并按类型分组 Demo Request Form 与 Test Report，支持预览和下载。
- Installed Tools 以 Stage 看板展示设备当前安装/服务步骤，视觉与 Demo 看板共享实现。
- 不引入新依赖，不重构无关模块，不覆盖当前工作区中其他未提交改动。

## 2. R4：Manager 全局 CRUD 与 Sales 隔离

### 2.1 权限模型

保留三角色模型。前端 `ROLE_PROFILES.Manager.scope` 继续为 `all`，Manager 使用完整能力集合；后端 `ROLE_CAPABILITIES["Manager"]` 与 DocPerm 保持相同语义。

修复 `scope.py` 中 Customer 的 Sales 条件：Manager 在统一的早期分支返回 `1=1`，Sales 必须按 `Customer.custom_crm_owner = 当前用户` 过滤。联系人通过 Dynamic Link 继承客户范围，Opportunity、Booking、Visit 继续按自身 owner 或客户 owner 判断。Engineer 继续只看显式 assignment。

### 2.2 CRUD 接口

现有 Account、Lead、Opportunity、Booking、Visit 缺少顶层删除 API。新增 Manager-only delete service/API/前端适配器契约：

- 删除前先校验对应查看能力、Manager 角色、记录 scope。
- 使用 Frappe 文档删除，保留框架的关联约束；存在被引用数据时返回明确冲突，不级联静默删除。
- Sales 调用删除接口一律返回权限拒绝。
- 联系人及 Opportunity Stakeholder/Action 延续现有删除实现。

前端只在 Manager 具备对应写能力时显示删除操作；Sales 保留新建、查看、编辑自己数据，不显示删除。

### 2.3 权限矩阵

同步 `CRM功能权限可见性矩阵-2026-08-04.md`：明确 Manager 对 Sales 模块全量 CRUD，Sales 仅自己数据且无顶层删除能力，Engineer 不变。

## 3. R5：Test Report 上传与 Article

### 3.1 流程状态

不新增 Evaluation 主状态，避免迁移和下游枚举扩散。`Testing` 内部增加“上传 Test Report”完成条件：

1. 至少一条 Test Run 完成。
2. Engineer 或 Manager 上传 Test Report。
3. 上传成功后 `report_status = Ready`、`report_artifact_id` 指向最新文件、`report_version` 递增。
4. `Testing → Internal Review` 同时要求完成 Test Run 和有效 Test Report artifact。

旧的字段选择、客户端 PDF 构建和服务端固定 PDF 生成不再进入主流程；兼容字段暂不删除，避免破坏已有数据迁移。旧 `release_demo_test_report` API 改为接收 multipart 文件并完成上述上传，前后端契约一致，不再丢弃文件。

### 3.2 上传权限与安全

上传者必须具备 `evaluation:write`，且 Evaluation 在本人 scope 内。允许格式：PDF、DOCX、XLSX、CSV、TXT、PNG、JPEG；单文件最大 10 MiB。

服务端按内容检测而非只信扩展名：

- PDF/PNG/JPEG 使用文件签名。
- DOCX/XLSX 校验安全 ZIP 结构，并拒绝宏格式。
- CSV/TXT 要求可解码文本、拒绝 NUL 字节，并限制内容大小。
- 声明 MIME、扩展名和检测结果必须一致。
- 所有文件继续经过恶意软件扫描；扫描不可用时失败关闭。
- 文件名做路径与长度校验；文件存为 private File；下载时重新校验 scope 并记录审计。

非 PDF 报告不做 PDF 水印转换，保持原始字节下载；浏览器可原生显示的 PDF、PNG、JPEG、TXT 可预览，其余格式提供下载。

### 3.3 Article 模块

新增 `DemoArticleCard.vue`，在 Demo 详情 Information 页使用 `SectionCard`：

- 分组一：Test Report。
- 分组二：Demo Request Form。
- 每项展示文件名、类型、版本、上传人、时间。
- 提供 Preview 与 Download；预览不支持时自动回退到下载。
- 空分组显示明确空态。

数据继续使用 `CRM Demo Artifact`，将 artifact 类型从带格式的 `External Demo Test Report PDF` 调整为格式无关的 `Test Report`；为已有旧类型保留读取兼容映射。Demo workflow DTO 补齐 MIME、上传人等 Article 所需字段。

## 4. R6：Installed Tools 流程看板

### 4.1 共享看板组件

抽取跨 feature 的通用视觉组件到 `src/design-system/`：

- `PipelineBoard.vue`：Stage 轨道、横向滚动和列布局。
- `PipelineStageColumn.vue`：列、计数和统一空态。
- `PipelineCard.vue`：通用卡片壳、状态色、标题/摘要/负责人槽位。

Demo 看板改为通过轻量适配继续使用这些组件；Installed Tools 看板使用同一套组件。所有新增颜色、间距、字号、圆角使用 `tokens.css` 变量；必要的新 token 只添加到 `tokens.css`。

### 4.2 分组事实源

Installed Tool 的 `milestones` 是权威数据。Stage 顺序取当前领域已有顺序（FAT、Shipment、Installation、SAT、Warranty）；每台设备归入首个 `Current` milestone，若无 Current 则归入首个 Waiting，全部 Done 则归入 Warranty/Completed 末列。卡片显示客户、序列号/型号、Engineer 和完成进度。

看板置于 Installed Tools 页面筛选区之后、详情列表之前。选择卡片沿用现有 `selectedId`，不会移除或绕过 `InstalledToolEditorModal.vue`。

## 5. 错误处理与兼容

- 权限和 scope 错误使用现有 `CrmApiError`/`CrmApiException` 编码。
- 删除关联冲突返回可读错误，不做强制级联。
- 上传校验失败不写 File、Artifact 或 Evaluation 状态；事务整体回滚。
- 同一 Evaluation 多次上传按版本递增并保留历史 Article。
- 旧 Test Report artifact 可继续列表和下载；新上传统一写 `Test Report`。
- 当前工作区已有未提交改动按所有权视为用户内容，修改时只做最小上下文补丁。

## 6. 测试与验收

测试采用红—绿—重构：

- R4：前端权限测试；后端 roles/scope 及各 Sales 资源 API 测试，覆盖 Manager 对他人记录增删改查和 Sales 跨 owner 拒绝；更新 stage 验收。
- R5：文件魔数/文本检测、大小、宏/伪 MIME、恶意软件扫描失败；上传事务、版本、流程门禁、Article 分组/空态/预览下载；更新 stage5e/5f。
- R6：`InstalledToolPipelineBoard.test.ts` 覆盖 Current/Waiting/全部完成分组、进度和空态；回归 Demo 看板；更新 stage5d 以验证 milestones 数据。
- 最终运行受影响 Vitest、TypeScript 类型检查、后端单测，以及 stage5d/5e/5f PowerShell 验收。若本机缺少运行中的 Frappe/ClamAV，明确记录无法本地执行的验收项，不以静态检查冒充通过。

## 7. 自检结论

- 无占位内容或未定义接口。
- 三项需求均有代码、数据、权限、错误处理和测试落点。
- 方案不新增依赖，不改变 Engineer 角色语义，不删除旧字段，不触碰无关报价模块。
