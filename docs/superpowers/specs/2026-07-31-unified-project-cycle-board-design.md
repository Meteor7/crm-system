# 统一项目周期看板设计

## 目标

把现有“Demo Request / Demo Test / 已完成”三块式项目周期看板改为一个连续项目列表。每个项目占一行，左侧显示项目名称、当前阶段负责人和 DDL，右侧同时显示该项目的完整周期节点链；已完成项目统一排列在列表最下方。

## 页面结构

- 保留现有顶部汇总、搜索、健康状态、客户、Sales 和 Engineer 筛选。
- 筛选区下方只显示一个看板容器，不再显示 Request、Test、已完成分区标题。
- 看板使用表格式横向结构：
  - 左侧固定信息区：项目名称、当前阶段负责人、DDL。
  - 右侧周期区保留六个分类列：Sales Preparation、Engineer Review、Manager Approval、Wafer & Test Preparation、Test Execution、Customer Review。
  - `Wafer & Test Preparation` 分类列包含两个并行业务节点：Wafer Preparation 与 Test Preparation；两个节点从 Manager Approval 后分叉，并在 Test Execution 前汇合。
  - 悬浮到任一并行节点时显示对应阶段名称；旧时间线缺少 Wafer Preparation 时，沿用 Test Preparation 的状态、负责人和日期自动补齐。
- 每个项目同时渲染自己的节点链，不再通过选择项目切换单条时间线。
- 点击任意项目行打开现有档案详情。

## 排序与状态

- 未完成项目保持现有数据顺序。
- 最近 100 天已完成项目继续沿用现有日期倒序逻辑，并统一追加到未完成项目之后。
- 未完成项目使用当前的 Request 绿色、Test 橙色和加急红色语义。
- 已完成项目使用低对比度灰色，并在列表底部通过细分隔线与上方项目区分，不新增独立分区标题。
- DDL 使用 `YYYY-MM-DD`；缺失时显示“待确认”；临近或逾期项目继续使用红色提示。

## 当前阶段负责人

从项目的完整周期节点中取状态为 `Current` 的节点负责人。若当前节点没有负责人，则按现有数据回退到 Engineer Owner；若仍为空则显示“待确认”。不新增后端字段。

## 响应式与滚动

- 桌面端左侧信息列保持稳定宽度，右侧周期节点区填充剩余空间。
- 宽度不足时，看板整体提供横向滚动，保证节点顺序和连线不压缩变形。
- 小屏幕仍保留完整项目行，不改成卡片，不隐藏节点。

## 影响范围

- 修改 `src/features/demo-workflow/DemoProjectCycleBoard.vue`，改为连续行布局并处理行级详情入口。
- 修改 `src/features/demo-workflow/DemoProjectTimeline.vue`，增加适合项目行的上下文隐藏能力，复用现有节点状态和色调。
- 更新 `src/pages/DemoWorkflowPage.test.ts` 的项目周期看板断言。
- 不修改 Mock 数据、路由参数、筛选数据流、档案详情页或 Frappe 适配器。

## 验收标准

- 页面只存在一个连续项目列表，不存在三个项目周期分区。
- 默认数据下显示 10 个项目行，最后两行为最近 100 天已完成项目。
- 每个项目行都有项目名称、当前阶段负责人、DDL，以及六个分类列中的七个业务节点。
- 点击进行中或已完成项目行都能打开对应档案详情。
- 客户等现有筛选继续生效并保持 URL 查询参数行为。
- 聚焦测试通过，Vite 构建通过，浏览器中无控制台错误。
