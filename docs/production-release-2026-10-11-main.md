# 生产发布 e37f782c-main-20261011（main 全量上线）

## 结果

2026-10-11 07:22:25–07:23:24 UTC（15:22–15:23 Asia/Shanghai），生产从 `3088723` + 首日门控热补丁升级到 main `e37f782c`（含 PR #247 的附件门控）。写入冻结窗口 07:22:27–07:23:05 UTC，约 40 秒。

- 范围：main 上 3088723 之后的全部提交：#247 #240 #242 #241 #236 #224 #239 #223 #218 #237 #217 #233 #231 #230 #5 #215。
- 附件暂停保持开启：`crm_attachment_uploads_paused: true` 未动；`before_request`、`before_write_file` 与 `File.before_insert` 三处门控在新镜像内，升级脚本逐项验证生效。恢复附件仍按 #246 的顺序和条件。
- PR #245（上传截止时间、ClamAV 超限拒绝）不在本次发布内；`clamav` 服务配置未变。
- 升级后 Error Log 为 0，短/长队列为空，57 项三角色 HTTPS 冒烟通过，临时数据清理后 9 类业务表快照一致。

## 起始状态

升级前生产并非单一镜像：另一会话于 06:55 UTC 已把 `launch-guard-p1-20261011` 热补丁镜像（`sha256:a59759db…`）切到 backend、scheduler、queue-short、queue-long（由 `releases/3088723-main-20261007/backend/compose.yaml` 加 `launch-guard-p1-20261011/compose.launch-guard.yaml` 创建）；frontend 与 websocket 仍运行 3088723 镜像（`sha256:10e27daa…`，由单一 compose 文件创建）。升级脚本按这一形态改编，回退与恢复均重建该形态。

升级后六个应用服务全部运行 `rayher-crm-stage1:v15-production-e37f782c-main-20261011`（`sha256:ab3e345c…`），由 `releases/e37f782c-main-20261011/backend/compose.yaml` 单独创建；`FORWARDED_ALLOW_IPS="*"` 已在该 compose 文件内，`compose.launch-guard.yaml` 不再使用。

## 发布包

主机目录 `/home/plancksemicon/apps/rayher-crm-stage1-production/releases/e37f782c-main-20261011/`：

| 文件 | 来源 |
| --- | --- |
| `backend/build/rayher_crm.zip` | Release Gate run 38121037483（main `e37f782c`，package job）的 `verified-archives` 产物，sha256 `b582c41d…`；与 PR #247 的 run 38118241344 / 38119770535 产物字节一致 |
| `backend/compose.yaml` | 提交 `e37f782c` 的文件 |
| `overlay.Dockerfile` | 与 3088723 发布字节一致 |
| `upgrade.sh`、`restore.sh`、`lib.sh` | 自 3088723 发布改编，见下 |
| `targets/production.env`、`targets/rehearsal.env` | 新增 `PREVIOUS_COMPOSE_OVERLAY`、`PREVIOUS_GUARD_IMAGE` |

脚本改编点：

- `verify-running-stack`：门控服务须运行 `PREVIOUS_GUARD_IMAGE` 且由两个 compose 文件创建；frontend/websocket 须运行 `CRM_IMAGE` 所指镜像，由单一文件或（回滚/恢复之后）两个文件创建。两个镜像 ID 均写入 `state.env`，并各以一个 holder 容器钉住。
- `old_dc` 带两个 compose 文件：迁移前失败的回滚和 `restore.sh` 都按原形态重建门控栈，暂停开关随 site_config 一并恢复。
- `verify-release`：归档必须含 `security/attachment_gate.py`、两个钩子注册、`overrides/file.py` 的插入前拒绝、`patches.txt` 中本次 4 个补丁。
- `verify-migration`：4 个补丁（及前一发布 10 个）在 Patch Log；新列（Opportunity/Booking 归档列、`red_flag_records`、历史表负责人身份列、区域树 `is_group`/`enabled`、Cockpit Target 范围列、报价计划发送日）、5 张新表、新索引；每个商机已有红旗记录；负责人变更身份已解析；区域树仍为默认 8 节点且仅 World/Asia/China 为分组、无改名；无记录被标归档。`CRM Cockpit Settings` 为单例，按 meta 校验字段。
- `acceptance-internal`：`crm_attachment_uploads_paused` 须与冻结快照一致且为真。
- API 验收：`frappe.get_hooks` 中两处门控钩子存在、开关为真、`reject_new_file()` 对 Administrator 抛 PermissionError（回应 #247 review 关于钩子缓存的意见：新 backend 启动后执行 `clear-cache`，再核对生效钩子）。
- `acceptance-http`：guest multipart 上传须 403 且 `_server_messages` 含门控文案。

