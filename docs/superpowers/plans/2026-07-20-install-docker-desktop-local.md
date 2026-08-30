# Docker Desktop Local Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 Windows 用户下安装 Docker Desktop，启用 WSL 2 Linux 容器后端，并验证 Docker Engine、Compose v2 与本地端口 2223。

**Architecture:** 使用 Docker 官方 Windows 安装包的当前用户模式，不创建 Frappe 容器、不修改项目业务数据。安装后启动 Docker Desktop，等待 Engine 就绪，再运行只读版本和最小容器验证。

**Tech Stack:** Windows 11 Pro、Docker Desktop、WSL 2、Docker Engine、Docker Compose v2

## Global Constraints

- 安装范围为当前 Windows 用户。
- Docker 后端为 WSL 2，使用 Linux containers。
- 不安装或启动 Frappe、MariaDB、Redis或项目容器。
- 不在源码、日志或文档中写入密码、Token或Cookie。
- 预留本地 Web 入口端口为 `2223`。
- 若安装器要求注销、重启或人工接受协议，停止自动化并明确报告。

---

### Task 1: 安装 Docker Desktop

**Files:**
- Reference: `docs/superpowers/specs/2026-07-20-frappe-local-backend-design.md`

**Interfaces:**
- Consumes: Windows 11、WSL 2.7.10、当前用户安装权限
- Produces: `docker.exe`、Docker Desktop、Docker Engine、`docker compose`

- [ ] **Step 1: 检查安装状态**

Run: `Get-Command docker -ErrorAction SilentlyContinue`

Expected: 当前返回空，确认不是覆盖现有安装。

- [ ] **Step 2: 检查官方 Winget 包信息**

Run: `winget show --exact --id Docker.DockerDesktop`

Expected: 包标识为 `Docker.DockerDesktop`，来源为 Winget。

- [ ] **Step 3: 以当前用户模式安装**

Run: `winget install --exact --id Docker.DockerDesktop --scope user --silent --accept-package-agreements --accept-source-agreements`

Expected: 安装器返回成功；若 Winget 不支持 user scope，则下载 Docker 官方安装器并使用 `install --user`，不切换到全系统安装。

- [ ] **Step 4: 刷新并验证 CLI 文件**

Run: `Get-Command docker; docker --version; docker compose version`

Expected: 三条检查均返回版本信息。

### Task 2: 启动并验证 Docker Engine

**Files:**
- None

**Interfaces:**
- Consumes: Task 1 安装的 Docker Desktop
- Produces: 已运行的 WSL 2 Linux Docker Engine

- [ ] **Step 1: 启动 Docker Desktop**

Run: `Start-Process "$env:LOCALAPPDATA\Programs\Docker\Docker\Docker Desktop.exe"`

Expected: Docker Desktop进程启动；若安装位置不同，则从注册表或应用路径解析实际可执行文件。

- [ ] **Step 2: 等待 Engine 就绪**

Run: `docker info --format '{{json .ServerVersion}}'`

Expected: 返回服务端版本；未就绪时按短间隔重试，并在60秒内提供进度更新。

- [ ] **Step 3: 验证 Linux 容器**

Run: `docker run --rm hello-world`

Expected: 容器成功拉取、运行并自动删除，输出 Docker Hello World成功消息。

- [ ] **Step 4: 验证 Compose v2**

Run: `docker compose version`

Expected: 返回 Docker Compose v2版本。

- [ ] **Step 5: 验证端口 2223**

Run: `Get-NetTCPConnection -LocalPort 2223 -State Listen -ErrorAction SilentlyContinue`

Expected: 返回空，端口仍可供后续 Frappe入口使用。

- [ ] **Step 6: 记录安装结果**

记录 Docker Desktop、Engine、Compose和WSL版本，以及是否需要用户注销、重启或首次确认；不记录任何凭据。
