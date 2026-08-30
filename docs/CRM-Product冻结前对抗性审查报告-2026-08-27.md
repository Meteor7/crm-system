# CRM Product 冻结前对抗性审查报告

日期：2026-08-27  
审查对象：当前本地工作区及 `http://203.0.113.10:2224/` 本地 Docker 版本  
审查结论：**部分通过，不建议直接冻结或部署 Product**

## 1. 审查范围

本轮覆盖以下方面：

1. Git 工作区、发布包与透明加密风险；
2. TypeScript 类型检查、全量 Vitest、Frappe 前端构建和 Python 编译；
3. 本地 Docker 容器健康、HTTP 入口、静态资源与近期错误日志；
4. Installed Tool 文件上传功能下线完整性；
5. Mock/Frappe runtime 边界；
6. 凭据、测试文档、会话失效和 Product 发布控制；
7. 后端 Frappe 测试及真实多角色浏览器证据完整性。

## 2. 执行结果摘要

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| `vue-tsc --noEmit` | 通过 | 退出码 0 |
| 全量 Vitest | 通过 | 106 个测试文件，690 个测试通过 |
| Python `compileall` | 通过 | `backend/apps/rayher_crm/rayher_crm` 无语法错误 |
| Frappe 前端构建 | 通过 | Vite 生成 `index-Bybx_884.js` 等产物 |
| 本地 Docker 核心容器 | 通过 | backend/frontend/db/Redis/ClamAV healthy |
| 本地 HTTP | 通过 | `/`、`/api/method/ping`、CRM `index.html` 均为 200 |
| 最近 10 分钟 500/Traceback | 通过 | backend/frontend 日志未发现新增异常 |
| Installed Tool 上传入口 | 通过 | 前端入口、adapter、类型、后端白名单和服务函数均已移除 |
| Installed Tool 备注字段 | 通过 | 本地构建显示“备注”，保留多行文字记录 |
| 两篇 Document Center 测试文档 | 通过 | 精确删除 `DOC-UPL-00460`、`DOC-UPL-00406` |
| Frappe runtime | 通过 | 构建产物不包含 `createMockApi`，真实 API 请求进入 Frappe |
| 后端 Frappe 全量测试 | 通过 | 隔离 `rayher-crm.test`：253 tests，0 error，退出码 0 |
| 多角色真实浏览器回归 | 未通过门槛 | 本轮未重新执行 Sales/Manager/Engineer 完整流程 |

注：第 3 节记录的是首次审查时的发现；当前状态和关闭依据以第 7 节“本轮 P1 修复与对抗性复审”为准。

## 3. 对抗性发现

### P0-1（历史发现，已处理）：仓库中存在未跟踪的账号密码 CSV

`git status` 显示：

```text
?? docs/CRM-账号密码-2026-08-27.csv
```

首次审查时该文件正被其他进程占用，本轮复查已确认其不在工作区。仅凭文件名已足以判定其不应进入源码仓库或发布包。

影响：

- 可能导致账号密码进入 Git 历史、PR、构建上下文或 Product 镜像；
- 一旦提交，即使后续删除也无法从历史中自然消失；
- 与“不在仓库保存密码、Token、Cookie”发布要求冲突。

冻结门槛：仍需在正式提交前确认 Git 历史、暂存区和应用 ZIP 不包含该文件及其他凭据。

### P1-1（历史发现，部分已处理）：工作区未形成可复现发布基线

首次审查时存在多项已修改和未跟踪文件，包括报告、CSV、临时文件 `({text`、`x.p`。部分文件此前出现过透明加密或二进制变化风险。

影响：

- 无法从一个明确 commit 复现当前本地运行版本；
- 构建包可能混入临时文件、过期报告或敏感数据；
- 本地验收结果不能直接映射到 Product 发布 commit。

冻结门槛：逐项确认工作区文件归属，清理临时产物，检查文本文件为明文；只提交发布相关内容，从最终 commit 重新生成 ZIP 并记录 SHA-256。

### P1-2（历史发现，已处理）：应用容器运行不同镜像版本

首次审查时 queue-short、queue-long、scheduler 仍显示旧镜像摘要；本轮已统一重建。

影响：

- Web 请求与异步任务可能加载不同版本的 Python 代码；
- 定时任务、通知和后台作业可能产生不可复现行为；
- 当前 HTTP 健康不能证明异步路径与发布版本一致。

