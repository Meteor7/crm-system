# CRM 浏览器关闭后会话失效设计

> 日期：2026-08-05  
> 状态：用户已批准方案 1  
> 范围：仅修改本地 Frappe 登录会话 Cookie 行为，不更新其他 Stage。

## 1. 目标

当前 Frappe 把 `sid` 写成带 `Max-Age` 的持久化 Cookie，系统设置中的服务端会话有效期为 `170:00`。目标是把 `sid` 改成浏览器会话 Cookie：关闭整个浏览器进程后，浏览器不再保留该 Cookie；同一浏览器会话内刷新页面仍保持登录。

## 2. 已批准方案

在 `rayher_crm` 注册 `after_request` Hook。Hook 只检查 Frappe 本次响应即将写出的 Cookie；如果存在 `sid`，则清空其 `max_age` 与 `expires`。Frappe 随后沿用框架自身的 `CookieManager.flush_cookies` 写回响应，因此继续保留 `HttpOnly`、`SameSite=Lax`，并在 HTTPS 下保留 `Secure`。

不修改 Frappe 或 ERPNext 框架源码，不在 Nginx 层改写响应，也不缩短服务端会话有效期。

## 3. 数据流

1. 用户向 Frappe 标准登录端点提交账号密码。
2. Frappe 完成认证、创建服务端 Session，并准备带 `sid` 的响应 Cookie。
3. `rayher_crm` 的 `after_request` Hook 在 Cookie flush 之前运行。
4. Hook 仅把 `sid` 的持久化属性设为空，不读取、记录或返回 Cookie 值。
5. Frappe 写回不带 `Max-Age`/`Expires` 的会话 Cookie。
6. 浏览器关闭整个进程后丢弃会话 Cookie；服务端旧 Session 继续按 Frappe 原有期限自然清理。

## 4. 安全边界

- Hook 不打印 `sid`，不写审计日志，不接触密码、Token 或其他 Cookie 值。
- 只处理键名严格等于 `sid` 的 Cookie；其他 Frappe Cookie 保持原状。
- 正常退出登录继续调用 Frappe 标准 logout，立即删除服务端 Session 并清除 Cookie。
- 服务端 Session 的过期策略保持不变，避免正常使用期间意外掉线。
- 浏览器的“恢复上次会话”功能或后台常驻进程可能延续浏览器会话，这是浏览器行为边界；系统不使用不可靠的 `beforeunload` 网络请求强制退出。

## 5. 错误处理

- 未创建 Cookie manager、响应中没有 `sid` 或 `sid` 结构不是预期字典时，Hook 安全返回，不影响请求结果。
- Hook 不抛出业务异常，不改变登录响应正文和 HTTP 状态。

## 6. 测试与验收

- 单元测试先证明当前缺少 Hook，再验证：存在 `sid` 时清空 `max_age`/`expires`；不存在 `sid` 时无副作用；其他 Cookie 不变。
- App package contract 验证 `hooks.py` 注册了 `after_request`。
- 本地 Docker 部署后，使用临时测试用户或受控测试路径检查登录响应头：`sid` 保留 `HttpOnly` 与 `SameSite=Lax`，不含 `Max-Age` 和 `Expires`；验证过程中不输出 Cookie 值。
- 验证同一浏览器会话内刷新仍能访问认证接口，标准 logout 后原会话失效。
- 执行后端全量测试、前端全量测试和 Frappe 生产构建；测试结束后恢复 `allow_tests=false`。

## 7. 非目标

- 不实现页面每次刷新都重新登录。
- 不改变密码策略、角色权限、账号数据或 B1 owner 契约。
- 不部署 Ubuntu Staging。
- 不更新其他 Stage，不提交、重置、暂存或清理 Git 工作区。
