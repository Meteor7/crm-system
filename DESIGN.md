---
name: "栖衡 QIHENG CRM"
description: "浅色索引导航与靛蓝操作色组成的客户协作工作台。"
colors:
  primary: "#3159CE"
  primary-hover: "#2448B0"
  primary-soft: "#EAF0FF"
  page: "#F3F5FA"
  surface: "#ffffff"
  surface-muted: "#E9EDF5"
  heading: "#20324C"
  text: "#26364E"
  text-muted: "#59677D"
  line: "#DEE4EE"
  line-strong: "#C6D0DF"
  table-head: "#f5f7fb"
  nav-text: "#52617a"
  positive: "#3B9B64"
  warning: "#C58A18"
  danger: "#C84E4E"
  danger-soft: "#FFF0EF"
  badge-danger-ink: "#a63c3c"
  badge-danger-fill: "#fff0ef"
typography:
  headline:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.15
    letterSpacing: "-.02em"
  title:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "16px"
  body:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "13px"
  secondary:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "12px"
  label:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "11px"
  emphasis:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "14px"
  button:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "13px"
    fontWeight: 700
  navigation:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "12px"
    fontWeight: 500
  login-title:
    fontFamily: "\"Segoe UI\", \"Microsoft YaHei\", sans-serif"
    fontSize: "22px"
    fontWeight: 600
rounded:
  control: "8px"
  sm: "9px"
  md: "14px"
  lg: "14px"
  badge: "999px"
  login-field: "7px"
spacing:
  "1": "4px"
  "2": "7px"
  "3": "8px"
  "4": "10px"
  "5": "12px"
  "6": "14px"
  "7": "16px"
  "8": "18px"
  "9": "22px"
  "10": "28px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    typography: "{typography.button}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    typography: "{typography.button}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 13px"
    typography: "{typography.button}"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    rounded: "{rounded.sm}"
    padding: "0 13px"
    typography: "{typography.button}"
  input-filter:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "0 28px 0 10px"
    typography: "{typography.body}"
  nav-active:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.primary-hover}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    typography: "{typography.navigation}"
  badge-danger:
    backgroundColor: "{colors.badge-danger-fill}"
    textColor: "{colors.badge-danger-ink}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
    typography: "{typography.label}"
  section-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
---

# Design System: 栖衡 QIHENG CRM

## Overview

**Creative North Star: "研发记录册 / The R&D Notebook"**

栖衡 QIHENG 是本次重塑选定的虚构品牌。研发记录册的索引、对齐与信息密度转译为浅色侧栏、分组导航、清晰标题和可扫描的业务记录；隐喻不画成纸张、工具或其他装饰物。

本规范记录已实现的界面，延续真实业务流程、权限与路由。颜色、排版和组件以源码及桌面、移动、登录截图为依据；方向种子为 41963e97。

**Key Characteristics:**

- 浅色导航与冷纸白工作区。
- 靛蓝识别当前模块、链接与主要操作。
- 细边框分区，数字等宽对齐，业务表格保持密度。

## Colors

### Primary

靛蓝 primary 用于主要操作与链接；primary-hover 提供加深状态，primary-soft 标出导航和轻量强调。

### Secondary

positive、warning、danger 只承担业务状态。风险徽标另有浅底深字配对，不能把全局 danger 直接当作徽标前景。

### Neutral

page 承托白色 surface；heading、text、text-muted 区分标题、正文与辅助说明。line 和 line-strong 用于记录与控件边界。

**The Record Rule.** 颜色用于定位、状态与操作，状态同时保留文字。

## Typography

界面使用系统无衬线栈；标准内容区正文、次要文字、标签、强调与章节标题分别对应 frontmatter 中的 body、secondary、label、emphasis、title。页面标题对应 headline。数字采用 tabular-nums。

标准层级来自 `src/design-system/typography.css`，品牌文件更新其中四个变量。`/demo-workflow`、`/demo-requests`、`/evaluations` 不进入该标准作用域，保留组件自己的字号；导航和登录也有独立层级。通用应用基础字号为（14px），通用按钮基础字号为（10px），进入标准内容区后按钮为 body 大小。

