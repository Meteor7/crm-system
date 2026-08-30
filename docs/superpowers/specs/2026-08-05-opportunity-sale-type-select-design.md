# Opportunity Sale Type 下拉框设计

## 目标

消除 Opportunity 新建与编辑时自由填写 `saleType` 导致的后端枚举校验错误。销售类型改为固定英文下拉选项，并兼容当前前端 Mock 数据中的旧值。

## 范围

- 仅修改 Opportunity 新增/编辑共用弹窗。
- `saleType` 使用原生 `select`，不再允许自由文本输入。
- 下拉框显示和提交以下后端认可的精确英文值：
  - `New Equipment`
  - `Repeat Order`
  - `Service`
- 新建 Opportunity 的默认值为 `New Equipment`。
- 编辑旧数据时执行以下前端初始化映射：
  - `New Tool` → `New Equipment`
  - `Capacity Expansion` → `Repeat Order`
- 已经是合法枚举的值保持不变。

## 数据流

1. 弹窗初始化时读取 `opportunity.saleType`。
2. 初始化辅助函数将旧值映射到合法枚举；缺失值回退到 `New Equipment`。
3. 用户只能从三个合法选项中选择。
4. 提交 payload 继续使用现有 `saleType` 字段，不改变 API 结构。

## 保持不变

- 不修改 Frappe 后端枚举、DocType 或数据库。
- 不修改 Opportunity 其他字段、成交概率计算、权限或校验。
- 不迁移已存储数据；兼容映射仅发生在表单初始化阶段。
- 不修改 Opportunity 详情页与列表页的显示格式。

## 验收标准

1. 新建 Opportunity 时销售类型默认选中 `New Equipment`。
2. 下拉框只包含 `New Equipment`、`Repeat Order`、`Service`。
3. 编辑 `New Tool` 旧记录时自动选中 `New Equipment`。
4. 编辑 `Capacity Expansion` 旧记录时自动选中 `Repeat Order`。
5. 编辑合法值时原值保持不变。
6. 聚焦测试与 Frappe 前端生产构建通过。
7. 本地 Docker 前端刷新后保持健康，且不删除 volumes。
