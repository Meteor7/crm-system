# CRM Frappe 命名与 legacy_id 迁移约定

**日期：** 2026-08-04
**状态：** Stage 2 契约冻结；待 Frappe DocType 与导入脚本实现验证
**权威上游：** `docs/CRM-后端数据库对接契约-2026-08-04.md` A6

## 1. 强制原则

1. 正常 create API 不接受 `name`、`id`、`legacy_id` 或任何客户端指定主键。
2. Frappe 服务端按 DocType 独立 naming series 生成 `name`；不同 DocType 不复用业务前缀。
3. 旧 Mock ID 只写入自定义字段 `legacy_id`，不可变、不可作为新记录外键、不可用于正常 create/update API 寻址。
4. `legacy_id` 在每个 DocType 内建立唯一索引；跨 DocType 可以出现相同旧值，但必须通过 `(doctype, legacy_id)` 解析。
5. 所有旧外键先通过受控映射表转换为新的 Frappe `name`，再写入 Link 字段。存在重复、孤儿或类型歧义时整批事务失败，不允许写空串或猜测目标。
6. 导入脚本必须幂等：同一 `(doctype, legacy_id)` 重跑返回同一 `name`，不得创建第二条记录。

## 2. 独立命名空间

| 实体 / DocType | Frappe naming series | legacy 字段 |
|---|---|---|
| CRM Account | `CRM-ACC-.#####` | `legacy_id` |
| CRM Site | `CRM-SITE-.#####` | `legacy_id` |
| Contact | `CRM-CNT-.#####` | `legacy_id` |
| CRM Lead | `CRM-LEAD-.#####` | `legacy_id` |
| CRM Opportunity | `CRM-OPP-.#####` | `legacy_id` |
| CRM Opportunity Stakeholder | `CRM-STK-.#####` | `legacy_id` |
| CRM Opportunity Action | `CRM-ACT-.#####` | `legacy_id` |
| CRM Booking | `CRM-BKG-.#####` | `legacy_id` |
| CRM Visit | `CRM-VIS-.#####` | `legacy_id` |
| CRM Requirement | `CRM-REQ-.#####` | `legacy_id` |
| CRM Contract | `CRM-CTR-.#####` | `legacy_id` |
| CRM Demo Request | `CRM-DR-.#####` | `legacy_id` |
| CRM Evaluation | `CRM-EVAL-.#####` | `legacy_id` |
| CRM Test Run | `CRM-RUN-.#####` | `legacy_id` |
| CRM Demo Artifact | `CRM-ART-.#####` | `legacy_id` |
| CRM Contact File | `CRM-CF-.#####` | `legacy_id` |
| CRM Installed Tool | `CRM-IT-.#####` | `legacy_id` |

Contact 旧值 `CON-001` 与 Contract 旧值 `CON-001` 必须分别解析为 `Contact/legacy_id=CON-001` 和 `CRM Contract/legacy_id=CON-001`；任何仅以字符串 `CON-001` 全局查询的迁移逻辑均不合规。

## 3. 映射表与导入顺序

迁移过程维护受控映射表：

```text
source_doctype | legacy_id | target_doctype | frappe_name | imported_at | source_hash
```

- 唯一键：`(source_doctype, legacy_id)`。
- `source_hash` 用于检测同一旧 ID 的源数据被悄然修改；hash 不一致时停止并要求显式迁移裁决。
- 映射表不包含密码、Token、Cookie 或文件正文。

建议顺序：Account → Site → Contact/Lead → Opportunity → Booking/Visit/Requirement/Contract → Demo Request → Evaluation/Test Run/Artifact → Installed Tool。每批先创建主记录并登记映射，再解析 Link；批内任一 Link 无法解析时整体回滚。

## 4. 后端验收 Gate

- 正常 create 端点提交 `id/name/legacy_id` 时服务端忽略或拒绝，且绝不据此命名。
- Contact 与 Contract 的相同旧 ID 能迁移为不同、稳定且类型正确的 Frappe `name`。
- 重跑迁移记录数不增加，映射不变化。
- 注入重复 `legacy_id`、孤儿外键、错误 DocType 或 source hash 漂移时，事务完整回滚。
- 所有 Link 字段只保存 Frappe `name`，没有空串外键或遗留 Mock 主键。

以上集成测试通过前，权威契约 A6 保持未勾选；本文件只证明命名与迁移策略已经冻结。
