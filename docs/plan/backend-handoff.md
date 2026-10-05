# Plan 前后端对接清单（2026-09-18）

## Planned Test Run 操作与执行人姓名（2026-09-22，开发分支，未部署）

本节更新下文历史记录中的两个剩余缺口，不改变已部署的 Demo 阶段计数规则。

- Evaluations 页面新增测试记录列表；Manager/Engineer 可对 Scheduled/Testing 阶段、当前轮次的 Planned 记录改期、填写结果完成或填写原因取消。Plan 的测试链接仍跳转到原 Evaluations 页面，不新增 Plan 写接口。
- 原记录 ID 保留；完成须三项结果及摘要齐全，0 是有效结果。旧轮次、已完成、已取消及评审阶段记录不可编辑。保存使用父 Evaluation 的 `modified`，失败保留输入，版本冲突后由用户明确放弃草稿并重新载入；请求中禁止重复提交与关闭。权限撤销清除页面数据和弹窗。
- Plan 通过单独的批量 User 查询返回行动执行人的 `actionOwnerName`，包括工程师；缺名返回 null，前端继续回退到账号。执行人不加入销售筛选，不改变销售归属、数量和分页。
- 为验证真实页面调用，测试用 mock 的 Evaluation 补齐稳定版本、成功修改后的版本递增和 Test Run 历史。已有版本保留；旧模拟快照的初始版本仅用于并发令牌，不作为业务时间。正式 Frappe 仍使用原有并发和历史机制。
- 本次不改 Status 附件存储、商机组合查询或导出，不新增业务库迁移。代码需与 PR #41 的接口一起集成；这段实现说明不代表已部署到 staging 或 production。
- 回归覆盖见 `src/pages/evaluation-run-actions.test.ts`、`src/api/evaluation-run-lifecycle.test.ts`、`test_cockpit_plan.py` 和 `test_cockpit_api.py`。

状态：Plan 读接口、Demo 阶段统计与已确认 UI 优化已部署 staging（2026-09-22，发布版本 `17cce3f-plan-demo-20260922`）。随后概率分级显示统一为英文，已完成本地测试，尚未包含在该 staging 发布中。本文后半部分保留各次实现与部署记录，当前规则以「计划测试按 Demo 阶段统计」为准。
当前分支：`codex/plan-integration`。本次提交打包上午已确认的 UI 与 Plan 逻辑优化；更早的基线与验证记录仅供追溯。

## 已确认的范围

- 保留计划拜访、计划测试、到期行动、本期预计 PO。
- 预计 PO 复用商机 `po_date` / `poDate`；不新增“客户承诺决策日”。
- 不新增报价计划发送日期；不做待发送报价卡片。
- 不做活动/展会、内部会议、设备筛选/设备汇总、团队目标。
- 区域、市场取客户主档；保留销售筛选。
- 前端 `/plan` 复用 AppShell（左侧功能栏、右上角角色信息）。从 Review 的 Plan 标签进入。
- 页面只读；记录链接进入原业务页面，编辑继续调用现有自有业务接口。

## 仅需新增两个读接口

完整前缀：`rayher_crm.api.v1.cockpit`，使用现有业务响应封装 `{data, meta, warnings}` 和错误码。

| 接口 | 参数 | 返回 |
|---|---|---|
| `get_plan` | `period`, `anchor`, `sales`, `region`, `market` | `PlanDto` |
| `get_plan_details` | 上述参数 + `metric`, `page`, `pageSize` | `PlanDetails` |

类型定义：`src/features/cockpit/plan-types.ts`。最小一致样例：`src/features/cockpit/plan.fixture.ts`（仅测试/预览，不进入运行时）。可调整契约，但请同步前端，不要独立采用另一套字段名。

- `period`: week / month / quarter / year。`anchor`: YYYY-MM-DD，必填且允许未来日期；所在周期在 2000-01-01 之前结束的日期返回 `VALIDATION_ERROR`。服务端返回周期 start/end（均为业务日期，含首尾）、previousAnchor/nextAnchor。周一至周日，上海时区。
- 默认打开下周；查询的是“当前数据库里的排期”，不是历史快照。`asOf` 是本次读取时间（带时区的时间戳），不是所选周期的结束时间。
- `sales` 为用户 ID；空字符串表示全部。`region`、`market` 是存储值，不是翻译标签；空字符串表示全部。
- 沿用 cockpit Manager 权限，后端必须校验身份、权限和各业务源的数据范围。前端隐藏不能替代后端鉴权。
- 区域迁移未就绪时返回 `regionReady=false` 并禁用区域筛选；禁止对未清洗的别名分别聚合。
- `filters` 返回当前身份可选的稳定选项，不要因选择某个销售就把其他销售选项清空。自定义区域、市场原文保留。
- 统计只在后端完成；不能由前端拉取所有业务表后统计。只使用自有业务接口，禁止 Frappe resource/get_list 通用读接口。

