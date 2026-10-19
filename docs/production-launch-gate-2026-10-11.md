# 生产首日放行与附件暂停规则

## 最新放行结论

2026-10-10 23:55（America/Los_Angeles，UTC-7）完成 P1 修复后的生产复测，可以按本文限定范围放行。实际运行代码对应修复提交 `5bef99a8228fec5b4132ae033f758bc5ab6f82b8`，其 [完整 CI](https://github.com/kizzhang/PlanckSemicon_CRM/actions/runs/38118241344) 在部署前通过：前端 1774 项、后端 1426 项测试和 6 组 HTTP 验收通过，frontend/package/backend/release-gate 全部成功。

生产四个 Python 服务已切到 `rayher-crm-stage1:v15-production-3088723-launch-guard-p1-20261011`，镜像 `sha256:a59759db3d38dac03a031d952a91fd1075a5b1fbccf4bcd25246f5c060b9df9a`，业务基线仍为 3088723，无数据库迁移。实际部署已执行清缓存并验证有效 `before_write_file` 钩子。生产公开与私有 save_file 均在落盘前拒绝，文件目录哈希和 File 行快照一致，无文件或记录残留。

三角色真实 HTTPS 冒烟扩展为 63 项并全部通过，运行 `LAUNCH-SMOKE-202610110655532317`；临时账号剩余 0，9 类业务表快照一致，附件目录哈希一致，Cookie Secure/HttpOnly 生效，存量 PDF 授权下载成功，未新增 Error Log。资料位于生产 `launch-guard-p1-20261011` 目录；备份批次 `20261011_145508`。本次仍是限定范围接口冒烟，不是完整浏览器交互 UAT；所有新增文件及依赖流程继续暂停，包括需要生成新 PDF 的报价发布。

## 每次正向部署必须清理并验证钩子缓存

Frappe 15 在生产模式使用 Redis 的 `app_hooks` 缓存，仅替换镜像不足以启用新增钩子。所有 Python 服务切换到含修复的镜像后，必须先执行：

```sh
docker exec rayher-crm-stage1-production-backend-1 bench --site 203.0.113.32 clear-cache
docker exec rayher-crm-stage1-production-backend-1 bench --site 203.0.113.32 execute frappe.get_hooks --kwargs '{"hook":"before_write_file"}'
```

第二条命令必须返回包含 `rayher_crm.security.attachment_gate.reject_file_write` 的列表；同时确认站点 `crm_attachment_uploads_paused=true`，有效 `before_request` 包含 `reject_upload_request`。随后在正常生产模式下验证公开/私有 save_file 拒绝且无文件或记录残留，再跑角色冒烟，全部满足才恢复有限放行。验证有效钩子时不得用 developer_mode 或进程内替换钩子代替生产缓存路径。若更换 backend 容器地址，刷新 frontend 的上游解析并检查 HTTPS 健康和 Cookie。部署步骤缺失、钩子未生效或复测失败均停止放行。

## 原 P1 复核与修正记录

PR #247 的 review 确认：Frappe 15 `file_manager.save_file` 会先写文件，再插入 File；仅在 `before_insert` 拒绝会留下无记录文件。下文 05:59 UTC 的 57 项冒烟没有覆盖这条路径，不能证明所有新增附件均被封闭，原放行结论曾因此暂停，现由上述修复后复测结果取代。

修复增加 `before_write_file` 钩子，在 legacy writer 运行前拒绝；保留 `before_insert`，因为内容去重命中会跳过写文件钩子。新增公开、私有无文件/记录残留测试，以及暂停关闭后的真实写入正向对照。上述 CI、生产更新、缓存清理及复测已完成；以下内容保留为初次部署历史，最终部署结果以本页开头的最新记录为准。

## 放行范围

2026-10-11 05:59 UTC 完成生产 HTTPS 冒烟，建议按限定范围放行。此时间为 UTC，生产业务时区为 Asia/Shanghai。

- 可用：销售客户、站点、联系人、商机和跟进行动；Demo 草稿、销售提交、工程师审核、经理审批；Evaluation 推进至 Testing；经理看板；已有附件的授权下载。
- 暂停：所有新增附件，包括 CRM multipart 上传、原生 Desk 上传、File REST / client.insert、后台 File 创建。文件导入、RFQ 新建所需上传、报告上传及依赖新报告的后续流程也在暂停范围内。
- 本次验证为真实 HTTPS 账号登录、接口写入和页面响应冒烟，不是完整浏览器交互 UAT 或全量回归。

## 实际部署

保持生产业务基线 `3088723`。未部署全部 main 或 PR #245。

- 原镜像：`sha256:10e27daa025745c4142a0b6d6df5836833c552a0b52845ba3d46bf3130419fc8`。
- 当前 Python 服务镜像：`rayher-crm-stage1:v15-production-3088723-launch-guard-20261011`。
- 当前镜像 ID：`sha256:33b5e2a7c3c11d2f1141bbd37b400694df43914319321859f1a7112c15a16de7`。
- 修改范围：新增 `security/attachment_gate.py`、注册 `before_request`、在 `ManagedFile.before_insert` 核心文件操作前阻止新建文件。
- backend 环境：`FORWARDED_ALLOW_IPS="*"`。backend 无主机发布端口；仅受控 frontend 转发请求协议。
- 站点配置：`crm_attachment_uploads_paused: true`。默认未配置时保持原行为；生产必须保留此开关和对应代码。
- backend、queue-short、queue-long、scheduler 使用限制镜像；frontend/websocket 保持原版。
- 不涉及数据库迁移。变更前已执行数据库及文件备份。

主机操作目录：`/home/plancksemicon/apps/rayher-crm-stage1-production/launch-guard-20261011`。

Compose 使用原版 `releases/3088723-main-20261007/backend/compose.yaml` 加上述目录的 `compose.launch-guard.yaml`，继续使用 `backend/.env.production`。目录内保留文件哈希、构建上下文、部署结果、备份日志和冒烟结果。

**后续部署不能只换回原 Compose 或只升级部分 Python 容器。** 附件暂停未解除前，新镜像必须包含本规则，并保留站点开关和 Cookie 环境配置。#245 也修改 `before_request` 时，应同时保留两个 hook，不得覆盖附件暂停 hook。

## 验证结果

- 镜像预检：真实 Frappe 15 / MariaDB 环境下执行 4 个针对性测试，数据库事务只读，站点卷只读；全部通过。
- 生产冒烟：57 项通过；三个独立临时角色均实际登录，Cookie `Secure` / `HttpOnly` 生效。
- 销售创建及更新客户、站点、联系人、商机、行动；完成行动；创建并提交 Demo。
- 工程师完成技术审核；经理批准生成 Evaluation；工程师推进至 Testing。
- 过期版本写入 409、越权审批 403、重复批准 409、销售访问经理看板 403。
- CRM 上传、三角色原生上传、File JSON 创建及通用 client.insert 绕过均被拒绝。
- 重新登录仍能读取审批结果；拒绝上传未改变 Evaluation 状态。
- 现有两份 PDF 通过授权下载 API 返回完整字节；直接私有 URL 按现有设计拒绝，Guest 同样被拒绝。
- 临时账号、自动生成的联系人和测试业务实体已清理。9 类业务表的记录数及 `name + modified` 快照与冒烟前一致；原有 57 客户、21 联系人、64 站点、23 商机、3 Demo、1 Evaluation、4 File 行保留。
- 生产服务健康，短/长队列为空。保留必要运行与访问审计，不清除生产审计记录。

最终成功运行：`LAUNCH-SMOKE-20261011055913d0b8`。前两次脚本验收问题已修正：自动 User Contact 需一并清理；托管附件应走授权 API，原始 URL 的 403 是设计行为。随后完整重跑通过。

## 上线后修复顺序

以下是建议执行顺序，未承诺其他人员工期；现有 issue 保持开放。

| 顺序 | 工作 | 跟踪 | 验收与开放条件 |
| --- | --- | --- | --- |
| 1 | 扫描超限拒绝、整次上传截止时间、Office 部件限制 | #243、#244、PR #245 | 最新提交完整 CI 和 review 通过；部署后真实 clamd 超限拒绝；超时无记录/文件残留；正常大型 Office 成功。先修复，后恢复附件功能。 |
| 2 | 普通私有客户附件权限 | #220 | 客户移交后原负责人不能从原生 API、列表及私有 URL 读到文件；确认后才考虑开放 Desk 附件。 |
| 3 | RFQ 搜索与分页截断 | #58 | 1501 条及以上数据验证总数、搜索、跨页完整性；批量导入或接近 1000 条前完成。当前生产 RFQ 为 0。 |
| 4 | PDF/CSV 原件误标 PPTX、审批轨迹文案 | 新增上线后清单、#186 | 按实际文件格式展示按钮/提示；轨迹对应真实审批状态。 |

重新开放附件前，必须明确满足上述对应项，并在生产重新跑上传、审批、下载和权限冒烟。不得仅因 PR 合并就关闭暂停开关。

## 回退

变更前备份位置及名称见主机目录的 `pre-change-backup.log`，开关原值见 `site-flag-before.json`。原镜像与原 release 仍保留。

如需回退限制镜像，先暂停业务使用，再按原 Compose 重建四个 Python 服务并恢复开关原值、清缓存、刷新 frontend 上游，重新验收。回退原镜像会同时失去附件限制，不得沿用本次有限范围放行结论。禁止删除数据库或文件卷。
