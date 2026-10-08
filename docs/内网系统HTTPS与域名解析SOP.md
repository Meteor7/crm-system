# 内网系统 HTTPS 与域名解析 SOP

适用于公司内网系统通过自有域名访问，并由 Ubuntu 服务器运行 Nginx、由
Microsoft AD CS 签发内部证书的场景。

## 0. 参考实践与对齐原则

本 SOP 参考了 Cloudflare、AWS、Microsoft、Google 等成熟云服务和企业平台
公开文档中反复采用的工程做法，并结合你们的内网条件落地。这里对齐的是通用
架构原则，不代表直接复制某一家厂商的产品配置：

| 成熟平台的通用做法 | 本 SOP 的对应落地 |
| --- | --- |
| 在边缘/网关统一终止 TLS，后端服务不直接暴露证书和公网入口（Cloudflare、AWS 等） | Ubuntu 上由 Nginx 监听 443，CRM 只监听 `127.0.0.1:<应用端口>` |
| 使用域名承载访问入口，证书 SAN 与访问域名严格匹配（各大云平台证书服务） | iKuai/内网 DNS 将域名解析到应用服务器，AD CS 证书包含正确 DNS SAN |
| 通过反向代理转发真实客户端信息和原始协议（Nginx、AWS ALB 等） | 转发 `Host`、`X-Forwarded-For`、`X-Forwarded-Proto`，保证 Frappe 正确生成 HTTPS 链接 |
| 对长连接单独配置升级和超时（Cloudflare、AWS WebSocket 文档） | `/socket.io` 单独配置 Upgrade/Connection 头和 `proxy_read_timeout` |
| 企业内部 PKI 统一签发和分发信任链（Microsoft AD CS） | AD CS 只负责签发；Windows/macOS 客户端信任企业根 CA |
| 环境隔离、最小暴露面、可验证变更和可回滚（Google/AWS 生产运维实践） | staging/production 分离，数据库和 Redis 不发布端口，先 `nginx -t` 再 reload，保留配置备份 |

因此本方案选择“内网 DNS + 企业 CA + Nginx TLS 终止 + 本机应用 upstream”，
而不是让业务框架自行监听 HTTPS 或给每个客户端分发 hosts。该组合适合内网
系统，也方便后续统一续期、审计和迁移。

## 1. 标准架构

```text
客户端
  | 访问 https://<域名>/<路径>
  v
公司 DNS / iKuai
  | <域名> -> <应用服务器内网 IP>
  v
Ubuntu 应用服务器
  | 443: Nginx HTTPS
  | 80: 308 跳转到 HTTPS
  ` 127.0.0.1:<应用端口>: 应用/Frappe/Docker

Microsoft AD CS 仅负责签发证书，不负责转发业务流量。
```

核心原则：应用端口只监听 `127.0.0.1`，用户只访问 80/443；不要把应用端口
直接暴露给局域网，也不要让前端代码写死后端 IP。

## 2. 变量表

部署前先填写：

```text
域名：<例如 crm.example.invalid>
应用服务器：<例如 203.0.113.32>
应用本机端口：<例如 4174>
CA 服务器：<例如 203.0.113.204>
站点路径：<例如 /crm>
```

同一域名只能指向一个目标环境。staging 和 production 使用不同域名、证书、
Compose project、数据卷和 secret。

## 3. 配置内网 DNS / iKuai

在 iKuai 或公司内部 DNS 添加 A 记录：

```text
<域名>  A  <应用服务器内网 IP>
```

例如：

```text
crm.example.invalid  A  203.0.113.32
```

不需要配置路由器端口转发。客户端和应用服务器在同一网段时通常不需要新增
静态路由。公网 DNS 不应发布 RFC1918 内网 IP。

客户端验证：

```powershell
Resolve-DnsName <域名>
```

或：

```bash
nslookup <域名>
```

结果必须是目标应用服务器 IP。

没有内部 DNS 时，可在少量测试电脑的 hosts 文件临时添加：

```text
<应用服务器内网 IP> <域名>
```

hosts 适合临时验证，不适合多人长期生产使用。

## 4. 在 Ubuntu 生成私钥和 CSR

私钥必须在最终提供 HTTPS 的 Ubuntu 服务器上生成，并且不上传到 CA、聊天或
代码仓库：

```bash
sudo install -d -m 700 /etc/ssl/private/<服务名>
sudo install -d -m 755 /etc/ssl/certs/<服务名>

sudo openssl req -new -newkey rsa:3072 -nodes \
  -keyout /etc/ssl/private/<服务名>/<域名>.key \
  -out /tmp/<域名>.csr \
  -subj "/CN=<域名>" \
  -addext "subjectAltName=DNS:<域名>" \
  -addext "extendedKeyUsage=serverAuth"

