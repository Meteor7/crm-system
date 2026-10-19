# Document Center 模块高保真实施规格

## 目标

将已经确认的三张高保真视觉稿落到现有 Vue CRM Demo 的 `/document-center` 页面。保留现有 AppShell、路由、Mock API 和身份切换，只重做 Document Center 主内容区。

## 范围

- Direct Access：普通文档可以查看模拟 PDF、版本信息、下载审计和受控下载说明。
- Access Required：Restricted 文档正文完全锁定；用户填写用途并提交访问申请，状态变为 `Manager Review`。
- Admin Review：CRM Administrator 可以查看申请队列并执行批准、拒绝或补充信息。
- Management Viewer：可以查看审批、版本历史和下载审计，但审批与下载相关操作必须禁用。
- 不新增依赖，不修改 Frappe 接口，不扩展全局权限能力枚举。

## 页面结构

### 普通文档工作台

主内容使用三栏结构：

1. 文档库：只有全部文档、技术文档、商务文档，并显示访问级别统计。
2. 文档列表：支持搜索、分类和选中状态；展示标题、Document ID、版本、Owner、更新时间和密级。
3. 详情区：Direct 文档显示模拟 PDF；Restricted 文档显示不可穿透的锁定画布。版本历史与下载审计位于详情区标签，不作为左侧入口。

### 管理审批工作台

CRM Administrator 和 Management Viewer 进入审批视图：

1. 左栏为审批队列过滤和角色权限说明。
2. 中栏为访问申请列表。
3. 右栏为申请人、申请理由、审批链、授权期限、访问方式、版本历史和下载审计。

CRM Administrator 的审批动作在 Demo 会话内更新本地状态。Management Viewer 只显示只读说明，所有变更按钮禁用。

## 数据与状态

- 文档目录继续来自 `CrmApi.listControlledDocuments()`。
- 申请提交继续调用 `CrmApi.requestControlledDocumentAccess(versionId, reason)`。
- 当前角色来自 `CrmApi.getBootstrap()`，不复制或绕过现有权限矩阵。
- 审批队列为页面内的演示数据，不宣称已接入正式后端审批流。
- 页面重载或 Demo 身份切换后，组件按当前 Mock 会话重新初始化。

## 关键交互

- 搜索匹配标题、Document ID、产品或 Owner。
- 分类只允许 All、Technical、Commercial。
- Direct 文档的“受控下载”只显示 Demo 成功提示，不生成真实文件。
- Restricted 文档必须填写申请理由；未填写时显示内联错误。
- 申请成功后保留锁定预览，显示 `Manager Review` 与审批链。
- 管理员批准、拒绝或要求补充信息时，只更新当前 Demo 申请状态并显示操作反馈。

## 视觉规则

- 延续深海军蓝、暖白、PLANCK 橙和青绿色状态色。
- 三栏使用清晰分隔线和紧凑档案式信息密度，不使用渐变、玻璃拟态或营销型大标题。
- Restricted 预览不得显示价格、表格或任何正文内容。
- 1440px 桌面优先；在 1100px 以下允许三栏变为可横向适配的两栏或单栏，不破坏现有 AppShell。
- 所有可操作控件提供 hover、focus-visible、disabled 状态。

## 验收标准

1. Sales User 可以看到三栏文档工作台和 Direct Access 预览。
2. 选择 `DOC-PRICE-26` 后正文锁定，可填写原因并提交申请。
3. 提交后页面显示 `Manager Review`，仍不能预览或下载正文。
4. CRM Administrator 可以看到审批队列、审批链、版本历史和下载审计，并执行三种审批动作。
5. Management Viewer 可以查看相同证据，但不能执行审批或下载。
6. 左侧库不出现“最近查看”或“版本历史”。
7. 聚焦测试、类型检查和生产构建通过。

