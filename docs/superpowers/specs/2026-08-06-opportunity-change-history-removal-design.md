# Opportunity Change History 模块移除设计

## 目标

从 Opportunity 详情页移除整个 `Change History` 展示模块，使用户不再看到字段名、修改前后值、日期和操作人。

## 范围

- 仅修改 Opportunity 详情页前端展示。
- 删除 `Change History` 标题、历史记录列表及对应空白布局占位。
- 保留 Opportunity 的编辑、阶段推进、Action Plan、Commercial Forecast、Buying Influence 等现有功能。
- 保留后端历史记录生成与数据库审计数据，不删除既有历史记录，不修改相关 API 或 DocType。

## 实现方式

在 `src/pages/OpportunityDetailPage.vue` 中删除渲染 `selected.history` 的详情卡片。其他组件、接口和数据结构保持不变。

## 验收标准

1. 打开任意 Opportunity 详情页时，不显示 `Change History` 标题和历史条目。
2. Opportunity 编辑仍可保存并回显。
3. Opportunity 阶段推进仍可保存并回显。
4. 后端历史数据及审计逻辑不受影响。

## 测试

- 先增加页面回归断言，要求 Opportunity 详情页不存在 `Change History` 模块，并确认修复前失败。
- 删除模块后重新运行 Opportunity 详情页及相关流程测试。
- 构建 Frappe 前端资产并验证部署后的 Opportunity 页面资源可访问。
