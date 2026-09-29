# Review 测试服务器部署交接

## 2026-09-18：Plan 前端增量

本分支新增 `/plan` 页面和 Review 的 Plan 入口。Plan 调用 `get_plan / get_plan_details`，**这两个后端接口尚未实现，不能视作联调完成**。请先阅读 [Plan 后端交接](../plan/backend-handoff.md) 和 [前端验证](../plan/validation.md)，在保留区域模块的集成分支补齐接口后统一联调。没有新增报价计划字段或团队目标。

## 本次正式 UI 合入交接

- `63c7c34` 的视觉标准已做进 `src/pages/ReviewPage.vue`；正式路由继续由现有 `AppShell` 承载，复用其导航、身份、角色、语言与账户功能。
- Review 接 `get_review / get_details / save_target`。个人图表可独立选择销售，沿用当前期间、区域与市场；区域/市场筛选下不拆分个人目标。
- 销售表末列为 PO 年累计数量；丢单响应新增历史事件时点的估算金额与币种，缺可信字段历史则为空。实际订单金额自 2026-09-18 起按订单人民币金额计算，见下文。
- 用户告知区域模块仅存在于测试服发布版本 `119b9fc`，未推 GitHub；此版本信息未由 Codex 进行站点核验。本分支不包含该发布版本，不能直接用本分支整体覆盖测试服代码。Claude 从保留 `119b9fc` 区域功能的集成基线合入本分支，解决冲突后重新构建验证。
- 区域选项显示接口原文，不做中文映射；Claude 合并时接区域中文标签。现有 regionReady 门控不变，不在此分支添加/迁移区域字段。
- GitHub 基线与服务器发布版本不是同一回事。下面的迁移步骤按实际集成结果核对，不重复执行已经确认完成的迁移。

## 获取代码

- 仓库：`kizzhang/PlanckSemicon_CRM`
- 分支：`codex/review-cockpit`
- PR 基分支：`feat/probability-level-rules`（#36）
- 已包含 #36 的 `5c5f27d`，以及其依赖的 #35 和 PR #16 修复；不用重复 cherry-pick 这些提交。
- 本分支新增 Review 页面、三个自有 cockpit 接口及个人目标表；没有团队目标。
- Codex 负责提交与推送，测试服务器部署由 Claude 统一执行。本交接不代表已经部署。

在干净的独立工作区获取：

```sh
git fetch origin codex/review-cockpit
git worktree add -b integration/review-staging ../review-staging origin/codex/review-cockpit
git -C ../review-staging rev-parse HEAD
```

如果 Claude 另有未包含的模块，先在集成分支合并并验证。不要覆盖已有未提交改动。部署时记录最终集成提交号。

## 部署顺序

1. 确认测试服务器当前实际版本、站点名和部署目录，并备份数据库及文件。先在数据库副本演练 #35 七阶段迁移，保留迁移结果和数据缺口记录。
2. 按仓库现有部署流程构建和打包前后端。前端使用 `pnpm run build:frappe`，将生成的资源随 backend app 打包，不能只替换前端页面。
3. 在部署容器或 bench 环境内对实际站点执行 `bench --site <site> migrate`。必须同步 #36 的 `CRM Opportunity Probability History.reason` 和本分支 `CRM Cockpit Target` DocType。随后按现有流程清缓存并重启相关服务。
4. 在迁移后的隔离测试站点运行以下模块（替换 `<rehearsal-site>`，不要在共享业务数据上开启测试或运行测试夹具）：

```sh
bench --site <rehearsal-site> run-tests --app rayher_crm --module rayher_crm.tests.test_cockpit_api
bench --site <rehearsal-site> run-tests --app rayher_crm --module rayher_crm.tests.test_cockpit_metrics
bench --site <rehearsal-site> run-tests --app rayher_crm --module rayher_crm.tests.test_stage5g_dashboard_stakeholders
```

同时执行 #35/#36 原有迁移、概率和业务流程验证。

## 必须保留的数据口径

- 复用发布版本中的区域模块，并核对存量映射及核验结果；未确认前区域筛选保持禁用。完成核验后才可设置 `crm_cockpit_region_migration_verified=true`。来源必须是客户主档区域。
- `crm_cockpit_history_complete_from` 是按 `stage / fields / actions / probability` 分别记录的可信起点映射。只有部署、迁移和实际写入路径能证明完整的范围才填写；默认不填，相关总数显示数据不足。不能用最早历史行或 Git 提交日期代替证据。
- 降档原因历史旧行允许缺失，显示未记录原因；新降档由 #36 的商机更新接口强制填写 `probabilityReason`。
- Lead 活动按转化时间；S7 YTD 按当前 Confirmed / Completed、source=Opportunity 的 Booking 实际 PO 日期归年，归属当前商机负责人。缺日期单列待补录，不按年份筛选；取消或回退会移出年累计。旧的 po 历史覆盖配置不再参与判断。
- 订单实际金额按 Booking 的人民币金额计算：人民币订单取 amount，外币订单取 amount_cny（Claude `5c44a82`）；缺人民币金额的订单单列待补录，补齐前年累计金额显示数据不足。不要填入估算金额冒充实际。

## 页面与真实接口验收

- Manager 登录后打开 `/crm` 内的 Review（前端路由 `/dashboard`），确认页面、期间切换和明细加载。
- 浏览器数据调用只走 `rayher_crm.api.v1.cockpit.get_review / get_details / save_target`，不使用 Frappe 通用资源或 client 接口。
- Sales/Engineer 看不到 Review，直接请求 cockpit 接口和旧 dashboard 聚合接口也应被拒绝。
- 用授权商机负责人降档并填写原因，Review 明细展示同一原因；首次设档不算降档。
- 在完整性未确认的历史区间显示数据不足；区域未核验时禁用；无团队目标。
- 验证个人目标保存、刷新回读、过期版本冲突、未来周默认值，以及区域/市场筛选下目标不适用。
- 确认浏览器无接口或控制台错误，再记录部署提交、迁移结果、真实角色验收及剩余数据限制。

本地验证记录见 [validation.md](validation.md)，接口和本期范围见 [implementation-contract.md](implementation-contract.md)。数据库联调和浏览器视觉验收仍需部署阶段完成。

## 2026-09-18 实际 PO 日期增量

Claude 的 `7d48bc2`（接在 `35259c0` 后）提供 actual_po_date 及维护流程。本分支仅接入 Review 统计与明细，不复制这些业务变更。合并需保留区域翻译。请先合入并 migrate Claude 的字段，再部署本次增量；旧后端缺字段时 S7 与待补录显示数据不足。部署验收步骤见 [actual-po-date-integration.md](actual-po-date-integration.md)。

## 2026-09-18 人民币金额增量

Claude 的 `5543485` 提供商机人民币金额及补填迁移，本分支已接入 Review 的阶段、销售 Pipeline、停滞和丢单金额。合并时保留该字段、迁移和区域模块；先在副本运行金额迁移，再执行联调。已有 PO 日期统计 `e7c7b30` 同时保留。业务口径、缺值、历史回放及测试清单见 [cny-amount-integration.md](cny-amount-integration.md)。旧 schema 缺金额列时显示数据不足。
