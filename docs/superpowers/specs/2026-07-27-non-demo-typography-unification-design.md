# 非 Demo 页面全局字号统一设计

## 目标

统一桌面端 CRM 非 Demo 页面中的字体层级和最小可读字号，消除当前同类内容在 `6px` 至 `10px` 之间无规则混用的问题，同时保持 Demo 板块现有视觉完全不变。

## Demo 排除范围

以下路由及其页面内部组件不应用本次排版规则：

- `/demo-workflow`：Demo 档案
- `/demo-requests`：Demo Request
- `/evaluations`：Demo Test

共享侧边栏和顶部栏属于系统框架，不属于 Demo 页面内容，可使用统一后的系统字号。

## 适用页面

- 信息中心
- Calendar
- 客户档案
- Opportunities & Booking
- 拜访与 Action
- Stakeholders
- Requirements
- Contracts
- Installed Tools
- Document Center

## 字号体系

桌面端统一使用以下语义层级：

| 层级 | 字号 | 适用内容 |
| --- | ---: | --- |
| Caption | `10px` | 状态、时间、眉题、表格列头、辅助标记 |
| Secondary | `11px` | 次要说明、卡片辅助信息、脚注 |
| Body | `12px` | 正文、表格内容、输入控件、按钮 |
| Emphasis | `13px` | 重点标签、列表主信息 |
| Section title | `15–16px` | 卡片和区块标题 |
| Page description | `13px` | 页面标题下方说明 |
| Page title | `28–34px` | 页面一级标题 |

金额、统计数字和其他展示型数值可继续使用现有大字号，不强制压缩到正文层级。

## 实现方式

- 在 `AppShell` 根据当前路由为主内容区添加“标准排版”或“Demo 排除”状态。
- 通过非 Demo 路由专用 CSS 变量和选择器统一共享组件、表格、筛选器、按钮、表单与页面常用文字。
- 对仍被页面局部高优先级样式覆盖的非 Demo 元素做少量定点修正。
- 信息中心现有已放大的可读字号作为下限，不回退。
- 非 Demo 图表坐标、图例和数据标签的最小字号统一到 `10px`。
- 不新增字体或依赖，不改变颜色、间距、布局结构和业务行为。

## 桌面端边界

- 本次以桌面端为验收目标。
- 不专门重做移动端布局；移动端继续继承现有响应式规则。
- 不使用整体缩放、浏览器 `zoom` 或元素 `transform: scale()` 模拟字号变化。

## 验收标准

- 非 Demo 页面不再出现 `6px`、`7px`、`8px` 的可见正文或辅助文字。
- 同类页面标题、卡片标题、正文、说明、表格和控件字号一致。
- 信息中心现有字号不缩小。
- Demo 档案、Demo Request、Demo Test 的主要内容计算字号与修改前一致。
- 页面布局不发生明显溢出、遮挡或文本截断回归。
- 当前 `4173` 页面至少检查信息中心、客户档案、拜访与 Action、Installed Tools、Document Center 和三个 Demo 页面。
- 相关测试、类型检查和生产构建通过。
- 浏览器控制台无错误。
