# CRM Ubuntu Staging 部署与回滚清单

> 状态：本地端到端 Gate 已完成；本文只固化 staging 前置条件和可复现步骤。尚未取得目标服务器地址、SSH 身份、DNS/TLS 与维护窗口，因此未执行远程写入。

## 1. 本次候选制品

- Frappe / ERPNext：v15 固定 digest，禁止改用 `latest`、浮动 v15 或旧 v16 镜像。
- CRM App ZIP：`backend/build/rayher_crm.zip`。
- 当前候选 ZIP：761 entries，3,288,592 bytes，SHA-256 `1E650C4AA75BD4BB62EB1D90BF956AAA5ADC5F7AA7F25CCBCF857EB42C23E63E`。
- Compose：`backend/compose.yaml`；staging 必须使用独立 project、独立 site、独立 volumes 和独立网络。
- 运行时：MariaDB 10.6、Redis 6.2、ClamAV 1.4.5，均使用仓库内已固定 digest。

部署前必须重新生成 ZIP 并记录新的 SHA-256；任何源码或生成前端变化都会使上面的候选哈希失效。

## 2. 必须由部署负责人提供的外部参数

- Ubuntu 服务器地址、SSH 用户和已授权密钥位置；不得把私钥复制进仓库。
- staging FQDN、DNS A/AAAA 记录、TLS 证书签发方式和反向代理责任人。
- 维护窗口、验收负责人、故障升级联系人。
- 加密且位于服务器之外的备份目标；只有本机 volume 快照不算可恢复备份。
- staging 人员清单：至少覆盖 `docs/CRM-人员显示名到Frappe用户ID迁移映射-2026-08-04.csv` 中会出现在 Owner/Engineer 字段的 Frappe User，并分配最小 CRM 角色。

缺少任意一项时，不执行实际上线或创造临时公网暴露方案。

## 3. 服务器预检 Gate

1. Ubuntu 安全更新、时钟同步、防火墙和磁盘告警已启用。
2. Docker Engine 与 Compose v2 可用；非授权用户不能访问 Docker socket。
3. 可用磁盘必须覆盖镜像、数据库、站点文件、ClamAV 病毒库和至少一次本地暂存备份，并保留增长余量。
4. 只允许 80/443 对外；Compose 的 CRM 端口继续绑定 `127.0.0.1`，由主机反向代理终止 TLS。
5. 服务器上不存在同名 Compose project、volume 或网络；若存在，先人工确认归属，绝不复用或删除未知资源。

## 4. Staging 环境文件

在服务器的受限部署目录创建不入 Git 的 `backend/.env.staging`，至少设置：

```dotenv
COMPOSE_PROJECT_NAME=rayher-crm-stage1-staging
SITE_NAME=crm-staging.example.com
HTTP_PORT=2224
ALLOW_TESTS=false
CRM_IMAGE=rayher-crm-stage1:v15-staging
```

其余基础镜像变量沿用 `.env.example` 中的固定 digest。执行以下检查时只读取退出码，不把展开后的 Compose 配置写入日志：

```bash
docker compose --env-file backend/.env.staging -f backend/compose.yaml config --quiet
sha256sum backend/build/rayher_crm.zip
```

## 5. 首次部署顺序

```bash
set -euo pipefail
archive_hash="$(sha256sum backend/build/rayher_crm.zip | awk '{print $1}')"
test -n "$archive_hash"
docker compose --env-file backend/.env.staging -f backend/compose.yaml build --build-arg "CRM_APP_ARCHIVE_SHA256=$archive_hash" backend
docker compose --env-file backend/.env.staging -f backend/compose.yaml up -d --no-build
docker compose --env-file backend/.env.staging -f backend/compose.yaml ps
```

Compose 会幂等创建独立 site、安装 `rayher_crm`、设置 `ALLOW_TESTS=false` 并执行 migrate。不得从本地环境复制数据库 volume、`local-secrets` volume 或管理员会话。

随后在 Frappe 中创建/核验获批人员 User 与 CRM 角色；禁止为了让表单通过而启用共享账号、弱密码或客户端身份伪造。

## 6. 反向代理与 TLS Gate

- 反向代理只转发到 `127.0.0.1:2224`，保留 Host、X-Forwarded-For 和 X-Forwarded-Proto。
- 强制 HTTPS，启用合理的请求体上限和 120 秒上游超时；WebSocket 路径必须支持 Upgrade。
- `/crm` 对 Guest 必须跳转 `/login?redirect-to=%2Fcrm`；登录后必须落到带内容哈希 query 的 CRM hash-router URL。
- 不对 `index.html` 设置长期 immutable 缓存；带哈希的 JS/CSS 资源可以长缓存。

## 7. 上线验收 Gate

```bash
curl --fail --silent https://crm-staging.example.com/api/method/ping
docker compose --env-file backend/.env.staging -f backend/compose.yaml exec -T backend \
  bench --site crm-staging.example.com migrate
docker compose --env-file backend/.env.staging -f backend/compose.yaml ps
```

还必须人工验收：

- Guest 登录边界、Manager/Sales/Engineer 三类真实 Frappe 会话与最小权限。
- Dashboard、客户列表、客户创建、Account 360 的真实 GET/POST；禁止出现 Mock seed 或身份切换。
- Contact 文件、Demo Artifact、报告下载、ClamAV 拒绝路径与收件人隔离。
- 数据库中 Customer/Contact/Lead 与自有 CRM DocType 正确落库；Asset、Sales Order、Delivery Note、Project、Task、Quality Inspection 不因 CRM 操作生成。
- 浏览器控制台无 CRM 应用错误，页面显示 Frappe / ERPNext v15。

## 8. 升级前备份

每次升级前，在当前健康版本上执行带文件备份，并把备份与校验和复制到受控的异机存储：

```bash
docker compose --env-file backend/.env.staging -f backend/compose.yaml exec -T backend \
  bench --site crm-staging.example.com backup --with-files
```

同时记录：当前 App ZIP SHA-256、镜像 ID/digest、Compose project、site 名、数据库/站点/secret volume 名和部署时间。备份完成不等于可恢复；首次上线前必须在隔离环境完成一次 restore drill。

## 9. 回滚原则

1. 若只在健康检查前发现镜像启动失败且 migrate 未执行，可切回上一候选镜像并重建六个无状态应用服务。
2. migrate 已执行后，不假设旧镜像兼容新 schema；进入维护窗口，先保全故障现场，再用同一时间点的数据库与 sites/files 备份整体恢复。
3. 不用 `docker compose down -v`，不删除或复用未知 volume，不以空 site 覆盖故障 site。
4. 回滚后重跑 Guest/login、ping、角色权限、代表性读写和被禁止 ERP 实体计数；证据不完整时保持 staging 隔离，不推进生产。

## 10. 当前明确阻塞

- 缺少真实 Ubuntu 服务器连接参数与远程写入授权。
- 缺少 staging FQDN/TLS/反向代理信息。
- 缺少获批的 staging 人员与角色初始化清单。
- 缺少异机备份目标和维护窗口。

这些阻塞只影响远程 staging；本地独立 Docker 栈和 Stage 6 Gate 不受影响。