## 数据来源与计数（测试口径于 2026-09-22 更新）

| 类型 | 范围与日期 | 稳定 ID / 销售归属 |
|---|---|---|
| visits | CRM Visit.status = Planned；visit_date 落在周期内 | 拜访 ID / visit_owner |
| tests | Demo 的 Wafer Preparation 与 Test Preparation 均完成，尚未进入 Internal Review；每个 Evaluation 一次，不以 Test Run 或日期为门槛 | Evaluation ID / Demo Request.sales_owner；evaluationId 与 id 一致 |
| actions | CRM Opportunity Action.status = Open、archived=0；due 落在周期内；关联开放商机 | Action ID / 当前 opportunity_owner；另回传 actionOwner 为执行人 |
| po | 尚未收到 PO、未丢单的 S1–S6 商机；po_date 落在周期内 | 商机 ID / 当前 opportunity_owner |

以上销售筛选建议按业务归属销售统一，而非把工程师执行的 Action 冒充工程师销售业绩。Action 的执行人同时显示。若与既有业务定义冲突，Claude 在接接口前明确指出。

- 到期行动计 Action 条数，不能复用 Review 按商机去重的预警数量。不同 Action 即使属于同一商机，也各计一条。
- `overdue`：同一 Action 范围，但 `due < start`；保持原 due，不改到周一。不计入本期 actions 指标、销售 actions 列或市场活动数。
- `metric=all`：本期四类记录 + 往期未完成 Action；`visits/tests/actions/po`：对应本期明细；`overdue`：只看往期未完成 Action。
- 前端日程 key 为 kind + id；默认排序 carryover 优先，其余按 date、kind、id 稳定排序。分页 total 为该 metric 及筛选下的完整条数，page 从 1 开始，pageSize 默认 50、上限 200（沿用全站分页规则）。
- 默认包含周末。无日期的记录不能擅自排进某天；已有业务要求日期时仍需排除遗留空值。
- `market.activities` = 本期 visits + tests + actions；预计 PO、往期逾期不叠加。市场缺失使用 name=null 分组，不丢弃记录。
- 销售无归属用 id=null 组；可识别执行人姓名的方式沿用项目人员显示机制，ID 不变。
- 计划拜访不推断“新客户/老客户”分类；计划测试不推断“实验室/客户现场”分类。

## 预计 PO 与金额

- 商机预计 PO 日期只用于排期，不冒充实际 PO 收到时间或客户承诺的决策时间。
- 每个商机 PO 数量计一次；拜访/测试/行动中的关联商机不能重复累加预计金额。
- 金额口径（2026-09-20 后端确认，与 Review 对齐）：只使用商机上销售填写的人民币金额 `amount_cny`，未加权。`poAmounts` 字段形状不变，仍为 `[{currency, value}]`，但后端只会返回一条 `currency="CNY"`（或 `[]`）；value 是两位小数的十进制字符串。不读取原币 `amount`，不做汇率换算。未填写 `amount_cny` 的商机不计入金额，行内 amount/currency 为 null，并使 `poAmountIncomplete=true`。
- S1 仅计数量，不把尚无可靠金额的商机计为 0；相关行 amount/currency 为 null，聚合 `poAmountIncomplete=true`。其他缺失金额同样处理。
- 已知金额仍可显示，但有任何缺失时必须显示“部分金额数据不足”。完全没有本期商机时为 []、false；不伪造金额。
- `expectedPO.items` 返回同一 po 明细排序下前 5 条，`total` 为全部本期预计 PO 商机数；“查看全部”调用明细接口。
- 四档概率：low_probability → pipeline → upside → committed。无值回传 null。
- Metric 的 ready + 0 才是真正零；无法统计时 insufficient + null，并提供 reason，不用 0 掩盖缺数据。

