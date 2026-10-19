# Contact Safe Delete Design

## Goal

让演示员工170可以从 Contacts 主档中清理误建或待复核联系人，同时不破坏 Opportunity、Booking、Demo Request、Visit 和汇报关系的历史引用。

## Root Cause

Contacts 列表下方的记录不是随机数据。旧 Opportunity 与 Booking 的自由文本联系人在主数据升级时被确定性迁移为 `Needs Review` 联系人。典型记录 `CT-BKG-BKG-001` 来自 Booking `BKG-001` 的 `customerContact: 演示员工20`；由于同名种子联系人属于另一客户，客户隔离规则要求新建一条当前客户下的待复核记录。当前列表没有醒目标识数据质量，因此这些记录看起来像异常数据。

## Approved Behavior

- 采用安全归档，不执行物理删除。
- 只有 `CRM Administrator` 可以看到并执行“删除联系人”。
- 删除确认后把 Contact 状态改为 `Archived`，保留原 ID、业务关联、汇报关系与时间线。
- 默认 Contacts 列表不展示 `Archived`；演示员工170仍可通过状态筛选查看归档联系人。
- `Archived` 联系人不能用于新建 Opportunity、Booking、Demo Request 或 Visit 关联。
- 已归档详情页保留只读历史信息，不显示编辑、合并或再次删除操作。
- `Needs Review` 在列表和详情页显示醒目标识，解释其来自旧数据迁移。
- Frappe 删除接口保持明确 `NOT_IMPLEMENTED`，Mock 成功不代表正式后端完成。

## API and Error Handling

- 新增能力 `contact:delete`，仅演示员工170拥有。
- 新增 `CrmApi.deleteContact(id)`。
- Mock API 校验可见范围与演示员工170能力，幂等地将记录设为 `Archived`。
- 不重写或删除任何业务引用。
- 不存在联系人返回 `CONTACT_NOT_FOUND`；非演示员工170返回权限错误。

## Verification

- API 测试覆盖演示员工170归档、非演示员工170拒绝、关联记录保留和重复归档幂等。
- 页面测试覆盖默认隐藏、Archived 筛选、Needs Review 标识、确认删除、删除后返回列表和详情页动作隐藏。
- 浏览器验证 Contacts 列表与详情页，无错误覆盖层或控制台错误。