sudo chmod 600 /etc/ssl/private/<服务名>/<域名>.key
```

检查 CSR，不要打印私钥：

```bash
openssl req -in /tmp/<域名>.csr -noout -text
```

必须包含正确的 CN/SAN 和 `Server Authentication` 用途。浏览器主要校验 SAN，
不能只依赖 CN。

## 5. 通过 Microsoft AD CS 签发

使用 CA Web Enrollment 或公司的证书申请流程提交 CSR：

```text
http://<CA服务器>/certsrv/
```

选择适合服务器 TLS 的模板，通常是 `Web Server` 或公司定制模板。模板必须：

- 允许申请账号 Enroll；
- 包含 `Server Authentication` EKU；
- 允许从 CSR 提供 SAN（Supply in the request）；
- SAN 包含 `<域名>`。

下载 Base-64/PEM 格式的签发证书。证书文件名可以任意，例如
`<域名>-issued.cer`；文件名不决定证书类型。

同时准备企业根 CA（以及存在时的中间 CA）证书。网站证书和根 CA 不是同一张：

```text
网站证书：Subject=<域名>，Issuer=Qiheng Demo Internal Root CA
根证书：Subject=Qiheng Demo Internal Root CA，Issuer=自身
```

## 6. 安装并验证证书

把签发证书复制到 Ubuntu，例如：

```bash
sudo install -o root -g root -m 644 \
  /tmp/<域名>-issued.cer \
  /etc/ssl/certs/<服务名>/<域名>.crt
```

如果下载的是 DER 格式，先转换：

```bash
sudo openssl x509 -inform DER \
  -in /tmp/<域名>-issued.cer \
  -out /etc/ssl/certs/<服务名>/<域名>.crt
```

检查证书：

```bash
openssl x509 -in /etc/ssl/certs/<服务名>/<域名>.crt \
  -noout -subject -issuer -dates -ext subjectAltName
```

确认域名、SAN、签发者和有效期正确。

检查私钥：

```bash
sudo openssl pkey \
  -in /etc/ssl/private/<服务名>/<域名>.key \
  -check -noout
```

确认签发证书和私钥是一对。两个公钥摘要必须一致：

```bash
openssl x509 -in /etc/ssl/certs/<服务名>/<域名>.crt \
  -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum

sudo openssl pkey -in /etc/ssl/private/<服务名>/<域名>.key \
  -pubout | openssl pkey -pubin -outform DER | sha256sum
```

不一致就停止，不要配置 Nginx；重新生成 CSR 并重新签发。

如果有中间 CA，创建链证书（服务器证书在前，中间 CA 在后）：

```bash
sudo sh -c 'cat /etc/ssl/certs/<服务名>/<域名>.crt \
  /etc/ssl/certs/<服务名>/<中间CA>.crt \
  > /etc/ssl/certs/<服务名>/fullchain.pem'
```

## 7. 配置应用只监听本机

以 Docker Compose 为例，将环境文件中的端口绑定改为：

```dotenv
HTTP_BIND_ADDRESS=127.0.0.1
HTTP_PORT=<应用端口>
```

例如：

```dotenv
HTTP_BIND_ADDRESS=127.0.0.1
HTTP_PORT=4174
```

先备份环境文件，再只重建对应 frontend/ingress 服务：

```bash
cp -p .env.production .env.production.before-https
docker compose --env-file .env.production config --quiet
docker compose --env-file .env.production up -d --no-deps frontend
```

不要使用 `docker compose down --volumes`。不要重启或删除不属于该应用的
Compose 项目、容器、卷和数据库。

检查监听：

```bash
sudo ss -ltnp | grep -E ':80|:443|:<应用端口>'
```

目标结果是 `0.0.0.0:80`、`0.0.0.0:443` 和 `127.0.0.1:<应用端口>`。

## 8. 配置 Nginx

安装并启用 Nginx：

```bash
sudo apt update
sudo apt install -y nginx
```

生产配置至少包含：

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream app_upstream {
    server 127.0.0.1:<应用端口>;
}

server {
    listen 80;
    server_name <域名>;
    return 308 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name <域名>;

    ssl_certificate     /etc/ssl/certs/<服务名>/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/<服务名>/<域名>.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;

    location /socket.io {
        proxy_pass http://app_upstream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }

    location / {
        proxy_pass http://app_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $host;
        proxy_redirect off;
        proxy_read_timeout 120s;
    }
}
```

Ubuntu Nginx 1.28 推荐使用独立的 `http2 on;`，避免旧式 `listen ... http2`
弃用警告。先检查再 reload：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

不要先打开 HSTS。确认整个域名及其子域名都必须强制 HTTPS 后，再考虑启用：

```nginx
add_header Strict-Transport-Security "max-age=31536000" always;
```

