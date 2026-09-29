# Plan 前端验证（2026-09-18）

## 已完成

- `/plan` 正式页面及 Review → Plan 入口，复用 AppShell；没有修改 AppShell 或区域业务模块。
- 四项指标、日程按日期/销售/市场分组、明细分页、销售汇总、市场汇总及预计 PO 列表。
- 周/月/季/年、日期及销售/区域/市场筛选走自有 Plan 接口；无设备筛选或团队目标。
- 本地测试覆盖：不混合币种、周末和逾期原日期、筛选/下钻/分页、未来周期参数、角色限制、过期请求丢弃、接口失败重试、英文界面。
- `pnpm exec vitest run src/pages/PlanPage.test.ts src/pages/ReviewPage.test.ts src/api/frappe-adapter.test.ts src/i18n/template-coverage.test.ts src/app`：8 个测试文件、79 项通过。
- `pnpm exec vitest run`：全量 127 个测试文件、938 项通过。
- `pnpm run build`：通过（包含 vue-tsc 和 Frappe 模式生产构建）。
- 浏览器用真实 PlanPage + AppShell，注入仅本地使用的合成数据：1958×1102、1440×1000、390×844；中文、英文、空数据及接口失败状态已检查。
- 1958 宽度下：日程和市场卡片高 744px，中列上下各 364px；空数据不缩成小卡片。窄屏改为纵向布局，日程/表格内部滚动，未出现整页横向溢出。
- Test Run 链接使用现有 `/evaluations?focus=<evaluationId>`，确保定位到对应测试。

## 尚未完成

- Claude 的两个 Plan 读接口实现、业务计数口径确认及测试服 HTTP 联调。
- Planned Test Run 完成/改期/取消的闭环核验。
- 后端未接通时显示读取失败和重试，不回落到示例数字。
- 预览数据不是真实业务数据，不进入正式运行时。布局预览不代表服务器已部署。

本次前端改动不包含后端 schema/迁移或 Plan 聚合实现。合并与部署由 Claude 从保留区域模块的集成基线执行；不能用 Codex 分支覆盖现有发布版本。
