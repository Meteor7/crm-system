# Semicore 半导体 CRM MVP

本仓库交付 Vue 前端与 `rayher_crm` Frappe 后端。开发、构建和生产运行均连接 Frappe API，由 Frappe 会话、权限、DocType 和 MariaDB 提供正式持久化。

## 已实现

- 经营看板：Open/Weighted Pipeline、Confirmed Booking、漏斗、趋势、重点客户、行动、Demo 审批、验证与合同提醒。
- 客户档案：筛选列表与 Account 360 抽屉，聚合 Site、关键人、需求、商机、Demo / 验证、合同和行动。
- 采购需求：设备/应用、预算、完整度、负责人、Next Action 和关联业务。
- 商机与 Booking：独立金额口径、阶段、概率、意愿分和来源追溯。
- Demo Request：Sales 创建、修改、取消与提交，工程可行性评估、经理审批/驳回，以及批准后幂等生成 Evaluation。
- Demo / Wafer Test：五段式验证看板、受控状态推进、Hold 记录和带日期/数值边界校验的 Wafer Test Run 指标追踪。
- 合同管理：合同类型、签署状态、金额以及 30 / 60 / 90 天到期风险口径。
- 全局壳层：内存路由、响应式导航、角色上下文、统一请求状态和 `.semicrm-app` 样式隔离。
- 可靠性：列表搜索防抖与请求乱序保护、Account 360 身份守卫、权限/过期/部分数据提示、相对静态资源路径。

## 本地运行

需要 Node.js 22.12+（本项目验证环境为 Node 24）和 pnpm 11.9.0。

```bash
pnpm install --frozen-lockfile
pnpm dev
```

默认地址：`http://127.0.0.1:5173`

生产预览：

```bash
pnpm build
pnpm preview
```

## 质量检查

```bash
pnpm typecheck
pnpm test
pnpm build
```

## 数据运行模式

正式运行入口仅使用 Frappe：

- `pnpm dev` 与 `pnpm dev:lan` 固定使用 Frappe 开发模式。
- `pnpm build` 与 `pnpm build:frappe` 固定生成 Frappe 前端产物。
- `src/api/frappe-adapter.ts` 调用 `rayher_crm.api.v1` 接口。
- `backend/apps/rayher_crm` 包含 DocType、服务、权限、迁移与测试；数据由 Frappe/MariaDB 持久化。

Mock adapter 仅供单元测试注入隔离夹具，不存在开发或生产 Mock 模式开关，也不会进入 Frappe 构建产物。

## 设计与范围

- MVP 规格：`docs/superpowers/specs/2026-07-17-semiconductor-crm-mvp-design.md`
- 实施计划：`docs/superpowers/plans/2026-07-17-semiconductor-crm-mvp.md`
- 交付模块规格：`docs/superpowers/specs/2026-07-17-demo-evaluation-contract-design.md`
- 交付模块实施计划：`docs/superpowers/plans/2026-07-17-demo-evaluation-contract.md`
- 原始 HTML 原型和 Word 需求文档保持不变。
- 最终质量门：全部自动化测试、TypeScript 类型检查和生产构建均需通过。