首次不要加入 `includeSubDomains` 或 `preload`。

## 9. 客户端信任内部 CA

客户端安装的是企业根 CA 证书，不是 `<域名>-issued.cer` 网站证书。

### Windows

双击根 CA `.cer` 文件，选择“安装证书” -> “本地计算机” -> “将所有证书放入
以下存储” -> “受信任的根证书颁发机构”。域控环境优先使用组策略统一下发。

管理员 PowerShell：

```powershell
Import-Certificate `
  -FilePath 'C:\Temp\Planck-Semicon-Internal-Root-CA.cer' `
  -CertStoreLocation 'Cert:\LocalMachine\Root'
```

### macOS

双击根 CA 文件，在“钥匙串访问”中导入到“系统”钥匙串，打开证书的“信任”，
将“使用此证书时”改为“始终信任”，然后重新打开浏览器。命令行方式：

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/Downloads/Planck-Semicon-Internal-Root-CA.cer
```

Firefox 可能使用独立证书库，需要在 Firefox 中单独导入根 CA。

## 10. 验收清单

在服务器本机验证：

```bash
curl -kI --resolve <域名>:443:127.0.0.1 https://<域名>/<路径>
curl -I --resolve <域名>:80:127.0.0.1 http://<域名>/<路径>
```

从另一台已安装根 CA 的公司电脑验证：

```bash
curl -I https://<域名>/<路径>
curl -i https://<域名>/api/method/ping
curl -sI https://<域名>/api/method/ping | grep -i '^set-cookie: sid='
```

必须满足：

- HTTP 返回 `308` 并跳转到 HTTPS；
- HTTPS 证书主机名和 SAN 匹配；
- 浏览器没有证书警告；
- 浏览器地址栏没有应用端口；
- API 返回正常，Guest 进入登录边界；
- 登录、文件上传/下载和 WebSocket 使用 HTTPS/WSS；
- 经 HTTPS 返回的 `Set-Cookie: sid=` 带 `Secure`。CRM 依赖 Compose backend 的
  `FORWARDED_ALLOW_IPS`，见 `deploy/nginx/README.md`；
- `4174` 等应用端口不再监听在 `0.0.0.0`；
- 数据库、Redis、ClamAV 等内部服务没有 published ports；
- Nginx、应用和 Docker 日志没有阻断性错误。

## 11. 回滚与续期

配置失败时先恢复 Nginx 配置并 reload，再恢复环境文件并只重建受影响服务：

```bash
sudo nginx -t
sudo systemctl reload nginx
cp -p .env.production.before-https .env.production
docker compose --env-file .env.production up -d --no-deps frontend
```

不要删除数据卷。证书到期前提前续期，重复“生成 CSR/提交 AD CS/匹配验证/替换
证书/`nginx -t`/reload”流程。每次续期都要检查 SAN、有效期和证书私钥匹配。

## 12. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `ERR_CERT_AUTHORITY_INVALID` | 客户端不信任企业根 CA | 安装 `Qiheng Demo Internal Root CA`，不要安装网站证书到根信任库 |
| `ERR_CERT_COMMON_NAME_INVALID` | 域名不在 SAN 中 | 重新生成包含正确 DNS SAN 的 CSR 并签发 |
| 证书和私钥摘要不一致 | CSR 与当前私钥不是一对 | 停止部署，重新生成私钥和 CSR |
| HTTP 可访问但 HTTPS 不通 | Nginx 未监听 443、证书路径错误或防火墙阻断 | `nginx -t`、`ss -ltnp`、检查防火墙 |
| 页面能开但实时功能失败 | WebSocket 升级头或 `X-Forwarded-Proto` 缺失 | 检查 `/socket.io` location 配置 |
| 仍可访问 `:4174` | Compose 仍绑定 `0.0.0.0` | 改为 `127.0.0.1` 并重建对应 frontend |
| 浏览器跳转回 HTTP | Frappe/反代未正确传递 HTTPS scheme | 检查 `X-Forwarded-Proto https` 和站点 URL 配置 |
| HTTPS 下会话 cookie 没有 `Secure` | backend 的 gunicorn 只信任本机回环转发的 `X-Forwarded-Proto` | Compose backend 设置 `FORWARDED_ALLOW_IPS`，见 `deploy/nginx/README.md` |

## 13. 安全禁忌

- 不在聊天、Git、工单或日志中发送私钥、密码、PFX 密码和 CA 管理凭据。
- 不把网站证书当作根 CA 安装到客户端信任库。
- 不把内网 IP 发布到公网 DNS。
- 不做路由器端口转发到应用端口。
- 不用 Vite dev/preview HTTPS 配置替代生产 Frappe/Nginx 方案。
- 不执行 `docker compose down --volumes` 作为普通排障手段。