冻结门槛：从同一应用包重建并重启 backend、frontend、websocket、scheduler、queue-short、queue-long；记录六类容器的镜像 ID 并确认一致。

### P1-3（历史发现，已处理）：后端 43 个 Frappe 测试文件未完成运行时执行

首次审查仅完成 Python 编译，未在专用 `.test` 站点执行：

```text
bench --site <dedicated.test> run-tests --app rayher_crm
```

禁止在本地业务库或 staging 业务库直接运行破坏性测试。

影响：服务层权限、事务、数据库约束、补丁和文件安全逻辑仍缺少本轮版本的运行时证据。

冻结门槛：在一次性 Frappe `.test` 站点运行全部测试，记录测试数量、失败用例、退出码、Frappe/ERPNext/app 版本和容器镜像 ID。

### P2：删除 Document Center 测试文档后的文件存储审计证据不足

两条 Controlled Document 记录已精确删除并清理缓存；本轮没有形成对应 Frappe `File` 物理文件和数据库行均已删除的可审计输出。

建议：发布前检查 `File.attached_to_doctype/attached_to_name`、private files 目录和孤立文件扫描结果，避免只删除文档主记录。

## 4. 已关闭问题

### Installed Tool 文件上传功能

已确认以下内容全部移除：

- 生命周期弹窗中的文件选择入口；
- Installed Tool 文件列表和下载区域；
- 前端 contracts、Frappe adapter、Mock adapter 和文件 DTO；
- 后端 list/upload/download 白名单接口；
- 后端 Installed Tool 文件服务函数；
- 无效附件样式。

生命周期表单保留“备注”多行文本，仍通过原有 `evidence` 数组保存文字内容，不包含文件上传。

## 5. Product 冻结前必须完成

1. 正式提交前检查 Git 历史、暂存区和 ZIP 不包含凭据；
2. 确认所有发布文本无 `%TSD-Header-###%` 污染，并建立正式 release commit 和 SHA-256；
3. 在 staging 重新完成 Sales/Manager/Engineer 真实会话回归；
4. 验证失效用户会话返回标准未认证结果；
5. 核验已删除测试文档无孤立 File；
6. Product 发布前禁用/删除测试账号并精确清理测试数据。

## 6. 最终结论

当前版本的前端单元测试、类型检查、Python 编译、Frappe 构建和本地 HTTP 健康均通过，Installed Tool 上传功能已完整下线。

## 7. 本轮 P1 修复与对抗性复审（2026-08-27）

| P1 项 | 本轮动作与证据 | 结果 |
| --- | --- | --- |
| 后端全量测试 | 修复 `test_evaluation_api.py` 中已过期的 `contactId` 夹具引用；在隔离 `rayher-crm.test` 站点执行 `bench --site rayher-crm.test run-tests --app rayher_crm` | **已关闭**：253 tests，0 error，退出码 0 |
| 应用容器版本混用 | 重新构建并重启本地 backend、frontend、websocket、queue-short、queue-long、scheduler | **已关闭**：六类应用容器均为同一镜像 digest `sha256:0081bfc5...`，全部 healthy/运行中 |
| 发布包混入测试代码 | 测试结束后重新运行 `prepare-app-build-context.ps1`（不带 `-IncludeTests`） | **已关闭**：生产包 329 entries，未包含 tests 目录 |
| 工作区凭据/临时文件 | 复查账号密码 CSV、`({text`、`x.p` | **已关闭（当前工作区）**：均不存在；仍需在提交前复查 Git 历史 |
|  |

本轮复审新增证据：

- `npm.cmd run typecheck`：退出码 0；
- `npm.cmd run test -- --run`：106 个测试文件、690 个测试通过；
- `python -m compileall -q backend/apps/rayher_crm/rayher_crm`：通过；
- `http://203.0.113.10:2224/api/method/ping` 与根入口：HTTP 200；
- 本地应用容器日志最近 15 分钟未形成可复现的 500/Traceback 证据。

### 复审结论

上一轮的后端全量测试、容器版本混用和测试包污染 P1 已关闭。失效用户旧会话和真实三角色浏览器回归仍缺少运行时证据，因此 Product 冻结结论仍为：

> **部分通过。可继续本地验收；完成失效会话专项验证和 Sales/Manager/Engineer 真实 staging 回归后，才能申请 Product 冻结。**
