# Claude 继续开发交接：Opportunities 看板与设备型号

核对日期：2026-09-22。本文区分当前事实与后续建议；不是已批准的型号迁移设计。

## 1. 先到正确的工作树

最新前后端合并工作树：
C:/Users/PlanckSemicon/Desktop/CRM-opportunity-board-frontend

分支：codex/opportunity-board-frontend
HEAD：695f0c5（后端提交）
基线：origin/codex/plan-integration @ b7cf8ee

Claude 原后端工作树：
C:/Users/PlanckSemicon/Desktop/CRM-opportunity-board
分支：feat/opportunity-board-api

关键：
- 最新前端源文件及 UI 对齐改动在 frontend 工作树中，包含未跟踪的新文件；尚未 git commit。
- 仅 checkout 到同名分支或读取 HEAD，看不到这些未提交改动。请直接进入上述 frontend 工作树，先检查 git status。
- frontend 分支已包含后端 695f0c5，不要重复 cherry-pick。
- 当前没有推送、没有创建 PR、没有打发布包。用户要求先本地开发验收，等通知再处理发布。
- 不要 reset/clean/stash 或覆盖已有前端改动；本次交接没有替你执行这些操作。
- 原任务目录 Desktop/testpr3 不是本次功能工作树，不要把它当作最新看板源码目录。
- frontend/node_modules 当前是指向 Desktop/testpr3/node_modules 的本地 junction；没有新依赖或 lockfile 变更。

## 2. 优先阅读的文档

以下路径均相对 frontend 工作树：
- docs/opportunity-board/backend-handoff.md：后端权威契约、校验、权限、迁移及接口边界。
- docs/opportunity-board/api-sample.json：15 组真实 HTTP 请求/响应样例。
- docs/opportunity-board/frontend-handoff.md：前端实现、联调记录和导出边界。
- 本文：设备字段事实、代码导航、继续开发注意点。

不要把样例中的设备名称或原 demo 图里的设备列表当作正式产品目录。

## 3. 用户已明确的要求

- Opportunities 看板由 Codex 实现前端，Claude 已完成后端五个接口。
- UI 必须和现有 Plan / Review 风格统一，已经按这个要求修正。
- 先完成本地开发，提交 PR 和打包上线需等用户通知。
- 最近讨论焦点：设备型号仍为自由字段，当前筛选统计会按不同文本拆开。
- 用户尚未提供标准型号清单，也尚未确认历史数据自动合并规则、型号主数据管理权限或新增接口契约。不要把下文建议当作这些事项已经确定。

## 4. 已完成的看板功能

入口：
- 路由 /opportunity-board；Frappe 模式 #/opportunity-board。
- Review、Plan、现有 Opportunities 商机列表已增加跳转入口。
- 原商机列表及业务编辑保留。

功能：
- 区域、销售、设备、市场范围多选；选项支持关键词搜索。
- 平铺 AND / OR 条件；最多 20 条；300 ms 防抖。
- Demo 完成、Demo 超过 21 天、Committed 待 PO、S6 待 PO 快捷查询。
- 全部结果汇总、概率档位汇总、缺失金额及阶段日期提示。
- 后端排序、分页、六个字段分组、显示列选择。
- 个人保存查询的列表、新增、更新、重命名、删除。
- 更新/删除携带 expectedModified；处理版本冲突；查询名称纯文本渲染。
- Excel 全量导出，使用当前筛选及列，分组时每组一个工作表。
- 中英文、错误/空态、身份变化清空数据、过期请求丢弃。
- Engineer 可按 deal:view 直接进入看板；沿用原系统隐藏 Sales 导航的规则，因此不显示不可达的商机详情/列表链接。

UI：
- 使用现有 crm 设计变量。
- 暖色渐变页头、官方品牌水印、深色活动页签、橙色按钮选中态。
- 页签与范围筛选同一控制区域；标题、圆角、表格、边框和留白参照 Plan / Review。
- 未引入新设计依赖。

## 5. 前端代码位置