CI 证据：`20aba9d7`（与 `e37f782c` 树一致）的 Release Gate 全绿（backend 14m26s）；`e37f782c` 自身 run 38121037483 的 package job 产出本次归档，其 backend job 在发布时仍在 staging runner 排队。

## 演练

staging 的 `rayher-crm-rehearsal` 栈（10-07 生产备份升级到 3088723 的副本）先复刻为生产门控形态：以 rehearsal 3088723 镜像为基构建门控镜像（hooks.py、attachment_gate.py、overrides/file.py 与生产热补丁文件一致）、两个 compose 文件、开关为真、guest 上传 403。随后用 release `5bef99a8-main-20261011`（归档与 compose 与生产发布字节一致）演练：

1. 第一次升级在 `verify-migration` 失败：脚本把单例 `CRM Cockpit Settings` 当作表。站点按设计 HOLD；用 `restore.sh` 恢复，门控栈、开关与数据均按备份回到原状（验证了回退路径）。
2. 第二次预检失败：恢复后 frontend/websocket 的 compose 标签含两个文件。校验放宽为两种形态均可。
3. 第三次：4 个补丁 12 秒，验证与验收全部通过，升级后 57 项冒烟通过并清理干净。

## 生产验证

| 阶段 | 结果 |
| --- | --- |
| 预检 07:21:57 | 归档校验通过，门控存在；栈形态与镜像 ID 符合；CNY 计划 {0,0,0} |
| 冻结 | 预检到冻结之间无记录变化；队列空 |
| 备份 | `backups/pre-update-e37f782c-main-20261011-20261011-072225/backup/`：数据库 1.1 MiB、私有文件 13.4 MiB、公共文件、site_config，SHA256SUMS |
| 迁移 | 10 秒，4 个补丁；无 traceback |
| verify-migration | stage/region ok；territories 8，groups Asia/China/World；redFlagRecordsMissing 0；ownerIdentitiesUnresolved 0；archived 0；CNY {0,0,0} |
| 数据验收 | 57 客户、21 联系人、64 站点、23 商机、3 Demo、1 Evaluation、5 Visit、4 File 与冻结快照一致；阶段、区域、scheduler、site_config 一致；uploads_paused=True |
| API 验收 | 门控钩子生效并拒绝；bootstrap/cockpit 正常；两名 Sales 看板可读、经理 Review 被拒 |
| HTTP 验收 | ping 200；/crm 301→200；guest 经理 API 401；5 个前端资源 200；guest multipart 403 + 门控文案 |
| 升级后冒烟 | `LAUNCH-SMOKE-20261011072343fcc0`：57 项通过，临时用户/数据清理，快照一致；结果存于运行目录 `post-upgrade-smoke-result.json` |
| 外部核对 | `https://crm.example.invalid/api/method/ping` 200，`sid` Secure/HttpOnly，HSTS；HTTP 308 跳转 HTTPS |

## 回退

恢复到升级前的门控栈（launch-guard-p1 镜像 + 3088723 前端，暂停开关为真），会丢失备份之后写入的数据：