## Claude 需要核实的唯一业务闭环

当前核查到 `add_evaluation_run`，没有找到修改/完成/取消已有 Planned run 的接口。
请确认已有计划如何转为 Completed、改期和取消：不能完成时另建一条而把原 Planned 永久保留，也不能统计旧 test_round。
若现有能力足够，给出调用方式即可；确有缺口则最小扩展原测试业务接口，保留既有权限、并发版本校验和审核约束。不要另建 Plan 写接口。

## 后端实现结论（Claude，2026-09-20）

两个读接口已实现：`cockpit.get_plan`、`cockpit.get_plan_details`，字段与 `plan-types.ts` 一致；真实返回样例见 `docs/plan/api-sample.json`。与上文建议口径的差异和补充：

- 金额：统一为 CNY，见上节。前端现有 `${currency} ${value}` 的展示无需改动，只是不会再出现多币种。
- 计划测试：Planned、当前 `test_round`，且 Evaluation 状态为 `Scheduled` 或 `Testing`，Demo Request 未取消。只有这两个状态下测试记录才能被完成、改期或取消；Evaluation 已进入 Internal Review 及之后仍残留的 Planned 记录不是可执行计划，不计入。
- 销售归属：拜访取 `visit_owner`；测试取 Demo Request 的 `sales_owner`；行动与预计 PO 取商机当前 `opportunity_owner`。行动同时返回 `actionOwner`（执行人用户 ID，可能是不在 `filters.sales` 里的工程师）。
- 无归属分组：`sales[].id = null` 时 `name` 返回空字符串，前端销售表、日程及分组均显示“未分配 / Unassigned”，不会留下空白名称。
- `sales[]` 和 `markets[]` 只包含本期有记录的销售/市场；往期未完成行动不会单独带出一行。
- 客户无主档（例如 Self Test 的 Evaluation 没有客户）的记录不进入 Plan，与 Review 一致。
- 缺日期：拜访日期、测试日期、行动到期日在业务上必填；若筛选范围内存在遗留空值，该指标返回 `insufficient` + `reason="missing_date"`（行动缺失时 `actions` 与 `overdue` 同时不足；市场 `activities` 任一来源不足即不足）。商机没有 `po_date` 属于“尚未排期”，不算数据不足。
- 明细行补充字段：拜访和测试在有关联商机时也带 `opportunityId`；预计 PO 行的 `status` 是商机阶段枚举（如 `rfq_validated`）。
- `anchor` 必填，缺失或非法返回 `VALIDATION_ERROR`；`metric` 缺省为 `all`；`pageSize` 缺省 50、上限 200（沿用全站分页规则）。
- 权限：非 Manager 在读取任何数据前返回 `PERMISSION_DENIED`；无效的 sales/market/region 返回 `VALIDATION_ERROR`，区域迁移未就绪时传 region 同样拒绝。

### 计划测试的完成、改期、取消

核实结果：此前确实只有 `add_evaluation_run`，已有 Planned 记录无法更新。已在原测试业务接口上最小补齐，没有新增 Plan 写接口：

| 接口 | 参数 | 作用 |
|---|---|---|
| `evaluations.update_evaluation_run` | `id`, `runId`, `input` | `input` 与新建相同（date、lot、wafers、capture、falsePositive、wph、summary）加必填 `expectedModified`。不带结果 = 改期/修改，仍为 Planned；三项结果加摘要齐全 = 原记录转为 Completed。 |
| `evaluations.cancel_evaluation_run` | `id`, `runId`, `input` | `input = {reason, expectedModified}`，reason 必填且不超过 500 字。记录保留，状态变为新增的 `Cancelled`，原因写入 `summary` 和 Evaluation 历史；不再计入 wafers 合计。 |

两者都要求 `evaluation:write`、Evaluation 数据范围、`expectedModified` 版本校验，只接受当前轮次的 Planned 记录，且 Evaluation 处于 Scheduled/Testing；均返回完整 `EvaluationDto`，并写 “Test Run” 历史。前端契约已同步：`TestRunDto.status` 增加 `Cancelled`，`CrmApi.updateEvaluationRun / cancelEvaluationRun` 在 Frappe 与 mock 适配器均已实现。Evaluations 页面的改期/取消操作入口尚未制作。

## 联调验收

