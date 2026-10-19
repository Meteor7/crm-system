# CRM 三类权限与人员契约设计

## 目标

将当前六个技术角色统一为 `Manager`、`Sales`、`Engineer` 三类权限契约，建立唯一人员目录，并禁止新建或编辑业务数据时通过自由文本产生无法对应到系统人员的负责人。

本轮只修改前端 Mock Demo，不接入 Frappe、数据库或生产身份系统。

## 人员目录

| 权限大类 | 人员 | 默认数据范围 |
| --- | --- | --- |
| Manager | 演示员工24、演示经理01、Demo Staff 06 | 全部数据 |
| Sales | Demo Staff 01、Demo Staff 02 | 本人负责的数据 |
| Engineer | 演示员工14、演示员工15 | 分配给本人的客户、Demo、设备与服务数据 |

人员目录是负责人选择、Demo 身份切换、Mock 权限判断和写入校验的唯一来源。业务数据继续存储人员姓名以兼容现有 DTO，但所有新写入的姓名必须来自人员目录。

## 权限契约

| 模块或动作 | Manager | Sales | Engineer |
| --- | --- | --- | --- |
| Dashboard | 全局查看与管理视图 | 查看本人范围 | 查看分配范围 |
| 客户、联系人、需求 | 全局读写 | 本人范围读写 | 分配范围只读 |
| Lead、Opportunity、Booking | 全局读写 | 本人范围读写 | 分配范围只读 |
| 拜访 | 全局读写与审核 | 本人范围创建和维护 | 分配范围查看 |
| Demo Request | 全局读写、工程审核和经理审批 | 本人范围创建和维护 | 分配范围工程审核 |
| Demo Test / Evaluation | 全局读写与报告发布 | 本人客户范围查看 | 分配范围读写 |
| Installed Tool / Service | 全局读写 | 本人客户范围查看 | 分配范围读写 |
| 演示员工116 | 全局查看 | 本人客户范围查看 | 不提供演示员工116能力 |
| 系统配置 | 允许 | 不允许 | 不允许 |

Manager 保留当前演示员工170、老板和销售经理能力的并集。Sales 与 Engineer 的数据范围仍由当前身份姓名、客户负责人和工程分配关系决定，不能仅依赖界面隐藏。

## 人员选择规则

新增统一人员选择组件或统一选项函数，并按字段语义限制候选人：

| 字段类型 | 可选人员 |
| --- | --- |
| 客户、联系人、Lead、Opportunity、Booking、销售行动、拜访负责人 | Sales |
| Demo、Evaluation、Installed Tool、Service 工程负责人 | Engineer |
| 拜访纪要行动负责人 | Sales 或 Engineer |
| 审批人 | 当前登录的 Manager 自动记录，不允许手填 |

现有有效值保持不变。若历史本地存储出现目录外姓名，页面允许只读显示，但再次保存前必须重新选择有效人员；Mock API 同时执行写入边界校验，阻止绕过下拉框提交非法姓名。

## 数据同步边界

人员变更必须沿现有业务外键和存储边界传播：

1. 人员目录提供身份、角色、团队和分配客户。
2. API 根据当前人员计算可见客户，再过滤 Contact、Requirement、Opportunity、Booking、Visit、Demo Request、Evaluation、Installed Tool 与通知。
3. 新建或编辑记录写入负责人姓名后，列表、详情、Dashboard、通知和关联客户视图必须重新读取同一数据源。
4. Sales 工作区仍由 `localStorage` 保存；Demo 工作流与附件仍由 IndexedDB 保存；静态 Mock 种子只作为初始数据。不得把任一存储单独描述为完整数据源。
5. 身份切换后重新创建 API，并刷新业务数据与通知，不能保留上一身份的缓存结果。

## 兼容与迁移

- 将旧角色映射为三类：`CRM Administrator`、`Management Viewer`、`Sales Manager` -> `Manager`；`Sales User` -> `Sales`；`FAE / Applied Engineer`、`Equipment Engineer` -> `Engineer`。
- 对浏览器中仍保存旧身份 ID 的情况保留身份 ID 兼容，加载后使用新的三类角色。
- Dashboard 订阅等与人员无关的本地设置不重置。
- 不批量删除业务数据；目录外历史负责人仅在编辑保存时要求修正。

## 验收与对抗性审查

实施必须先写失败测试，再进行最小修改。完成后验证：

1. 目录中的每个人恰好属于一个权限大类。
2. 所有新建和可编辑负责人字段不再是自由文本。
3. UI 选择和 Mock API 写入校验使用同一人员目录。
4. Manager 可跨人员查看和操作；Sales 不能读取或写入其他 Sales 的数据；Engineer 不能读取或写入未分配数据。
5. 身份切换后列表、详情、Dashboard 与通知同步刷新。
6. 业务链 `Lead -> Account -> Contact -> Requirement -> Opportunity -> Booking -> Demo Request -> Demo Test -> Installed Tool` 的负责人及可见范围一致。
7. 运行定向测试、全量测试、类型检查和生产构建，并把非本轮遗留失败单独列出。

最终在 Windows 桌面生成 Markdown 报告，至少包含接口契约表、三类权限矩阵、人员分配表、负责人字段与候选类别表、跨存储前后同步表、审查发现与剩余风险。
