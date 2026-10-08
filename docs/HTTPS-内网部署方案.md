# CRM 内网 HTTPS 部署方案

## 现状（2026-10-07 只读核对）

- 生产自 2026-08-31 起通过 `https://crm.example.invalid` 提供服务。公司内网 DNS 把该域名解析到
  `203.0.113.32`。生产机上的 Nginx 1.28 在 80 端口返回 308 跳转到 HTTPS，在 443 端口终止 TLS，
  再转发到本机 `127.0.0.1:4174` 的 Compose frontend。
- 生产的 `/etc/nginx/conf.d/crm.plancksemicon.cn.conf` 与 `deploy/nginx/crm-https.conf.template`
  按生产值渲染的结果逐字节一致，去掉模板开头的注释后共 1488 字节。
- 证书由 `Qiheng Demo Internal Root CA` 签发，SAN 为 `DNS:crm.example.invalid` 和
  `IP:203.0.113.32`，有效期 2026-09-09 至 2027-09-09，没有自动续期。
- 生产的 Compose frontend 只监听 `127.0.0.1:4174`；MariaDB、Redis、ClamAV 不发布主机端口。
- 测试服 `203.0.113.58` 没有 TLS 代理：Nginx 未运行，frontend 直接在 `0.0.0.0:4174` 以 HTTP
  对局域网提供服务。
- 经 HTTPS 访问时，Frappe 下发的会话 cookie 没有 `Secure`。frontend 容器里的 Nginx 会原样转发
  `X-Forwarded-Proto: https`，但 backend 的 gunicorn 默认只信任来自本机回环地址的这个请求头，而请求
  来自 frontend 容器，于是 Frappe 按 HTTP 处理。`backend/compose.yaml` 现在让 backend 信任 frontend
  转发的协议（`FORWARDED_ALLOW_IPS`），随下一次生产升级生效。CI 用真实请求检查：按 HTTPS 转发时
  会话 cookie 带 `Secure`，纯 HTTP 请求不带。

## 架构

```text
浏览器 -- HTTPS:443 --> 生产机 Nginx -- HTTP:127.0.0.1:4174 --> Compose frontend
        (HTTP:80 一律 308 到 HTTPS)                             |-- /api/method/... --> backend
                                                                `-- /socket.io      --> websocket
```

不改 Vue 业务代码，也不让 Frappe 容器直接持有证书。沿用同源 API 和 Socket.IO，避免 CORS、
Cookie 跨站和前端地址分叉。模板、生产取值和重建步骤见 `deploy/nginx/README.md`；域名解析、
证书申请、客户端信任和续期见 `docs/内网系统HTTPS与域名解析SOP.md`。

## 待办

1. **证书续期**：2027-09-09 到期。建议 2027 年 8 月前按 SOP 第 4 至 6 节和第 11 节换证，过期后
   浏览器会报安全警告。
2. **客户端信任**：没有安装公司根证书的电脑会提示证书不受信任。按 SOP 第 9 节安装根证书，域内
   电脑优先用组策略统一下发。
3. **默认站点**：生产机 `/etc/nginx/sites-enabled/default.disabled` 仍指向 Ubuntu 默认站点。Nginx
   会加载 `sites-enabled` 下的所有文件，不看文件名，所以 `http://192.168.1.33/` 显示 Nginx 欢迎页。
   删除这个链接、`nginx -t` 通过后 reload，按 IP 的 HTTP 请求也会跳转到 HTTPS。
4. **HSTS**：暂不启用。证书由内部 CA 手工续期；启用 HSTS 后，证书一旦过期或不受信任，用户无法
   临时继续访问。
5. **`host_name`**：站点没有设置 `host_name`，后台任务生成的绝对链接会用站点名
   `http://203.0.113.32`。目前没有外发邮件，影响很小；需要时在 site_config 把 `host_name` 设为
   `https://crm.example.invalid`。

## 生产验收清单

- `http://crm.example.invalid/` 返回 308，跳转到 `https://crm.example.invalid/`。
- 证书主机名匹配，客户端信任完整证书链，TLS 只启用 1.2 和 1.3。
- `https://crm.example.invalid/api/method/ping` 返回 200，Guest 进入 Frappe 登录边界。
- 升级到含 `FORWARDED_ALLOW_IPS` 的版本后，上一条响应的 `Set-Cookie: sid=` 带 `Secure`：

  ```bash
  curl -sI https://crm.example.invalid/api/method/ping | grep -i '^set-cookie: sid='
  ```

- 登录后 API、文件上传下载和 Socket.IO 都走 HTTPS/WSS，没有 4xx/5xx 或 Mixed Content。
- 生产机对局域网只开放 Nginx 的 80/443；4174 只监听回环地址；MariaDB、Redis、ClamAV 没有
  published ports。

## 回滚

- Nginx：恢复上一份配置，`sudo nginx -t` 通过后 `sudo systemctl reload nginx`。Compose 和数据卷
  不受影响。
- `FORWARDED_ALLOW_IPS`：随版本回滚即可。它只决定 cookie 是否带 `Secure`，不涉及数据。
- 任何情况下都不要执行 `docker compose down --volumes`。

## 给测试服加 HTTPS（未实施）

测试服目前是局域网 HTTP。若要加 HTTPS：为测试服申请独立的内部域名和证书，不得复用生产证书；把
frontend 改为只监听 `127.0.0.1:4174`；用同一模板以测试服的取值渲染 Nginx 配置，`nginx -t` 通过后
reload；再按上面的验收清单检查。生产与测试服不得共用证书、Compose project、数据卷或 secret。