1. API summary、sales、markets、details 在同一筛选下能核对，分别核对数量与币种金额。
2. 下周/下月/下季度/明年可查；周期切换和日期边界正确，周末不漏。
3. 修改原业务排期后刷新 Plan 更新；完成/取消的记录不再计入待执行计划。
4. 同商机多个 Action 分条统计；已归档、已完成、关闭商机的 Action 不计入；逾期保留原日期。
5. Sales/Engineer 直接调用接口被拒绝；Manager 不得读超出业务授权范围的数据。
6. 无记录返回 ready+0；数据不足、接口失败明确显示，不能自动回落到示例数据。
7. 超过 50 条仍能翻页，分组标题明确为本页记录，汇总不随页数改变。
8. 后端接口未部署前不要把前端页面发布视为联调完成；区域模块合并以 Claude 的发布分支为准。

## 前端接入核验（Codex，2026-09-20）

- 无须远程推送即可读取同机 `Desktop/CRM-plan-api`。为避开其他工作树中的 Booking 工作，本次从 `ef2340a` 新建 `codex/plan-integration`，仅提交 Plan 相关增量。
- 两个自有读接口的路径、筛选参数和分页调用已匹配；前端继续请求每页 50 条，兼容后端上限 200。没有新增 Plan 写接口。
- 预览 fixture 与页面测试同步为 `amount_cny` 的 CNY 金额口径，覆盖缺金额、未分配销售与不在销售筛选中的工程师执行人；未知执行人保留用户 ID。
- `api-sample.json` 的真实返回已用于组件测试，验证金额不足提示、预计 PO 数量、原始逾期日期和业务跳转。这是返回样例测试，不是本次重新完成 HTTP 联调；样例中的汇总和筛选后明细也不用于验证同一筛选总数一致。
- 修复了缺日期跨分组传播：Alice 的记录缺日期，只影响汇总和 Alice/所属市场的相关指标；Bob/其他市场仍返回其可确定的数量。已分别覆盖拜访、测试、行动三类缺日期；单独筛选 Bob 与全部销售表中的 Bob 指标一致。`dbaf514` 已补齐仅有缺日期记录的销售/市场汇总行。
- 本次独立验证：Plan 页面、Frappe 适配器和测试生命周期 mock 共 41 项前端测试通过；Plan 与 Review 纯规则共 45 项后端测试通过；vue-tsc 和 Frappe 模式生产构建通过。没有复跑 Docker 后端全量 389 项。
- 待完成：评估页面的改期/完成/取消操作入口、集成后的测试服部署及真实数据/权限验收。Plan 保持只读；不能把测试生命周期 API 已实现等同于页面操作闭环已交付。

### 姓名与数据不足提示适配（Codex，2026-09-20）

- 与后端约定新增可选 `actionOwnerName?: string | null`，保留 `actionOwner` 用户 ID。前端优先显示非空姓名，缺失时沿用销售姓名查找、用户 ID、未分配的回退顺序；不把工程师加入销售筛选。当前前端已支持，后端字段仍待 Claude 补齐并部署。
- Plan 的汇总、销售、市场和往期未完成指标收到 `insufficient` + `missing_date` 时，直接显示“数据不足：部分记录未填写日期”（支持英文）。未知原因保持“数据不足”，不展示内部原因码；不改变 Review 的展示。
- 测试服部署和上述 8 条真实验收仍待完成；本地组件测试不作为部署或真实联调证明。
- 本次显示适配验证：Plan 页面、Frappe 适配器、测试生命周期 mock 共 43 项通过；vue-tsc 通过。新增覆盖后端姓名优先、空姓名回退，以及汇总/销售/市场/逾期缺日期原因的中英文显示和未知原因回退。

### Plan 布局与本期日程（本地修改，未部署）

- 日程改为全宽七列周视图；销售、预计 PO、市场汇总位于下方。页头和右下方沿用 Review 的品牌渐变与 Logo 水印。
- 页面移除往期未完成入口及记录，不删除源业务数据。明细请求新增可选 `includeOverdue=false`；后端在分页前从 `metric=all` 排除 carryover，保证 total 和页数只计本期。参数缺省时保留原接口行为，显式 overdue 查询及 summary 不受影响。此改动需前后端一起部署，不能只发布前端。

### 销售汇总表的视觉验收约定