| 文件 | 作用 |
|---|---|
| src/pages/OpportunityBoardPage.vue | 主页面、调用接口、查询状态、权限、保存查询弹窗、排序分页和导出 |
| src/features/opportunity-board/board.css | 看板样式及容器响应式规则 |
| src/features/opportunity-board/types.ts | BoardField/Query/Filters/Row/Definition/SavedBoardQuery 类型 |
| src/features/opportunity-board/model.ts | 条件字段/运算符、默认列、快捷查询、前端校验、显示格式 |
| src/features/opportunity-board/BoardMultiSelect.vue | 搜索、多选、清空、点击外部关闭；保留已选但当前选项缺失的值以便移除 |
| src/features/opportunity-board/BoardConditionRow.vue | 字段/运算符/值编辑，按类型切换控件 |
| src/features/opportunity-board/export.ts | 分页拉取完整结果、变化检测、按组生成工作表 |
| src/features/opportunity-board/fixtures.ts | 从真实 HTTP 样例构建测试数据；仅用于测试 |
| src/api/contracts.ts:180 | CrmApi 五个方法声明 |
| src/api/frappe-adapter.ts:13、388 | 后端方法名映射和请求实现 |
| src/api/mock-adapter.ts | 测试适配器保留接口；默认看板方法明确返回未连接后端，测试按需注入样例 |
| src/app/router.ts:33 | 看板路由及导航归属 |
| src/app/AppShell.vue:74 | 初始路由未解析时不跳转；允许有 deal:view 的账号进入看板 |
| src/features/opportunities/OpportunityListView.vue:177 | 原商机列表中的新看板入口 |
| src/pages/ReviewPage.vue:226 | Review 页签入口 |
| src/pages/PlanPage.vue:132 | Plan 页签入口 |

设计参照：
- src/features/cockpit/plan.css
- src/pages/ReviewPage.vue 的 scoped style
- src/features/cockpit/sales-table.css
- src/design-system/tokens.css

行号为交接时参考，后续请用函数名/字段名定位。

## 6. 后端代码与五个接口

后端应用根目录：
backend/apps/rayher_crm/rayher_crm/

所有接口前缀：
/api/method/rayher_crm.api.v1.cockpit.

| 接口 | 方法 | 前端方法 |
|---|---|---|
| query_opportunities | POST | queryOpportunities |
| get_opportunity_filters | GET | getOpportunityFilters |
| list_opportunity_queries | GET | listOpportunityQueries |
| save_opportunity_query | POST | saveOpportunityQuery |
| delete_opportunity_query | POST | deleteOpportunityQuery |

代码：
- api/v1/cockpit.py:42–68：五个入口。
- services/opportunity_board.py：权限范围、数据库读取、设备选项、保存查询 CRUD。
- services/opportunity_board_rules.py：输入校验、条件匹配、DTO、排序、分组、汇总。
- rayher_crm/doctype/crm_opportunity_saved_query/：个人查询 DocType。
- permissions/scope.py：商机行级权限来源。
- permissions/roles.py：deal:view 等能力权限。

契约重点：
- POST 沿用现有 form 编码，对象参数 JSON 序列化，携带 CSRF。
- 查询返回 items/asOf/summary/groups，分页 total/page/pageSize 在 meta。
- 保存定义包含 scope/match/conditions/sort/groupBy/columns，不保存 page/pageSize。
- 保存查询属于当前用户，不能通过 Frappe 通用读写接口绕过。
- 本次后端迁移只新增 CRM Opportunity Saved Query，bench migrate，无已有表改动或数据补丁。

## 7. 设备型号的当前事实（重点）

### 7.1 录入仍是自由文本

数据库字段：
backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_opportunity/crm_opportunity.json:22
tool_type 的 fieldtype 为 Data，reqd 为 1；不是 Link 或标准选项 Select。

前端编辑器：
src/features/opportunities/OpportunityEditorModal.vue
- :48 初始化 form.toolType。
- :127 toolTypeInput 的显示/输入本地化处理。
- :177 普通 input，required，用户自行填写。

后端写入：
backend/apps/rayher_crm/rayher_crm/services/opportunities.py
- _validate_opportunity，约 :137。
- :167 通过 required_text(payload, "toolType") 写入 tool_type。
- serialize_opportunity，约 :350，返回 toolType。
- create_strategy_opportunity，约 :484。
- update_strategy_opportunity，约 :545。
- services/common.py:73 的 required_text 要求非空字符串，并 strip 首尾空白。
这条链路没有把型号校验为标准产品目录中的 ID。

