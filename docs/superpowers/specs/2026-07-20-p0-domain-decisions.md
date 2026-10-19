# QIHENG Demo CRM P0 领域决策

**日期：** 2026-07-20
**状态：** P1 前端原型的固定基线
**适用范围：** 核心 Sales CRM、Demo/Wafer/Test Run、Controlled Documents MVP、最小版 Installed Tool

## 1. 共享主数据与编码

| 对象 | 唯一标识 | 规则 |
|---|---|---|
| Customer | `customer_code` | 继续使用已确认的 `客户简称-年份-三位序号`，完整编号唯一且建档后不可修改 |
| Customer Site | `site_code` | `{customer_code}-SITE-{两位序号}`，同一客户内唯一 |
| Product / Tool Model | `model_code` | 使用产品正式型号，例如 `AX-9000`，全局唯一 |
| Installed Tool | `serial_number` | 制造序列号全局唯一；内部记录名使用 `INST-{serial_number}` |
| Opportunity | `opportunity_code` | `OPP-年份月份-序号`，全局唯一 |
| Demo Request | `demo_request_code` | `DEMO-年份月份-序号`，全局唯一 |
| Demo Execution | `execution_code` | `{demo_request_code}-EXE-{两位序号}` |
| Controlled Document | `document_id + version + revision` | 三者组合唯一；同一 `document_id` 同时只能存在一个 Current Released Version |

Customer、Site、Product、Tool Model、User 和 Team 只建立一份主数据，其他模块通过标识引用，不复制名称作为新的主档。

## 2. 角色、范围与审批责任

| 角色 | 数据范围 | P1 责任 |
|---|---|---|
| CRM Administrator | 全部 | 主数据、字典、权限和异常处理 |
| 管理者权限 | 全部只读 | 管理驾驶舱、跨团队商机和业务记录 |
| Sales Manager | 本团队 | 商机复核、Demo 最终批准、重大红旗和行动审阅 |
| Sales User | 本人及被分配客户 | 客户、商机、Stakeholder、Action 和 Demo 申请 |
| FAE / Application Engineer | 被分配 Demo 和关联客户 | Scope Review、Demo Execution、Wafer 和 Test Run |
| Document Manager | 被授权文档域 | 文档审核、发布、作废、原始文件和访问授权 |

Demo 审批固定为：Sales提交 → FAE Scope Review/退回 → FAE确认 → Sales Manager批准/拒绝。Controlled Document发布固定为：Owner提交 → Reviewer技术审核 → Document Manager批准并发布。访问申请由申请人的直属Manager审批，Restricted文档还需Document Manager复核。

## 3. Opportunity 与 Stakeholder

Stakeholder是Customer级主档；Opportunity通过关联记录引用Stakeholder。同一Stakeholder可以参与多个Opportunity，每个Opportunity可以关联多个Stakeholder。

机会关联记录保存：Buying Role、Influence、Attitude、Coverage Evidence、Win Result和机会内备注。这些字段属于“Stakeholder在当前机会中的作用”，不能覆盖Customer级联系人主档。

## 4. Demo Request 与 Demo Execution

- Demo Request表达业务申请、客户目标、成功标准、审批和总体责任。
- 一个Demo Request允许有一个或多个Demo Execution，以支持不同设备、不同时间窗口或复测。
- Wafer Sample属于Demo Request，可被多个Execution引用，但每次使用必须保留收发和状态记录。
- Test Run必须属于一个Demo Execution，并引用实际使用的Wafer Sample。
- Demo Conclusion汇总Execution和Test Run结果；客户确认后才能更新商机Action或阶段。

前端P1允许先展示一个主Execution，同时保留一对多的数据结构和切换入口。

## 5. Installed Tool 唯一标识

客户已交付设备以制造Serial Number作为不可变全局唯一标识。Tool Model、客户、Site、安装位置、软件版本、质保和服务状态可以变化，但Serial Number不允许修改或复用。

公司Demo Tool、租赁设备和客户已售设备未来通过`ownership_type`区分；本次最小版Installed Tool只展示客户已交付设备，不建设完整库存或固定资产模块。

## 6. Controlled Document 可见性与内容访问

权限分为两层：

1. **Catalog Visibility**：是否能看到标题、Document ID、类型、Current Version和Owner。
2. **Content Access**：是否能预览或下载文件内容。

固定规则：

- Internal技术文档：登录员工可见目录；相关工程角色可直接访问，其他人申请。
- Commercial文档：Sales、Sales Manager、管理者权限和Document Manager可见目录。
- Restricted、价格、合同和客户专属文档：只对Account Team、管理者权限和Document Manager显示目录。
- 普通获批用户默认只能获得带个人化水印的PDF，不获得主文件URL。
- 原始可编辑文件仅Document Manager或显式特批人员访问。
- Access Request必须记录原因、关联业务对象、有效期、审批人和撤销状态。

P1前端只演示目录、访问策略、申请状态和水印说明；不提供真实文件链接，不声称已经实现服务端安全控制。

## 7. P1 完成边界

- Core Sales CRM：沿用客户与拜访基础，新增Opportunity Strategy及机会级Stakeholder、Strength、Red Flag、Information Needed和多Action展示。
- Demo：展示Demo Request、Execution、Wafer Sample、Test Run和Conclusion关系。
- Controlled Documents：展示目录、Current Version、两层访问规则和Access Request状态。
- Installed Tool：展示唯一序列号、Customer/Site、交付里程碑、软件版本、质保和适用文档。
- Field Service、Procedure Run、动态PDF生成和真实下载审计不属于本批实现。

