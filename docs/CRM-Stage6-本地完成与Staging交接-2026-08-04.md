# CRM Stage 6 本地完成与 Staging 交接

## 当前结论

- 本地独立项目 `rayher-crm-stage1-local` 已完成 Frappe Adapter、真实浏览器 E2E、全量回归和最终数据清理。
- 新项目 10 个服务运行；backend/frontend/DB/Redis/ClamAV healthy，其余 worker/scheduler/websocket Up。
- 旧项目 `rayher-crm` 仍为 running(9)，未停止、重建或删除其 volumes。
- 不存在进行中的测试/构建命令；一次性 2235 listener、临时 helper、临时 E2E User 和客户均不存在。
- 尚未执行 Ubuntu staging，因为缺少服务器、SSH、DNS/TLS、人员、备份目标和维护窗口。

## 最终制品

- App ZIP：`backend/build/rayher_crm.zip`
- entries：245
- bytes：6,118,200
- SHA-256：`E0A7BA286782560DAE56CA0DE868EC8251C8E4CC50D41FD8AC1DBD7BCA7B310A`
- 本地镜像：`rayher-crm-stage1:v15-local`
- 本地入口：`http://127.0.0.1:2224/crm`

若任何 App 源码或 `public/crm` 产物变化，先重新 build/package 并更新哈希，不能继续使用本段哈希。

## 验证结果

- Frappe Adapter：17/17。
- Frappe web entry：2/2。
- 完整 `rayher_crm` App：105/105，文本 `OK`。
- 前端：78/78 files、508/508 tests。
- `vue-tsc --noEmit`：通过。
- 默认 Mock build：通过，2613 modules。
- Frappe build：通过，2603 modules；105 files、8,146,799 bytes、Mock guard 139 bytes，无已知 Mock customer/REQ seed。
- 最终镜像连续 migrate 两次：通过。
- HTTP：ping 200；Guest `/crm` 301 到登录；静态 index 200。
- 真实浏览器：Dashboard、客户列表、客户创建、Account 360、v15 标识、内容哈希入口和 Guest 登录边界通过。

## 最终数据只读快照

- Company 1；Contact 43（既有标准记录，未删除）。
- Customer、Lead、CRM Opportunity、CRM Booking、CRM Visit、CRM Demo Request、CRM Evaluation、CRM Installed Tool：0。
- Asset、Sales Order、Delivery Note、Project、Task、Quality Inspection：0。
- 临时 `person002@crm.example.invalid` E2E User：不存在。

## 本轮主要落盘文件

- `src/api/frappe-adapter.ts`、`src/api/frappe-adapter.test.ts`
- `src/api/runtime-adapter.ts`、`src/api/runtime-adapter.frappe.ts`
- `src/api/mock-identity-switch.ts`、`src/api/mock-identity-switch.frappe.ts`
- `src/api/index.ts`、`src/stores/app.ts`
- `src/app/AppShell.vue`、`src/app/AppShell.frappe.test.ts`、`src/app/router.ts`
- `vite.config.ts`、`package.json`
- `backend/compose.yaml`
- `backend/apps/rayher_crm/rayher_crm/www/crm.py`、`crm.html`、`__init__.py`
- `backend/apps/rayher_crm/rayher_crm/tests/test_stage6_web_entry.py`
- `backend/apps/rayher_crm/rayher_crm/public/crm/**`
- `backend/tests/frappe-frontend-contract.ps1`、`app-package-contract.ps1`、`compose-contract.ps1`
- `docs/superpowers/plans/2026-08-04-crm-stage6-frappe-adapter-e2e.md`
- `docs/CRM-Ubuntu-Staging部署与回滚清单-2026-08-04.md`
- `docs/CRM-持续执行审计日志-2026-08-04.md`

## Git 状态边界

- 工作树在本轮开始前已包含大量用户修改和未跟踪文件；`backend/` 整体仍显示未跟踪，不能据此推断它只包含 Stage 6 文件。
- Stage 6 相关 tracked 修改至少包括 `package.json`、`vite.config.ts`、Frappe adapter/index、AppShell/router/store；新增 runtime aliases、Frappe-mode AppShell test、backend 和 Stage 6 文档。
- `.gitignore` 是受保护/既有修改，本轮未读取修复、未覆盖。
- 本轮未执行 commit、reset、stash、clean、checkout 或 staging。

## 继续部署前的命令

先取得并核对外部参数，然后在 Ubuntu 受控部署目录执行；不要把展开后的配置或凭据保存到日志：

```bash
set -euo pipefail
docker compose --env-file backend/.env.staging -f backend/compose.yaml config --quiet
archive_hash="$(sha256sum backend/build/rayher_crm.zip | awk '{print $1}')"
test -n "$archive_hash"
docker compose --env-file backend/.env.staging -f backend/compose.yaml build --build-arg "CRM_APP_ARCHIVE_SHA256=$archive_hash" backend
docker compose --env-file backend/.env.staging -f backend/compose.yaml up -d --no-build
docker compose --env-file backend/.env.staging -f backend/compose.yaml ps
curl --fail --silent https://<staging-fqdn>/api/method/ping
```

完整备份、TLS、人员初始化、验收和回滚步骤见 `docs/CRM-Ubuntu-Staging部署与回滚清单-2026-08-04.md`。