字段对应：
商机编辑/详情 DTO toolType
→ CRM Opportunity.tool_type
→ 看板 DTO equipment

### 7.2 看板选项如何生成

services/opportunity_board.py：
- :82 _board_context。
- 先应用 conditions_for_doctype("CRM Opportunity") 的用户权限范围。
- :100 从用户可读商机的 tool_type 提取值，去掉首尾空白，过滤空值，用集合去重。
- 名称排序使用 casefold，但集合去重没有统一大小写。
- :119 返回 equipment: [{value: 名称, label: 名称}]。

所以这是“权限范围内已有商机出现过的型号”，不是完整产品目录。
范围选项不是随着当前其他查询条件联动收窄的级联目录，而是基于用户可读商机生成。

### 7.3 匹配、搜索和分组

services/opportunity_board_rules.py：
- :188 _allowed_values：设备自由文本不强制校验是否在当前下拉选项中。
- :344 _clean：去首尾空白，空值转 None。
- :402 将 tool_type 映射到行 DTO 的 equipment。
- :435/438：in / not_in 是字符串精确集合匹配，区分大小写。
- :459 _matcher：范围条件与条件区组合，范围限制始终生效。
- :531 build_board：按实际 equipment 文本分桶，统计数量及人民币金额。

前端 BoardMultiSelect.vue 的搜索不区分大小写，只用于找选项；不会更改后端匹配语义。
同一多选框的多个值是“任一所选值”；不同范围字段共同限制结果。
条件区可选择 AND 或 OR，不能绕过顶部范围和用户权限。

具体结果：
- Nansi 与首尾带空白的 Nansi → 同一值。
- Nansi、NANSI、Nansi设备 → 三个不同值、三个不同组。
- 中间空格、型号别名、拼写错误不会自动合并。
- 历史空设备值不进入下拉选项；分组时归“未填写”；排除某型号的 not_in 会保留空值行。
- 设备筛选没有 contains 模糊匹配运算符。
- 保存查询目前保存设备名称字符串。后续把名称换成 ID 时，必须考虑旧保存查询的兼容性。

## 8. 设备标准化可能影响的位置

这里是后续评估建议，当前尚未实施标准型号迁移。

至少检查：
1. 商机新建和编辑：OpportunityEditorModal.vue。
2. 商机写入与返回：services/opportunities.py。
3. 看板设备选项、筛选、分组、排序与导出：opportunity_board.py / opportunity_board_rules.py 及前端对应模型。
4. 商机列表/详情：src/pages/OpportunityDetailPage.vue:492，原有 toolType 显示逻辑。
5. Booking 预填：src/features/opportunities/booking-draft.ts:30 会从 opportunity.toolType 复制 equipment。
6. 已保存查询：设备名称字符串的历史定义。
7. 客户关联商机、导入或线索转商机等其他写入入口：修改前搜索 tool_type/toolType，避免只修编辑器。

已有 Installed Tools 是另一条实体设备业务链路，不能直接视为标准型号目录：
- api/v1/installed_tools.py
- services/installed_tools.py（model 字段及 Booking 转设备）
- rayher_crm/doctype/crm_installed_tool/crm_installed_tool.json

尚未做全项目设备主数据盘点，不能仅凭该模块名称认定存在或不存在可复用的完整产品目录。

若用户后续确认做标准化，建议按此顺序：
- 先确认标准型号清单、稳定标识与允许的历史别名。
- 盘点现有 tool_type 的不同写法及数量，形成映射表；有歧义的值保留待确认。
- 设计最小型号选项来源及服务端校验；前端新建/编辑使用同一来源。
- 明确旧字段、旧客户端、旧保存查询及 Booking 的兼容处理。
- 迁移前准备可审核的数据变更明细，不擅自覆盖生产历史型号。
- 增加大小写/别名/未知值/权限范围/已停用型号/旧保存查询的回归。

## 9. 本地环境

本次实际联调：
- Docker compose 项目名前缀：rayher-crm-stage1-tests-board
- 后端容器：rayher-crm-stage1-tests-board-backend-1
- Web 容器：rayher-crm-stage1-tests-board-frontend-1
- Web 端口：127.0.0.1:2231
- 测试站点：rayher-crm.test
- sites 为命名卷：rayher-crm-stage1-tests-board_sites
- 容器内 sites 路径：/home/frappe/frappe-bench/sites

