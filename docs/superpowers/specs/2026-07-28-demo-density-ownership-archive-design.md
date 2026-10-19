# Demo 高密度看板、双负责人和档案分类设计

**日期：** 2026-07-28
**范围：** `Demo 档案` 页面及其 Mock 数据投影、负责人范围和旧数据迁移
**部署目标：** 当前 Vue/Mock 应用的 4173 局域网热更新服务

## 1. 目标

本轮解决三个直接问题：

1. 活跃 Demo 增长到约 30–40 个时，五阶段看板仍然可读、可搜索、可滚动。
2. 每个 Demo 始终有且只有一个 Sales Owner 和一个 Engineer Owner，两位负责人贯穿 Request、Approval、Test、Customer Review 和最终档案。
3. `Demo 档案` 页面提供“生命周期看板”和“Demo 档案”两个视图。前者负责进行中的 Demo，后者负责已经结束的 Demo 留痕，并支持按客户或设备分类。

本轮不恢复已经移除的系统 Q&A，也不恢复 On Hold。

## 2. 页面信息架构

页面标题继续使用 `Demo 档案`。标题下方增加分段切换：

- `生命周期看板`
- `Demo 档案`

默认进入生命周期看板。URL 使用独立的 `surface` 参数保存视图：

- `surface=board`：生命周期看板，缺省时等同于此值。
- `surface=archive`：Demo 档案。
- `view=detail&focus=<Demo Request ID>`：在当前 surface 中打开详情。

详情返回时回到原 surface，并保留搜索、健康状态、负责人、归档状态和分组维度。

## 3. 生命周期看板

### 3.1 容量策略

预计活跃 Demo 总量为 30–40 个，因此不引入虚拟列表、服务端分页或新依赖。

采用以下组合：

- 卡片高度控制在约 110–125px。
- 每个阶段列拥有固定可视高度和独立纵向滚动。
- 生命周期横轴和阶段数量始终可见。
- 桌面端五列保持同屏；窄屏继续横向滚动。
- 搜索和筛选只改变列内卡片，不改变生命周期结构。

每列一屏可见约 5–7 张卡片。即使 Demo 集中在同一阶段，页面也不会无限向下增长。

### 3.2 卡片内容

卡片只显示：

- 客户名称。
- Demo ID 与简短标题。
- `Sales <name> · Engineer <name>`。
- 红、橙、绿健康原因。

卡片继续不显示：

- Test Run DDL。
- 客户预期日期。
- 任何 ISO 日期。
- 人物头像。

### 3.3 筛选

生命周期看板支持：

- 关键词：客户、Demo ID、标题、Sales Owner、Engineer Owner、设备。
- 健康状态：全部、红、橙、绿。
- Sales Owner。
- Engineer Owner。

CRM Administrator 和 Management Viewer 默认看全部。Sales User 和工程师角色默认只获取本人负责的 Demo；筛选不能绕过权限范围。

## 4. Demo 档案视图

### 4.1 收录范围

Demo 档案视图只收录已经形成 Evaluation 且状态为：

- `Accepted`
- `Rejected`

`Draft`、`Cancelled` 和仍在执行中的 Demo 不进入此视图。

### 4.2 结构

复用旧版“左侧档案列表 + 右侧详情”的信息结构，但不恢复旧版系统 Q&A。

左侧提供分组维度切换：

- `按客户`
- `按设备`

默认按客户分组。每个分组显示名称和档案数量，展开后显示该组内的归档 Demo。设备分类使用 Demo Request 的 `assignedEquipment`，没有分配设备时使用 `requestedEquipment`。

档案工具栏支持：

- 关键词搜索。
- 归档结果：全部、Accepted、Rejected。
- Sales Owner。
- Engineer Owner。
- 分组维度：客户、设备。

组内档案按最近有效进展时间倒序排列。

### 4.3 详情

右侧详情继续展示：

- Demo Request 正式快照。
- Sales Owner 与 Engineer Owner。
- 审批与 Customer Review 轨迹。
- Demo Test 与 Test Runs。
- Artifacts 和已发布报告。
- Demo Conclusion。

详情不展示系统 Q&A，也不展示 On Hold。

## 5. 双负责人数据规则

### 5.1 单一来源

每个 `DemoRequestDto` 使用：

- `salesOwner`：唯一 Sales Owner。
- `engineerOwner`：唯一 Engineer Owner。

