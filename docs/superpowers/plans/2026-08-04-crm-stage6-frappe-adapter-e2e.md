# CRM Stage 6 Frappe Adapter 与端到端验收执行计划

> 状态：执行中。默认 `.env.local` 保持 `VITE_API_ADAPTER=mock`；只有专用 Frappe 构建和验收使用真实 adapter。

## 范围与成功标准

- [x] Stage 6A：用前端单元测试冻结 Frappe 双层 envelope、GET/POST 编码、同源 session、CSRF、业务/HTTP/网络/超时错误、multipart、原始二进制下载及全部 `CrmApi` 端点映射。
- [x] Stage 6B：实现 `createFrappeApi()`，逐项映射现有 `rayher_crm.api.v1` 白名单端点，不增加契约外能力。
- [x] Stage 6C：构建 `VITE_API_ADAPTER=frappe` 的静态资源，在新 Docker 栈内提供独立 CRM 路由，并以真实 Frappe 会话完成浏览器 E2E。
- [x] Stage 6D：运行前端全量测试、类型检查、默认 Mock build、Frappe build、后端全量 App 测试、migrate/compose/HTTP smoke；确认旧 Docker 栈和 volumes 未改动。
- [x] Ubuntu staging：产出可复现的部署/回滚前置清单；仅在取得目标服务器连接参数与授权后执行实际上线。

## 契约冻结

1. 请求地址固定为 `/api/method/rayher_crm.api.v1.<module>.<method>`，不允许页面直接调用 Frappe Resource API。
2. GET 仅传定义过的 query 字段；POST 使用 `application/x-www-form-urlencoded;charset=UTF-8`，复杂对象 JSON 序列化到 `input`、`command` 或 `selection`。
3. 所有请求使用 `credentials: same-origin`；非 GET 在存在 Frappe CSRF token 时发送 `X-Frappe-CSRF-Token`。
4. JSON 成功响应必须同时解开 Frappe `{ message: ... }` 与 CRM `{ data, meta, warnings }`；分页结构不得重塑，Notification 是唯一已知的扁平 data 特例，需要包装为 `{ items }`。
5. CRM 业务错误优先读取内层 `error`；401/403 归一为 `PERMISSION_DENIED`，409 归一为 `VERSION_CONFLICT`，422 归一为 `VALIDATION_ERROR`，网络与超时分别归一为 `NETWORK_ERROR`、`UPSTREAM_TIMEOUT`。
6. multipart 不手工设置 `Content-Type`；Contact File 使用多值 `files`，Demo Artifact 使用单值 `file` 与独立元数据字段。
7. 下载不走 JSON envelope；文件名优先解析 RFC 5987 `filename*`，其次 `filename`，最后使用安全默认名。
8. `releaseDemoTestReport` 的当前后端只消费 `id` 并从已配置 artifact 生成发布记录；前端契约中的 `file` 参数不得错误上传到该端点。

## 验证顺序

1. 新增失败测试并确认现有占位实现不能通过。
2. 小范围实现 transport 与方法映射，运行聚焦测试、类型检查。
3. 构建并打包 Frappe 资源，更新新栈应用镜像，仅重建无状态应用服务。
4. 创建/验证 CRM SPA 路由与真实 session E2E，精确清理验收产生的数据。
5. 执行全量回归和 Docker/数据边界检查，更新审计日志与桌面副本。

## 停止条件

- 不停止/删除任何 Docker volume，不操作旧 `rayher-crm` 容器。
- 不 commit/reset/stash/clean/checkout。
- 若实际 staging 缺少服务器地址、SSH 身份或部署授权，只将“实际上线”登记为外部阻塞；本地所有可完成 Gate 继续执行。
- 不在日志、命令输出或交接文件记录密码、Cookie、CSRF token、API key 或其他 secret。