```bash
CONFIRM_RESTORE=e37f782c-main-20261011 /home/plancksemicon/apps/rayher-crm-stage1-production/releases/e37f782c-main-20261011/restore.sh /home/plancksemicon/apps/rayher-crm-stage1-production/releases/e37f782c-main-20261011/targets/production.env /home/plancksemicon/apps/rayher-crm-stage1-production/backups/pre-update-e37f782c-main-20261011-20261011-072225
```

原 3088723 镜像与 launch-guard-p1 镜像由 `rayher-crm-stage1-production-rollback-holder` 与 `-rollback-guard-holder` 容器钉住，不得删除。

## 后续

- `launch-guard-20261011`、`launch-guard-p1-20261011` 目录保留作记录，不再参与部署。
- run 38121037483（main `e37f782c`）的 backend job 首次因 runner 上 CI 产物下载未落盘而失败（"Artifact commit does not match checkout"），非代码问题；同一棵树在 #247 与 #248 的运行中后端测试均通过。已重跑该任务。
- 发布脚本与演练记录在两台主机的 `releases/` 目录及 `upgrade-*.log`、`restore-*.log`。

---

# 第二次发布 f4a4384d-main-20261011（#245：上传截止时间、扫描超限拒绝、大型 Office 附件）与附件开放

## 结果

2026-10-11 08:57:17–08:59:33 UTC（16:57–16:59 Asia/Shanghai），生产从 `e37f782c` 升级到 main `f4a4384d`（合入 PR #245）。写入冻结 08:57:20–08:57:55 UTC，约 35 秒。无新补丁、无 DocType 变更。

- 08:59:55 UTC 关闭 `crm_attachment_uploads_paused`（`set-config False --parse` + `clear-cache`）。附件上传自此开放。
- 升级后 19 项 HTTPS 上传冒烟通过，临时数据清理后快照一致，File 总数回到 4；升级后 Error Log 为 0，队列为空。
- 决策记录：按负责人选择"先上 #245 再开附件"执行。#220（Desk 直接上传的普通私有附件在客户移交后原负责人仍可读）未修，当前生产该类文件为 0；#58（RFQ 超过 1000 条的搜索分页）未修，当前 RFQ 为 0。

## 变更内容

- backend 以 `rayher_crm.wsgi:application` 启动 Gunicorn（release compose 的 `command`），在 Frappe 解析 multipart 之前记录请求入口时间；CRM API 的 multipart 请求（路径以 `/api/method/rayher_crm.` 开头）共用 90 秒准备预算、105 秒事务截止，超时回滚并返回 422。原生 Desk 上传（`/api/method/upload_file`）不在这一截止时间范围内，只受附件门控与扫描器策略约束。
- `before_request` 钩子顺序：`upload_deadline.begin_upload_request`、`attachment_gate.reject_upload_request`；`before_write_file` 保留门控。
- Office 部件上限 500 → 5,000；超限按文件名拒绝。
- `clamav` 服务由 release compose 重建：启动时安装 `backend/clamav/clamd.conf`（`AlertExceedsMax yes`、`MaxFiles 10000`、`MaxRecursion 17`、`MaxScanTime 55000`、`MaxScanSize 200M`、`MaxFileSize 100M`、`StreamMaxLength 100M`）。扫不完的文件按"未通过病毒扫描"拒绝。

## 发布包与脚本

主机目录 `releases/f4a4384d-main-20261011/`：归档 `rayher_crm.zip` sha256 `d03e9bac…`（run 38126526000 package job，与 PR #245 run 38122214386 / 38125109009 产物字节一致）、提交的 `compose.yaml`、`backend/clamav/clamd.conf`（纳入 MANIFEST）、自 3088723 改编的脚本（单镜像形态）。

脚本改编点：`verify-release` 校验归档内门控、截止时间模块与 WSGI 入口，校验 release 内 clamd 配置与 compose 的挂载/启动命令；`verify-migration` 校验前两次发布的 14 个补丁与列/表/索引；`start-backend` 核对容器命令与 `/proc` 中的 Gunicorn 进程确实使用新入口；API 验收核对两处 `before_request` 钩子、`before_write_file`、WSGI 模块可导入；新增 `scanner-policy` 阶段：canonicalize 之后重建 `clamav`、核对容器内配置、用后端自身的扫描客户端跑 `test_clamav_limits` 的三个用例（3,090 部件干净文件通过；内嵌 10,020 文件与 22 层嵌套均拒绝）。