`DemoWorkflowDto` 明确投影两个字段，不再用单一 `owner` 混淆两种职责。为兼容旧适配器，`owner` 可暂时保留为 Engineer Owner 的只读别名，但新组件不再依赖它。

### 5.2 创建和流转

- 创建 Demo Request 时，`salesOwner = formData.salesContact`。
- 创建 Demo Request 时，`engineerOwner = formData.demoOwner`。
- 两个字段均为必填；现有表单校验已经要求 Sales Contact 和 Demo Owner 非空。
- FAE Review 可以将 Engineer Owner 重新指派为另一个具体工程师，但同一时刻只能有一个 Engineer Owner。
- Boss Approval 创建 Evaluation 时，`evaluation.owner = request.engineerOwner`，不再使用 `FAE Team` 兜底。
- 工程师变更通过 Request history 留痕。

`FAE Team`、`未分配` 和空字符串不再是有效的最终 Engineer Owner。

### 5.3 旧数据迁移

旧 Snapshot 升级时补齐负责人：

1. 优先使用已经存在的具体 `request.engineerOwner`。
2. 其次使用关联 `evaluation.owner`。
3. 再次使用 `formData.demoOwner`。
4. Mock 旧数据仍无具体人员时，按业务线确定默认工程师：
   - Frontend：`FAE Leo`
   - Advanced Packaging：`FAE Mia`

迁移不覆盖已经存在的具体负责人，也不删除 Request、Run、Artifact 或 Word 表单内容。

## 6. 负责人权限范围

列表投影在数据进入页面前完成：

- Sales User：仅本人为 `salesOwner` 的 Demo。
- FAE / Applied Engineer：仅本人为 `engineerOwner` 的 Demo。
- Equipment Engineer：仅本人为 `engineerOwner` 的 Demo。
- Sales Manager：仅团队 Sales Owner 的 Demo。
- Management Viewer：全部可见，只读。
- CRM Administrator：全部可见。

同一规则应用于 Demo Request、Demo Test、生命周期看板和 Demo 档案，避免三个模块数量不一致。

## 7. 组件边界

- `DemoWorkflowPage.vue`：管理 surface、详情、查询参数和权限范围内的数据。
- `DemoPipelineBoard.vue`：生命周期筛选和五阶段布局。
- `DemoPipelineCard.vue`：紧凑卡片和双负责人展示。
- `DemoArchiveBrowser.vue`：归档筛选、客户/设备分组和档案选择。
- `DemoArchiveGroup.vue`：单个客户或设备分组。
- `DemoArchiveDetail.vue`：复用现有详情展示，避免页面文件继续增长。

归档浏览与生命周期看板只共享 DTO 和详情组件，不共享互相无关的布局状态。

## 8. 异常和空状态

- 生命周期阶段无 Demo：保留阶段空状态。
- 搜索或负责人筛选无匹配：五阶段仍显示，每列为空。
- Demo 档案无归档：展示“暂无已归档 Demo”。
- 分组无匹配：不创建空分组。
- 详情 focus 无权限或不存在：提示后返回来源 surface。
- 历史负责人无法识别：迁移为业务线默认具体工程师，而不是团队占位符。

## 9. 验收标准

### 9.1 密度

- 30–40 个活跃 Demo 时页面高度不随卡片总量无限增长。
- 每个阶段列可独立纵向滚动。
- 卡片仍能完整辨认客户、Demo、Sales、Engineer 和健康状态。
- 卡片无日期和头像。

### 9.2 负责人

- 新建 Request 后立即具有唯一 Sales Owner 和 Engineer Owner。
- Boss Approval 后 Evaluation Owner 与 Engineer Owner 相同。
- Sales、工程师和管理者获取的数据范围符合角色规则。
- 旧 Snapshot 中的空负责人或 `FAE Team` 被迁移为具体人员。

### 9.3 双视图和档案分类

- 页面可在“生命周期看板”和“Demo 档案”之间切换。
- Demo 档案仅包含 Accepted / Rejected。
- 可按客户和设备分组。
- 可按结果和负责人筛选。
- 点击归档记录进入原有详情，返回后保留分组和筛选。
- 系统 Q&A 和 On Hold 不重新出现。

### 9.4 验证

- 领域和迁移单元测试。
- Mock API 角色范围测试。
- 页面组件与路由查询测试。
- TypeScript 类型检查。
- 生产构建。
- 4173 桌面端与窄屏浏览器验收。
- 4173 响应包含 Vite HMR 客户端，源码修改可自动更新。
