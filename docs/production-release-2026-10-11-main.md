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

- 附件恢复：按 #246 的顺序；#245 合并后需单独发布并重建 `clamav`。恢复前重跑上传、审批、下载与权限冒烟。关闭开关是 site_config 变更加 `clear-cache`，不是部署副作用。
- `launch-guard-20261011`、`launch-guard-p1-20261011` 目录保留作记录，不再参与部署。
- 待补记：run 38121037483 的 backend job 结果。
- 发布脚本与演练记录在两台主机的 `releases/` 目录及 `upgrade-*.log`、`restore-*.log`；staging rehearsal 保留在升级后状态。
