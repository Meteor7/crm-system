# Demo 生命周期与档案分类设计

**日期：** 2026-07-22  
**状态：** 已确认设计，等待书面规格复核  
**范围：** 仅修改 Vue / Mock Demo，不接入 Frappe 后端

## 1. 目标

统一 Demo Request、Demo Test 与 Demo 档案的生命周期，消除三个模块数量和关联关系不一致的问题：

- Demo Request 只承载申请、FAE Review 与 Boss Approval，不再展示“已完成”栏目。
- Boss 批准后创建或关联 Demo Test，Request 从 Demo Request 工作区移除。
- Demo Test 只展示尚未结束的测试；`Accepted` 或 `Rejected` 后转入历史档案。
- Demo 档案展示全部非取消 Demo，并区分“进行中的 Demo”和“已完成历史归档”。
- 已完成历史中的已发布 External Demo Test Report PDF 对有权成员持续开放下载。
- 移除南京 Fab 的旧 `reportLink` 外部接口与卡片按钮，保留正式的 External Report PDF 流程。

## 2. 采用方案

采用“共享 Demo Repository + 动态聚合档案”方案。

Demo 档案不保存第三份业务副本，而是每次从 Demo Request、Evaluation、Test Run、Q&A 和 Artifact 聚合。状态变化只修改源记录，三个模块读取同一份 IndexedDB 数据。

不采用独立档案快照，因为它会引入 Request/Test/Archive 三份状态同步；不采用仅调整页面分类，因为它无法修复旧数据缺少提交历史或 `demoRequestId` 的问题。

## 3. 生命周期规则

### 3.1 Demo Request

Demo Request 页面只显示以下状态：

- `Draft`
- `Engineer Review`
- `Engineer Returned`
- `Manager Approval`
- `Manager Rejected`

页面删除“已完成”栏目。`Converted` 表示 Boss 已批准并生成 Demo Test，因此不再显示于 Demo Request。`Cancelled` 不进入 Demo Test，也不进入 Demo 档案。

Boss Approval 成功时必须在同一个 Repository 事务内：

1. 将 Request 设为 `Converted`。
2. 创建或关联唯一的 Evaluation。
3. 写入双向关联：`request.evaluationId` 与 `evaluation.demoRequestId`。

### 3.2 Demo Test

Demo Test 页面只显示未完成 Evaluation：

- `Requested`
- `Scope Confirmed`
- `Sample Received`
- `Scheduled`
- `Testing`
- `Analysis`
- `On Hold`
- `Customer Review`

完成判定只使用 Evaluation 状态：

- `Accepted`：已完成并接受。
- `Rejected`：已完成但未接受。

`Accepted` 和 `Rejected` 不再显示于 Demo Test，而是显示在 Demo 档案的“已完成历史归档”。

### 3.3 Demo 档案

Demo 档案不再使用“历史中是否存在进入 Engineer Review 的事件”作为显示条件。除 `Cancelled` 外，每个 Demo Request 都形成一个档案视图。

分类规则：

- **进行中的 Demo：** Request 尚未生成 Evaluation，或 Evaluation 状态不是 `Accepted / Rejected`。
- **已完成历史归档：** Evaluation 状态为 `Accepted / Rejected`。

每个档案继续同步展示 Request、客户预期时间、Q&A、FAE/Boss 审批、Test Run DDL、Test Run、Artifacts、结论和当前状态。Draft 根据现有角色范围控制可见性，Boss 仍看不到 Draft。

## 4. Report 规则

- External Report 仍在现有正式 PDF 流程中生成、发布并保存为 Artifact。
- 历史档案只提供已发布版本，即 `reportStatus === 'Released'` 且 Artifact 为 Evaluation 当前的 `reportArtifactId`。
- 拥有 `demo_request:view` 且通过客户/团队范围过滤的成员可以从历史档案下载已发布 PDF。
- 未发布预览、内部分析和旧外链不进入历史下载。
- 删除 `EvaluationDto.reportLink`、南京 Fab 种子数据中的示例 URL，以及 Evaluation 卡片上的旧 `Report` 外链按钮。

## 5. 旧数据迁移

IndexedDB Snapshot 升级到版本 2，并在读取旧版本时原位迁移，禁止清空用户已经填写的数据。

迁移步骤：

1. 保留全部 Request、Question、Evaluation、Run、Artifact 和 Blob。
2. 对缺少 `demoRequestId` 的 Evaluation，优先按现有 `request.evaluationId` 关联；否则按相同 `accountId + requirementId` 唯一匹配。
3. 回写 `request.evaluationId`，保证双向关联一致。
4. 对非 Draft 且缺少提交历史的旧 Request 补充一次 `Draft -> Engineer Review` 历史事件，仅用于审计完整性，不再作为档案显示门槛。
5. 删除旧 Evaluation 的 `reportLink` 字段。
6. 迁移失败时保留旧快照并返回明确错误，不覆盖或清空数据。

## 6. 权限

- 档案记录仍先经过现有客户/团队 scope 过滤。
- Boss / CRM Administrator 查看其权限范围内的完整档案。
- Sales 查看本人或团队范围内的业务信息和已发布客户报告。
- FAE 与设备工程师继续使用相同能力和分配范围，可查看工程信息及已发布报告。
- Demo 前端权限只用于演示；生产环境仍必须由 Frappe 后端执行记录、字段和文件权限。

## 7. 错误处理

- Boss Approval 创建 Evaluation 失败时，Request 不得单独变为 `Converted`。
- 找不到唯一 Request/Test 关联时，保留记录并显示为未关联，不得静默绑定到多个 Request。
- Report Artifact 缺失时显示“报告文件不可用”，不恢复旧 `reportLink`。
- 迁移失败不得重置 IndexedDB。

## 8. 测试与验收

- Demo Request 页面没有“已完成”栏目，也不显示 `Converted / Cancelled`。
- Boss Approval 后同一项目从 Demo Request 消失并出现在 Demo Test。
- `Customer Review` 仍在 Demo Test；`Accepted / Rejected` 只在历史档案。
- Demo 档案包含所有权限范围内的非取消 Request，并正确分成进行中与历史两类。
- 旧 Snapshot 自动补齐 Request/Test 双向关联且保留已有 Q&A、Run 与 Artifact。
- 有权成员可下载历史档案中的当前已发布 PDF；未发布或越权文件不可下载。
- 南京 Fab 卡片不再出现旧 Report 外链；正式 External Report 操作仍存在。
- 定向测试、类型检查和生产构建通过。