## 演练

staging rehearsal（当时为 5bef99a8 单镜像）以 release `aae47bc8-pr245-20261011`（归档、compose、clamd.conf 与生产发布字节一致）演练三次：前两次分别因脚本自身问题在 `start-backend` 停止（镜像内无 `pgrep`；`grep -q` 提前关管道触发 pipefail），均用 `restore.sh` 恢复；第三次全部通过，含 `scanner-policy`。随后在 rehearsal 关闭开关，上传冒烟 19 项通过（第一次清理因 `CRM Contact File` 元数据只允许软删除而失败，改为 `ignore_on_trash` 后重跑通过）。

## 生产验证

| 阶段 | 结果 |
| --- | --- |
| 预检 08:56:50 | 归档与 release 校验通过；六个服务均为 `e37f782c` 镜像；CNY {0,0,0} |
| 备份 | `backups/pre-update-f4a4384d-main-20261011-20261011-085717/backup/` |
| 迁移 | 9 秒，0 个补丁 |
| verify-migration | 14 个历史补丁在册；列/表/索引齐全；territories 8；CNY {0,0,0} |
| start-backend | `backend_entry=rayher_crm.wsgi:application`（容器命令与进程均核对） |
| 数据/API 验收 | 与冻结快照一致；钩子 deadline/before_request/before_write_file 生效；uploads_paused 当时仍为 True |
| HTTP 验收 | ping 200；/crm 301→200；guest 经理 API 401；5 个资源 200；guest 上传 403 带门控文案 |
| scanner-policy | clamav 重建后 healthy，配置已安装；探测 largeCleanDeck/nestedFileCount/nestedDepth 均符合预期 |
| 开放上传后冒烟 | `UPLOAD-SMOKE-20261011085957c51f`：小文件上传/列表/下载字节一致；3,092 部件 PPTX 上传成功；5,001 部件按名拒绝；扫描器扫不完的嵌套包拒绝；EICAR 拒绝；API 删除；清理后快照一致。结果存于运行目录 `post-upgrade-upload-smoke-result.json` |
| 外部核对 | ping 200，`sid` Secure/HttpOnly，HSTS，HTTP 308；guest 上传 403（Frappe 自身的 guest 规则，门控文案不再出现） |

## 回退

恢复到 `e37f782c` 单镜像状态（会丢失备份之后写入的数据；扫描器保留新策略，无害）：

```bash
CONFIRM_RESTORE=f4a4384d-main-20261011 /home/plancksemicon/apps/rayher-crm-stage1-production/releases/f4a4384d-main-20261011/restore.sh /home/plancksemicon/apps/rayher-crm-stage1-production/releases/f4a4384d-main-20261011/targets/production.env /home/plancksemicon/apps/rayher-crm-stage1-production/backups/pre-update-f4a4384d-main-20261011-20261011-085717
```

回退脚本会把 `crm_attachment_uploads_paused` 一并恢复到备份时的值（True）。如需只关闭上传而不回退，在生产主机上执行（Bench 运行在 Compose 的 backend 容器内）：

```bash
docker exec rayher-crm-stage1-production-backend-1 bench --site 203.0.113.32 set-config crm_attachment_uploads_paused True --parse && docker exec rayher-crm-stage1-production-backend-1 bench --site 203.0.113.32 clear-cache
```

## 后续

- #246 中的恢复条件已满足"#243/#244/#245 完成并在生产验证"这一项；#220、#58、DocumentCenter 文案与 #186 仍开放。
- `rayher-crm-rehearsal` 保留在 `aae47bc8-pr245-20261011` 升级后、开关关闭的状态。
