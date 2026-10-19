# 局域网浏览器预览实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留本机专用启动命令的同时，增加可供同一局域网浏览器访问的 Vite 开发与生产预览命令。

**Architecture:** 仅修改 `package.json` 的 scripts，不改变 Vite、应用代码或数据适配器。局域网命令显式绑定 `0.0.0.0`，原有命令继续绑定 `127.0.0.1`。

**Tech Stack:** Windows PowerShell、pnpm 11.9.0、Vite 8.1.5、Vue 3。

## Global Constraints

- 只用于可信的同一局域网，不配置公网端口转发。
- Windows 防火墙如需授权，只允许专用网络。
- 不修改当前 `.env.local` 的 Mock Adapter 设置。
- 不增加依赖，不修改应用业务代码。
- 当前目录不是有效 Git 仓库，因此跳过提交步骤。

---

### Task 1: 增加并验证局域网启动命令

**Files:**
- Modify: `package.json`
- Reference: `docs/superpowers/specs/2026-07-22-lan-browser-preview-design.md`

**Interfaces:**
- Consumes: Vite CLI 的 `--host` 和 `--port` 参数。
- Produces: `pnpm dev:lan` 与 `pnpm preview:lan` 两个命令。

- [ ] **Step 1: 验证当前命令中没有局域网入口**

Run:

```powershell
$scripts = (Get-Content -Raw -Encoding UTF8 package.json | ConvertFrom-Json).scripts
if ($scripts.'dev:lan' -or $scripts.'preview:lan') { throw 'LAN scripts already exist.' }
```

Expected: 命令演示员工152退出，不产生异常。

- [ ] **Step 2: 添加最小配置**

将 `package.json` 的 `scripts` 更新为保留原命令并增加：

```json
"dev:lan": "vite --host 0.0.0.0 --port 5173",
"preview:lan": "vite preview --host 0.0.0.0 --port 4173"
```

- [ ] **Step 3: 验证 package.json 和前端质量门**

Run:

```powershell
pnpm typecheck
pnpm test
pnpm build
```

Expected: TypeScript 检查通过、111 个测试通过、Vite 构建成功。

- [ ] **Step 4: 启动局域网生产预览**

先停止当前仅监听 `127.0.0.1:4173` 的旧预览进程，再运行：

```powershell
pnpm preview:lan
```

Expected: Vite 显示 Network 地址 `http://203.0.113.10:4173/`，进程保持运行。

- [ ] **Step 5: 验证监听与 HTTP 响应**

Run:

```powershell
netstat -ano -p tcp | Select-String ':4173'
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4173/ | Select-Object StatusCode
Invoke-WebRequest -UseBasicParsing http://203.0.113.10:4173/ | Select-Object StatusCode
```

Expected: 端口监听地址不是 `127.0.0.1:4173`，两个 HTTP 请求均返回 `200`。

- [ ] **Step 6: 同事侧验收**

让同一局域网内的同事打开：

```text
http://203.0.113.10:4173/
```

Expected: 页面和静态资源演示员工152加载；如 Windows 防火墙提示，仅勾选“专用网络”。

