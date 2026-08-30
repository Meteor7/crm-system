# RAYHER Salesforce 壳层视觉优化 Implementation Plan

> **状态：已取消。** 不执行 Salesforce 配色；最终只实现原型 RAYHER 三色图形与 `RAYHER` 主名称，保留“客户经营系统”副标题、原配色和页面结构。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在完全保留当前 CRM 页面结构和业务行为的前提下，将品牌替换为 RAYHER，并应用 Salesforce 深蓝、亮蓝、冷灰和白色容器视觉语言。

**Architecture:** 品牌结构和壳层交互样式集中修改 `AppShell.vue`，全局颜色、边框和阴影集中修改设计令牌与基础样式。业务页面、路由、权限、API、图表数据和导航结构保持不变。

**Tech Stack:** Vue 3、TypeScript、Scoped CSS、设计令牌、Vitest、Vue Test Utils

## Global Constraints

- 保留当前固定左侧导航、浅色顶部栏和全部业务页面布局。
- 品牌主字标为 `RAYHER`，副标题为 `SEMICONDUCTOR CRM`。
- 使用 `#032D60`、`#0176D3`、`#1B96FF` 和 `#F3F5F7` 作为壳层视觉色。
- 不新增顶部对象标签栏，不移动导航入口，不新增图片、字体或第三方依赖。
- 只运行 AppShell、设计令牌和本轮受影响页面的定向验证。

---

### Task 1: RAYHER 品牌身份

**Files:**
- Modify: `src/app/AppShell.vue`
- Modify: `src/app/AppShell.test.ts`
- Modify: `index.html`

**Interfaces:**
- Produces: `data-testid="rayher-mark"`、`data-testid="brand-name"`、`data-testid="brand-subtitle"`
- Preserves: 现有 AppShell props、路由、搜索、权限和移动导航接口

- [ ] **Step 1: Write the failing test**

```ts
it('uses the approved RAYHER identity from the prototype', async () => {
  const router = createAppRouter()
  await router.push('/dashboard')
  await router.isReady()
  const wrapper = mount(AppShell, {
    global: { plugins: [createPinia(), router], stubs: { CrmChart: { template: '<div />' } } },
  })

  expect(wrapper.get('[data-testid="brand-name"]').text()).toBe('RAYHER')
  expect(wrapper.get('[data-testid="brand-subtitle"]').text()).toBe('SEMICONDUCTOR CRM')
  expect(wrapper.get('[data-testid="rayher-mark"]').findAll('i')).toHaveLength(3)
  expect(wrapper.text()).not.toContain('SEMICORE')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/app/AppShell.test.ts`

Expected: FAIL because the current shell still renders `SEMICORE` and has no RAYHER test IDs.

- [ ] **Step 3: Write minimal implementation**

Replace the CPU icon block with:

```vue
<span class="brand-mark" data-testid="rayher-mark" aria-hidden="true"><i /><i /><i /></span>
<div>
  <strong data-testid="brand-name">RAYHER</strong>
  <span data-testid="brand-subtitle">SEMICONDUCTOR CRM</span>
</div>
```

Remove the unused `Cpu` import and style the three tiles with the prototype lime, teal, and pale colors. Change `index.html` title to `Rayher Semiconductor CRM · 客户经营`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/app/AppShell.test.ts`

Expected: all AppShell tests PASS.

### Task 2: Salesforce 配色和壳层层级

**Files:**
- Modify: `src/design-system/tokens.css`
- Modify: `src/design-system/tokens.test.ts`
- Modify: `src/design-system/base.css`
- Modify: `src/design-system/SectionCard.vue`
- Modify: `src/app/AppShell.vue`

**Interfaces:**
- Produces: `--crm-action`、`--crm-action-active`、更新后的 `--crm-navy-strong`、`--crm-surface`、`--crm-line` 和 `--crm-shadow`
- Preserves: 所有现有令牌名称和组件 props

- [ ] **Step 1: Write the failing token test**

```ts
expect(css).toContain('--crm-navy-strong: #032D60')
expect(css).toContain('--crm-action: #0176D3')
expect(css).toContain('--crm-action-active: #1B96FF')
expect(css).toContain('--crm-surface: #F3F5F7')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/design-system/tokens.test.ts`

Expected: FAIL because the Salesforce shell tokens do not exist yet.

- [ ] **Step 3: Implement the approved shell styling**

Update tokens to the approved palette, then use them in the existing shell:

```css
--crm-navy-strong: #032D60;
--crm-action: #0176D3;
--crm-action-active: #1B96FF;
--crm-surface: #F3F5F7;
--crm-line: #c9d4df;
--crm-shadow: 0 1px 3px rgba(3,45,96,.06), 0 10px 28px rgba(3,45,96,.07);
```

Use Global Navy for the existing sidebar, Salesforce Blue for navigation hover/focus and Active Blue for the active indicator. Keep the existing topbar layout but give it a white translucent surface, subtle border and shadow. Use the action token for global buttons and focus treatment. Apply the shared shadow token to `SectionCard` without changing its markup or slots.

- [ ] **Step 4: Run focused tests**

Run: `pnpm test src/design-system/tokens.test.ts src/app/AppShell.test.ts`

Expected: all selected tests PASS.

### Task 3: Targeted verification

**Files:**
- Verify only; no planned production changes

- [ ] **Step 1: Run type check**

Run: `pnpm typecheck`

Expected: exit code 0.

- [ ] **Step 2: Run production build**

Run: `pnpm build`

Expected: exit code 0 with updated AppShell and design-system assets.

- [ ] **Step 3: Browser verification**

Open `http://127.0.0.1:4173/dashboard` and verify RAYHER branding, unchanged navigation structure, Salesforce palette, desktop layout, mobile navigation and zero console errors.
