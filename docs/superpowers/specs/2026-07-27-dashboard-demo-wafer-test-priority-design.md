# 数据看板 Demo / Wafer Test 状态前置设计

## 目标

在管理者“信息中心”的数据看板中，用“Demo / Wafer Test 状态”替换“团队业绩与管线”，并将其作为数据看板第一张图表展示。

## 展示顺序

数据看板固定保留三张图表，顺序如下：

1. Demo / Wafer Test 状态
2. 实际 Booking 月度分布
3. 重点客户金额贡献

## 数据与交互

- “Demo / Wafer Test 状态”直接使用现有 `process.evaluationByStatus` 数据。
- 图表继续使用现有数量分布横向柱状图，不增加新的数据转换或接口。
- 图表标题为“Demo / Wafer Test 状态”，眉题为“EVALUATION”。
- 图表说明为“按当前 Demo 与 Wafer Test 记录汇总各执行状态。”
- 无数据时展示“暂无 Demo / Wafer Test 状态记录”。
- “查看更多分析”中的同名图表移除，避免同一数据在页面重复展示。
- 原“团队业绩与管线”图表不再出现在信息中心，其他分析图表保持不变。

## 技术边界

- 仅修改 `DashboardPage.vue` 及其页面测试。
- 复用现有 `buildCountBreakdownOption` 和 `DashboardDto.process.evaluationByStatus`。
- 不修改 Dashboard 数据聚合、Mock 数据、API、权限或其他页面。
- 不新增依赖，不调整当前前端服务端口。

## 验收标准

- 管理者进入信息中心后，数据看板第一张图表为“Demo / Wafer Test 状态”。
- 数据看板不再显示“团队业绩与管线”。
- 数据看板仍保持三张图表。
- 展开“查看更多分析”后，不再重复显示“Demo / Wafer Test 状态”。
- 管理者与非管理者原有页面权限和内容不受影响。
- Dashboard 页面测试、类型检查和构建通过。
- 当前 `4173` 页面实测布局、图表数量与控制台状态演示员工152。
