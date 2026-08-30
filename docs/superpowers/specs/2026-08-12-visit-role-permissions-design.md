# 拜访管理角色权限设计

## 目标

只收紧真实 Frappe 链路中的拜访管理权限，不调整其他模块，也不修改仅供单元测试使用的 Mock 适配器。

## 权限规则

- Manager：可以查看、创建、编辑、审核和删除全部拜访。
- Sales：可以查看、创建和编辑自己的拜访；可见性仅由 `CRM Visit.visit_owner = 当前用户` 决定，不再继承客户负责人的可见范围。
- Engineer：不具备任何拜访管理 capability；不能从导航进入拜访管理，直接访问页面会被现有路由权限逻辑重定向，直接调用拜访接口会被后端拒绝。
- Guest：保持拒绝访问。

## 实现边界

后端是权限真源：

1. 从 Engineer 的角色 capability 中移除 `visit:view`。
2. 将 `CRM Visit` 的 Engineer DocPerm 权限全部设为关闭，确保已安装环境在执行权限安装逻辑后也会撤销旧权限。
3. `CRM Visit` 行级条件对 Sales 只匹配 `visit_owner`，对 Engineer 返回拒绝条件，对 Manager保持全量。

前端只同步真实权限契约：

1. 从 Engineer 的前端 capability 集合移除 `visit:view`。
2. 复用现有导航过滤和路由重定向，不新增路由框架或页面级特殊判断。

## 测试

- 后端角色测试验证 Engineer 不再拥有 `visit:view`。
- DocPerm/查询条件测试验证 Engineer 无 CRM Visit 读取权限。
- 回归测试创建“同一客户、不同 `visit_owner`”的两条拜访，验证 Sales 只能看到自己的记录且不能读取或更新另一位 Sales 的记录。
- 前端权限测试验证 Engineer 不包含 `visit:view`，现有导航权限测试继续通过。
- 运行拜访、权限及相关前端测试，确认其他模块行为不变。

## 非目标

- 不调整 Demo、Demo Test、Installed Tools 或其他 Engineer 权限。
- 不修改 Mock 适配器及 Mock 数据。
- 不引入新的权限配置页面、数据库表或依赖。