前端临时开发预览：
http://127.0.0.1:4177/assets/rayher_crm/crm/#/opportunity-board

预览使用 Vite frappe 模式及仅监听 127.0.0.1 的临时 API 代理，代理连接上述本地测试站点，测试账号会话只在进程内存中。
不是生产入口，没有把账号、密码、Cookie 写进源码或本文。
该预览是临时运行进程；进程退出后需重新建立本地代理，不要假设 npm dev 单独启动就自动获得这个会话。
修改后端源码后，需核对容器实际加载的应用版本；不要假设 Windows 工作树改动会自动映射到现有测试容器。

现有环境启动/测试入口：
- backend/compose.yaml
- backend/tests/run-backend-tests.ps1
- backend/tests/compose-contract.ps1
使用前阅读脚本参数，保持 board 测试环境隔离；机器上另有其他 CRM 环境，不要重置它们。

## 10. 测试与验收状态

前端：
- 全量 135 个测试文件、1011 个用例通过（UI 对齐前的完整运行）。
- 后续原币金额不可排序及导出修正相关 20 个用例通过。
- UI 对齐后页面及国际化相关 16 个用例通过。
- TypeScript 类型检查通过。
- 不应把旧全量运行描述为每次最后改动后都重新跑过全量。

关键前端测试：
- src/pages/OpportunityBoardPage.test.ts
- src/app/opportunity-board-routing.test.ts
- src/api/opportunity-board.test.ts
- src/api/frappe-adapter.test.ts
- src/features/opportunity-board/export.test.ts
- src/i18n/template-coverage.test.ts

后端测试（Claude 交付结果，Codex 未重新跑全量）：
- 规则 16/16；站点集成 8/8。
- 全量 420 用例中 test_stage6_web_entry 缺前端 index.html，交付说明称基线同样失败。
- 本次关键文件：tests/test_opportunity_board_rules.py、tests/test_opportunity_board_api.py。
- 型号写入改动需同时回归 tests/test_opportunity_api.py。

浏览器真实联调：
- Manager 测试账号默认 43 条、Demo 完成 5 条、华东 + Demo 完成 2 条。
- 保存查询新增、更新、重命名、恢复、删除已实测；临时查询已删除。
- 分组、直接刷新页面、中英文、桌面/手机布局已检查。
- XLSX 生成及工作表隔离/字符串转义有自动测试。
- 点击导出生成了文件名正确的 Blob 下载链接，页面无错误；自动化下载事件未返回，实际落盘仍待手工验收。不要声称已经验证下载成功。
- 导出使用逐页请求，检测总数、汇总、分组、重复 ID 和上海跨日变化；无服务端快照令牌，不能保证并发修改时的严格一致快照。
- 嵌套条件组没有实现，当前后端契约仅支持平铺 AND / OR。

建议检查命令（在 frontend 工作树执行）：

    git status --short
    git branch --show-current
    git log -1 --oneline
    node node_modules/vue-tsc/bin/vue-tsc.js --noEmit
    node node_modules/vitest/vitest.mjs run src/pages/OpportunityBoardPage.test.ts src/features/opportunity-board/export.test.ts src/api/opportunity-board.test.ts src/app/opportunity-board-routing.test.ts src/i18n/template-coverage.test.ts --maxWorkers=2
    git -c core.whitespace=cr-at-eol diff --check

如变更范围需要全量回归：
    node node_modules/vitest/vitest.mjs run --maxWorkers=2

## 11. 本机文件写入注意

用户提供的硬规则：机器有天锐绿盾透明加密。Claude Code 的 Write/Edit/NotebookEdit 可能把文件写成带 %TSD-Header-###% 头的加密内容。
请遵守本项目 AGENTS.md：
- 不使用这些工具写源码。
- 使用 Bash heredoc、sed/awk、可信 cmd 或 WSL Python 等已确认安全的写入方式。
- 不泄露账号、密码、Token、Cookie。
- Codex 本次使用 Git Bash heredoc/sed 写文件；长内容分块写，避免 Windows 命令长度截断。
- 部分仓库文件原本是 CRLF。保留原换行，避免整个文件出现无关 diff。