- Review 与 Plan 的销售表统一使用 `cockpit-sales-table` 及 `sales-table.css`：姓名列左对齐；数值列的表头和数据必须同时右对齐，禁止仅设置 `td` 的对齐。
- 样式验收必须逐列核对标题、字段绑定与文字对齐，不能只看表格边界；覆盖宽屏、窄屏、长姓名、多位数及金额加单数的两行内容。
- 组件测试只能证明字段渲染，不能证明 CSS 的视觉对应；发布前需在带 AppShell 全局字体规则的页面中检查实际布局。
- Review 为已发生业务的回顾，Plan 为所选周期的待执行排期；两页的字段集合和统计值不要求相等，须按各自口径验收。

### 计划测试按 Demo 阶段统计（2026-09-22，当前口径）

本节覆盖上文历史交接中以 Planned Test Run、当前轮次及测试日期为条件的旧规则；只修改计划测试，其他指标继续按原周期口径。

- 业务条件：Wafer Preparation、Test Preparation 均完成后进入 Plan；Scheduled 与 Testing 均计入；Internal Review（含旧 Analysis 状态）及后续阶段不计入。被取消的 Demo 不计入。历史记录未存准备标记时，沿用 Demo Test 页面按 Scheduled/Testing 判为准备完成的兼容规则；明确 Pending 仍未准备完成。
- 一份 Demo 计一次；不需要预建 Test Run，不要求 lot、wafers、测试结果、摘要或测试截止日期。测试记录的完成、取消、改期都不改变 Demo 的 Plan 归属。客户要求重测、重新进入 Testing 后再次计入。
- 测试数量是当前仍处在上述阶段的 Demo 总数，仍受销售／区域／市场筛选，但不受周／月／季／年日期窗口排除；这点在页面说明中明确。汇总、销售、市场活动数和明细使用同一集合。
- 测试行 `id=evaluationId`，`status=Scheduled|Testing`；`date` 取现有 `test_run_deadline`，缺失返回 null。日期只用于展示，不回填、不虚构日期，也不返回 missing_date。拜访与行动的原缺日期提示不变。
- 日程保持周一至周日七列；无日期或截止日期在周期外的 Demo 放在下方“待排期／进行中”分组。保留真实截止日期；按销售／市场分组时同样保留这些 Demo。往期未完成 Action 仍不展示。
- 测试：Plan/Review 纯规则 50 项，独立 Docker 测试站 Evaluation/Cockpit 接口 18 项，前端 Plan/Review 34 项，vue-tsc、Frappe 构建通过。最初旧 Docker 测试栈因商机 schema 过旧无法建夹具，改用已有 stages 测试栈验证通过；未改动业务库 schema。
- staging 只读核对（进程内加载新计算规则，结束即丢弃）：旧口径 0，新口径 5；测试明细及销售测试合计均为 5，这 5 个 Demo 均未填测试截止日期。此核对不代表已部署。
- 本次修改保留在本地；未提交、推送、更新 PR 或部署。

### 本地确认内容已部署 staging（2026-09-22）

- 用户明确授权部署；发布版本 `17cce3f-plan-demo-20260922`，基于 `17cce3f` 加本地未提交改动。镜像 `rayher-crm-stage1:v15-staging-17cce3f-plan-demo-20260922`。未提交、推送或更新 PR。
- 包含 Plan 按 Demo 阶段统计、无日期测试展示、Plan/Review 共享销售表对齐，以及两页左上角“销售经营看板 · 检测与量测系统”删除。
- 仅替换现有发布包中的两个 Plan 后端服务文件与前端构建资源；校验后端原文件与本地 HEAD 基线一致，其他后端文件完整保留。无 schema 改动，未运行数据库迁移。
- 已执行数据库与文件备份，位于服务器 `backups/pre-update-17cce3f-plan-demo-20260922-20260922-030855`；上一版 `17cce3f-sales-align-20260922` 镜像与输入保留，可回退。
- 所有应用服务正常，backend/frontend 健康检查通过；部署前后 9 类业务记录数量一致。
- 部署后只读接口核对：周/月/季度/年均为 5 个计划测试，汇总、销售合计、市场活动与明细一致；Sales/Engineer 均被两个服务入口拒绝。
- 实际浏览器确认：Review 与 Plan 旧抬头已移除、销售表数值表头/内容同向右对齐、Plan 显示 5 个测试、七列周视图保留；年度 68 条记录第二页显示 18 条，翻页不改变汇总。页面未发现控制台错误。