**The Scope Rule.** 先确认组件所在作用域，再应用令牌；品牌样式不意味着每个局部尺寸都被覆盖。

## Layout

桌面索引侧栏宽（240px），顶栏高（64px），主内容最大宽（1600px），内边距（28px）。侧栏可以收起。页面标题与操作区分组，操作可以换行。

视口不大于（839px）时使用抽屉菜单，内容内边距为（18px 14px）；页面标题组件不大于（700px）时纵向排列。部分显式响应式表格在（839px）以下转为标签记录卡；客户表格等保留横向滚动，不强行把所有表格转成卡片。登录卡片在（480px）以下缩减内边距。

## Elevation & Depth

主操作按钮在品牌层去掉阴影和悬浮位移；白色表面、冷色底与细线承担主要分层。SectionCard 保留极轻阴影（0 1px 1px rgba(31,35,41,.02)）。通知浮层使用（0 18px 48px rgba(25, 43, 52, .16)），不作为普通卡片默认阴影。

状态过渡主要为（180ms ease），侧栏移动为（220ms ease）。减少动态效果时过渡和动画缩短至（0.01ms）。

## Shapes

通用主操作与导航采用 control 圆角；次要和危险按钮沿用 sm，SectionCard 使用 md，状态徽标使用胶囊轮廓。登录面板仍是 md 圆角，登录字段和按钮为 login-field。局部客户 KPI 为（11px）；不要从单一面板推导全局圆角。

## Components

### Buttons

主要、次要和危险操作共用最小高度（36px），主要操作为白字靛蓝底。主要悬停加深且不位移；次要悬停为浅蓝底与强调边框；危险按钮使用浅底风险色。禁用态保留禁用光标。

### Inputs / Fields

通用筛选控件高（34px），白底细线。品牌焦点为（2px）实色外框、偏移（3px）；局部密码输入仍有自己的焦点描边与轻光圈。

### Navigation

导航行最小高（40px），默认深灰蓝文字，选中为浅靛蓝底、深靛蓝文字及加粗标签。图标用于模块识别；折叠与移动菜单行为沿用应用壳。

### Chips

StatusBadge 使用文字、可选圆点和浅底描边。标准内容区采用 label 字号，其余上下文基础字号（10px）；危险徽标配对见 frontmatter。

### Cards / Containers

SectionCard 使用白底、细边框；头部内边距（19px 20px 14px），主体（6px 20px 20px）；flush 主体无内边距。客户 KPI 辅助说明使用 text-muted，保持可读。

### Brand and Login

`public/brand/qiheng-logo.svg` 与 `qiheng-icon.svg` 为应用资产；原生登录由 `backend/apps/rayher_crm/rayher_crm/public/css/qiheng-login.css` 控制，独立于 Vue 令牌作用域。登录按钮最小高（40px），输入最小高（42px），面板内边距（32px）；Frappe 局部样式仍可能控制字段内部表面。

依据：`src/design-system/tokens.css`、`base.css`、`typography.css`、`qiheng.css`、`src/app/AppShell.vue` 与所述组件。侧车示例保留 CSS 变量并提供实际值回退，可独立渲染。

侧车色带是用于预览的合成 OKLCH 明度梯度，不新增源码颜色令牌。

## Do's and Don'ts

### Do:

- Do 复用栖衡 SVG 字标与图标，保持其比例和应用入口一致。
- Do 在标准内容区采用正文、次要文字与说明标签的现有层级；客户 KPI 辅助说明使用 text-muted。
- Do 保留移动菜单、键盘焦点、表格独立滚动和减少动态效果偏好。

### Don't:

- Don't 将方向稿中的圆角概念覆盖到所有组件；以本文件与实际局部样式为准。
- Don't 把研发记录册画成装饰性物件，或恢复旧品牌字标与页头装饰。
- Don't 用统一强调色取代风险、成功和警告的文字语义，或为视觉重塑改动业务流程。
