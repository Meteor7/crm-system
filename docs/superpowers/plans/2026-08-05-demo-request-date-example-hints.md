# Demo Request Date And Example Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Demo Request 新增/编辑共享表单的 Timing 改为日历日期选择，并把指定文本字段的灰色提示统一为已批准的 `e.g. ` 示例。

**Architecture:** 继续由 `DEMO_REQUEST_HINTS` 集中维护提示文案，表单组件只引用提示常量。`timing` 仍绑定原有字符串字段和提交 payload，只把浏览器控件改为 `input[type="date"]`，不修改 API、后端或数据库。

**Tech Stack:** Vue 3、TypeScript、Vitest、Vue Test Utils、Vite、Frappe production build

## Global Constraints

- 仅修改 Demo Request 新增与编辑共用表单。
- 文本输入与文本域提示使用规格中已批准、以 `e.g. ` 开头的原文。
- 下拉框继续使用选择提示，不添加 `e.g.`。
- 必填标记、前后端校验、字段名、API payload 和数据库结构保持不变。
- 按用户要求不采用 TDD：先实施，再运行聚焦测试与构建验证。
- 不 commit，不 reset，不 stash，不 clean。

---

### Task 1: 更新提示文案与 Timing 日期控件

**Files:**
- Modify: `src/domain/demo-request-form.ts`
- Modify: `src/features/demo-requests/DemoRequestForm.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.test.ts`

**Interfaces:**
- Consumes: `DEMO_REQUEST_HINTS` 只读提示常量、`DemoRequestFormData.timing: string`
- Produces: 指定字段的精确 `e.g. ` placeholder，以及提交 `YYYY-MM-DD` 字符串的 `input[type="date"]`

- [x] **Step 1: 替换集中提示文案**

  在 `DEMO_REQUEST_HINTS` 中保留选择控件提示，按设计规格逐项替换 Industry、Size & Shape、Material、Specific Request、Detect、Expected、Other Tools、Primary Tool、Complementary Tool、Key Success、Internal Questions、Customer Questions 和六个 Wafer Details 字段的字符串。

- [x] **Step 2: 将 Timing 改为日期控件**

  将共享表单的 Timing 输入改为：

  ```vue
  <input name="timing" type="date" :value="draft.timing" @input="setField('timing', $event)" />
  ```

  保留字段名、双向更新路径、错误显示和 RequiredMark。

- [x] **Step 3: 更新现有聚焦测试**

  在 `DemoRequestForm.test.ts` 中断言所有目标提示都以 `e.g. ` 开头，并精确覆盖代表性字段；断言 Timing 的 `type` 为 `date`，设置 `2026-08-20` 后仍通过现有更新事件传递该字符串。保留 Wafer 计数、owner 选项和提交校验测试。

- [x] **Step 4: 运行聚焦验证**

  Run: `pnpm.cmd test -- src/features/demo-requests/DemoRequestForm.test.ts src/domain/demo-request-form.test.ts`

  Expected: 两个测试文件全部通过。

- [x] **Step 5: 运行生产构建**

  Run: `pnpm.cmd run build:frappe`

  Expected: TypeScript 检查和 Frappe 模式 Vite 构建成功。

- [x] **Step 6: 刷新本地 Docker 服务并检查健康状态**

  Run: `docker compose -p rayher-crm-stage1-local -f backend/compose.yaml up -d --build frontend`

  Run: `docker compose -p rayher-crm-stage1-local -f backend/compose.yaml ps`

  Expected: 本地服务保持运行且健康；不停止或删除 volumes。
