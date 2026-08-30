# CRM Frappe 人员目录与服务器通知设计

> 日期：2026-08-05  
> 状态：用户已批准  
> 覆盖 Gate：A3、B14  
> 边界：只修真实 Frappe runtime；Mock 演示行为保持不变。

## 目标

Frappe 构建不再携带或信任静态 `PERSONNEL` / Demo identities；owner/assignee 的显示与选择来自当前 Frappe 数据库。真实模式通知只来自 `CRM Notification Event`，并把已读状态写回服务器。

## 人员目录

`get_bootstrap` 增加 `personnel` 数组。后端只返回 enabled System User，排除 Guest、Administrator，并要求恰好拥有一个 CRM Manager/Sales/Engineer 角色。多角色、无角色、disabled 与 Website User 均失败关闭，不进入目录。

每项只含稳定 User ID、显示名、缩写、公开 CRM role、team 与可分配标志。不返回认证或个人敏感字段。目录仅供显示/选择，后端权限继续由 session、role、capability 与 SQL scope 决定。

Frappe 构建通过精确 Vite alias 把 `@/demo/personnel` 指向 reactive 空目录实现；Mock 构建保持现有静态实现。bootstrap 成功后原地替换 reactive array，因此现有 47 个调用方不需要逐文件改写。空目录不回退到 Alex 或任何静态默认值。

`src/demo/identities.ts` 同样经 alias 读取目录，因此 Frappe bundle 中 `DEMO_IDENTITIES` 自然为空；AppShell 仍由 `usingMock` 控制身份切换 UI。

## 服务器通知

Notification Store 在 Mock 模式保留 Requirement seed；Frappe 模式初始为空。`loadBootstrap` 在 server delivery 下读取第一页通知并替换 Store。

打开一条通知时，真实模式先调用 `markNotificationRead`，成功后才更新本地；全部已读同理。失败时保持未读并显示错误，不做不可回滚的乐观修改。Mock 模式保持同步本地 markRead/markAllRead。

## 失败策略

- bootstrap 人员目录失败：整个 bootstrap 失败，不展示伪目录。
- 通知列表失败：身份 bootstrap 可继续，但通知保持空并记录可见错误；不回退静态 seed。
- 通知已读写回失败：保持原未读状态。
- 未解析历史 User ID：直接显示稳定 ID，不猜测姓名。

## 安全与非目标

- 不创建或修改 Frappe Users，不接 HRMS，不同步 ERP 人员。
- 不把人员目录作为授权证据。
- 不复制本地 Mock 数据到数据库。
- 不改变旧 Docker 栈或 volumes。
- 本批次不顺带修 A4/A5/B8/B9/B10。

## 验收

1. 后端测试证明目录只含 enabled、exactly-one-CRM-role System Users。
2. Frappe personnel runtime 初始为空，bootstrap 后按角色查询和显示。
3. server delivery 初始化只显示服务器通知；mark read/mark all read 调服务器并失败关闭。
4. Mock 现有人员、身份切换与 Requirement 通知回归不变。
5. Frappe production bundle 不含静态测试邮箱、Alex/Bella 名字或 Requirement seed ID。
6. 前端聚焦测试、全量测试、typecheck、Mock build、Frappe build与后端测试通过。
