# CRM 系统测试账号产品发布提示

## 目的

当前 staging/FAT 使用的系统测试账号仅用于多角色验收、权限验证和问题复现，不属于正式业务人员。

当前账号：

- `person008@staff.example.invalid`
- 用途：staging/FAT 测试
- 当前角色：`CRM Manager`

## Product 发布前强制处理

在 Product 环境发布前，必须完成以下操作，不能将该账号作为正式业务账号保留：

1. 在 Product 数据库中确认不存在该账号，或将其禁用并移除全部 CRM 角色。
2. 清理该账号产生的测试业务记录、测试附件、测试通知和测试会话；如记录需要保留作审计，必须改由正式业务账号归属并经过业务负责人确认。
3. 检查人员目录和所有负责人选择器，不得出现该账号。
4. 检查 Customer、Contact、Lead、Opportunity、Booking、Visit、Demo Request、Evaluation、RFQ、Quotation、Installed Tool 及通知列表，不得残留该账号作为 Owner、Actor、Reviewer 或 Recipient。
5. 发布后使用 Manager、Sales、Engineer 正式账号重新执行登录、权限、人员目录和关键列表验收。

## Staging 使用边界

- 该账号只允许用于 staging/FAT，不得用于 Product 登录、数据导入或业务审批。
- 测试报告中必须单独标记该账号产生的测试数据，不能把测试数据当作正式业务数据统计。
- 任何需要修改 staging 数据的 FAT，都必须先备份并记录恢复方式。

## 发布 Gate

只有在“账号已删除或禁用”“CRM 角色已移除”“业务记录和人员目录复核通过”三个条件全部满足后，Product 发布才允许继续。
