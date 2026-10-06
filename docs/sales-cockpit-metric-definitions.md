# Sales Cockpit 指标口径表（Review / Warnings / Plan）

> #18 验收项“形成指标口径表”。依据分支 `feat/warnings-handling` 的代码整理（2026-09-24）；函数都在 `backend/apps/rayher_crm/rayher_crm/services/` 下（`cockpit_metrics.py`、`cockpit.py`、`cockpit_conversion.py`、`cockpit_plan.py`、`cockpit_settings.py`）。改口径时同步改本表。

**范围**：Manager 专用的 Review、Warnings、Plan 三页上显示的每个数字。Warnings 页（`get_warnings`）和 Review 页（`get_review`）走同一个 `calculate()`，筛选和周期相同，所以两页的数字一致。

**截至时点（as_of，`period`）**
- 已结束的周期：as_of = 周期最后一天 23:59:59.999999。
- 进行中的周期：as_of = 当前时刻 now。
- 期间发生量的区间是 `[start, cutoff)`，cutoff = min(周期结束, now)。

**时区**：所有日界按 Asia/Shanghai（UTC+8）。`stamp()` 把带时区的时间换算成上海时间，不带时区的库内时间直接当上海时间；Date 字段按上海自然日 00:00；API 返回 UTC `…Z`，前端按 Asia/Shanghai 显示。

**历史覆盖**：覆盖起点配在 site config `crm_cockpit_history_complete_from = {stage, fields, actions, probability}`。`covered(key, t)` 只有在“起点 ≤ t”时为真。缺覆盖时返回 `state = insufficient`，页面显示“数据不足”，**不会显示 0**；已记录的明细仍可打开作为样本。PO 统计不读覆盖键，直接用 Booking 当前状态。**这个键没有默认值，要在部署时按站点设置**：没有它时，丢单待复盘、概率降档、第 6 阶段三项在当前周期也显示数据不足，第 6 阶段的商机不会列出、也不发每日提醒；逾期行动和报价到期不依赖它。

**状态值**：ready，insufficient（数据不足），not_applicable（不适用），not_set（未设置）。见 `metric()` 和前端 `metricText()`。

## 一、Review

表中没写区域和市场的，都按客户主档当前值筛选（见通用规则 4）。

| 指标（UI · API · 明细 key） | 业务日期 | 类型 | 规则 / 阈值 | 历史覆盖 | 计数单位（= 明细行数？） | 筛选：销售 / 设备 | 函数 |
|---|---|---|---|---|---|---|---|
| 客户沟通 · `activities[visits]` · `visits` | CRM Visit.`visit_date` | 期间发生量；上期同规则 | status ∈ Visited / Minutes Submitted / Manager Reviewed。范围内任一条缺 visit_date，本期和上期都显示数据不足（不限期间） | 不需要 | 拜访条数 = 行数 | 销售取 visit_owner 当前值。设备看关联商机；没有商机的不计入，单独显示“N 条未关联商机，未计入”（`unclassified`） | `build_review` |
| 新增合格线索 · `activities[leads]` · `leads` | Lead.`custom_crm_converted_at`；为空时取阶段历史 `lead_converted` 的 `reached_at` | 期间发生量 | 线索已转化且转化客户在范围内。状态是 Converted 但没有时间的，显示数据不足 | 选了销售时需要 fields ≤ 转化时间，否则负责人未知，显示数据不足（不限期间） | 线索数 = 行数 | 销售取**转化时**的商机负责人（按字段历史回放）。设备看转化商机；没有商机的直接排除 | `build_review`、`field_at` |
| 完成测试 · `activities[tests]` · `tests` | CRM Test Run.`run_date` | 期间发生量 | Test Run 状态为 Completed，每轮（含复测）各计 1。缺 run_date、缺 Demo Request 或 sales_owner 为空，都显示数据不足 | 不需要 | 测试**轮次**数 = 行数 | 销售取 Demo Request.sales_owner 当前值。设备看 Request.opportunity；没有商机的进 unclassified | `build_review` |
| 首次发布报价 · `activities[quotes]` · `quotes` | 该报价最早一个版本的 `published_at` | 期间发生量 | 每张报价只计首次发布。状态不是 Draft 却没有任何已发布版本的，显示数据不足 | 不需要 | 报价单数 = 行数 | 销售和客户取**首个发布版本**上的 quotation_owner / account 快照。设备看 Quotation.opportunity；没有商机的进 unclassified | `build_review` |
| “较上期”/“/ N 目标” · `previous`、`delta`、`target` | 目标 anchor = 周期开始日 | — | 任一侧数据不足时 delta 为 null。目标只在“选了单个销售、且没选区域/市场/设备”时适用，否则不适用。周视图没有当周目标时，取 anchor ≤ 周一的最新 `weekly_default`；都没有则未设置 | — | — | — | `build_review`、`attach_targets` |
| 商机阶段分布 S1–S6 数量 · `pipeline[<stage>].count` · 各阶段 key | 阶段历史 `reached_at`（为空用 `recorded_at`）倒放到 as_of；只算 creation ≤ as_of 的商机 | 截至 as_of 的存量 | 当前周期取当前 stage；历史周期倒放阶段历史。某商机在 as_of 之后有 migration 行或 basis 为 unknown/upper_bound 的行，它的阶段算未知，此时**全部**阶段计数显示数据不足 | 历史周期需要 stage ≤ as_of；选了销售还需要 fields ≤ as_of | 去重商机数 = 行数 | 销售取 **as_of 时**的负责人。设备看商机当前 tool_type | `stage_at`、`build_review` |
| 阶段金额 S2–S6 · `pipeline[<stage>].amount` | amount_cny 按字段历史回放到 as_of | 截至 as_of 的存量 | S1 不适用（仅计数量）。任一行缺人民币金额，该阶段金额显示数据不足 | 历史周期需要 stage 和 fields ≤ as_of | 金额合计 = 明细金额之和 | 同上 | `cny_amount_at`、`amount` |
| 已收到 PO · 年累计 · `pipeline[po]`、`orders.count/actual` · `po` | Booking.`actual_po_date` | 年初到 as_of 当天：as_of 所在年的 1 月 1 日 ≤ 日期 ≤ as_of 日期。**不随周/月/季变化** | source = Opportunity，且**当前**状态 ∈ Confirmed / Completed。YTD 内任一单缺人民币金额，年累计金额显示数据不足 | 不需要；站点没有 actual_po_date 字段时显示数据不足 | **Booking 数**（不是商机数） | 销售取商机**当前**负责人（不是 booking_owner）。设备看源商机 | `build_review`、`booking_cny_amount`、`po_amount` |
| PO 日期待补录 / 人民币金额待补录 · `orders.missingDate/missingAmount` · `po_missing_date`、`po_missing_amount` | 同上 | 当前状态 | 待补日期：范围内所有 Confirmed/Completed 订单中没有 actual_po_date 的，**不限年份**。待补金额：YTD 内缺人民币金额的订单 | 不需要 | Booking 数 = 行数 | 同上 | `build_review` |
| 个人年度订单与目标 · `orders.target/planned/series/elapsedFraction` | 目标取 metric=orders、period=year、anchor = as_of 年 1 月 1 日 | 截至 as_of | planned = 年目标 × 已过天数 ÷ 全年天数（1 月 1 日数到 as_of 当天，含当天）。series 按 actual_po_date 逐日累计 | — | 金额 | 只在“单个销售、且没选区域/市场/设备”时有目标 | `attach_targets`、`po_series` |
| 销售表现 · `sales[*]` | 各列沿用对应指标 | — | 行 = 全部 CRM Sales 用户 + 明细里出现过的负责人。某活动整体数据不足，或本期明细里有负责人为空的行，**整列**显示数据不足 | 同各指标 | 行数 / 金额 | 各指标自己的负责人口径 | `build_review` |
| 停滞商机 · `stalled.count/items`（显示前 5）· `stalled` | 共用活动事实的实际业务时间及 Opportunity History 实质行动变更的最大值（详见 PR03 合同）；没有时用商机 creation | 截至 as_of 的存量，只看当时处于 S1–S6 的商机 | as_of 日期 − 最后更新日期 ≥ 21 天提醒，≥ 35 天升级（high）。最后更新早于 actions 覆盖起点时按覆盖起点算，显示“≥N” | **当前周期也需要** actions ≤ as_of − 35 天，且阶段计数为 ready | 去重商机数 = 行数 | 同阶段分布 | `build_review`、`substantive` |
| 近 12 个月丢单 · `losses.count/reviewed/pending/items` · `losses` | 阶段历史 `marked_lost` 的 `reached_at`（跳过 migration 行） | 窗口发生量：[as_of 日期 − 12 个自然月, as_of] | 按**丢单事件**计（丢单、重开、再丢单算 2 次）。reviewed = 复盘为 Reviewed；pending = 未复盘且丢单后没有 reopened（都按当前状态） | stage ≤ 窗口起点；选了销售还需要 fields ≤ 窗口起点 | 事件数 = 行数 | 销售取**丢单时**的负责人。金额取丢单时的 amount_cny | `build_review`、`event_count` |
| 阶段转化率 · `conversions.items[*]` · `reached_<stage>` | 阶段历史 `reached_at`，只认 basis ∈ recorded / declared / evidence | 窗口发生量：[as_of 日期 − 24 个自然月, as_of] | 每个阶段按商机去重、各自独立计数（比例可能超过 100%）。五步：S1→S2、S2→S3、S3→S4、S4→S5、S5→S7。低于 `crm_cockpit_conversion_threshold`（默认 45）标为瓶颈 | stage ≤ 窗口起点；窗口内有 upper_bound/unknown 或缺日期的到达记录就算不完整：比率显示数据不足，数量照常显示 | 去重商机数 = 行数 | 销售取 as_of 时的负责人 | `build_conversions` |
| 覆盖倍数 · `pipelineCoverage.openPipeline/remainingTarget/ratio` | 沿用阶段金额和 PO 金额 | 截至 as_of | openPipeline = S2–S6 金额之和（五项须都是 ready）。remaining = 年目标 − 年累计 PO；ratio = openPipeline ÷ remaining；remaining ≤ 0 时不适用。参考范围 3–4× | 同上游指标 | 金额 / 倍数 | 目标适用条件同个人目标 | `pipeline_coverage` |

## 二、Warnings（Review 顶部横幅 = `warnings` 数组；Warnings 页 = `get_warnings`）

| 指标（UI · API · 明细 key） | 业务日期 | 类型 | 规则 / 阈值 | 历史覆盖 | 计数单位 | 筛选：销售 / 设备 | 函数 |
|---|---|---|---|---|---|---|---|
| 近 4 周丢单待复盘 · `warnings[lost]` · `lost`、`lost_backlog` | `marked_lost` 的 `reached_at` ≤ as_of（跳过 migration 行） | **固定 28 天**窗口 [as_of 日期 − 27 天, as_of]，与周期类型无关 | 只计窗口内“待复盘”：复盘不是 Reviewed，且丢单后没有 reopened（按当前状态）。更早、仍待复盘的进 backlog（不限多久以前，补丁补建的也在内），标“复盘逾期”，**只列出不计数** | stage ≤ 窗口起点；选了销售还需要 fields。**当前周期也需要** | 按商机去重；`lost` 列表含窗口内全部丢单（已复盘的也在），行数 ≥ 数字 | 销售取丢单时的负责人 | `build_review` |
| 未执行计划（行动逾期） · `warnings[overdue]` · `overdue` | Action.`due` | 截至 as_of 的存量 + 当前状态 | as_of 时状态为 Open / In Progress / Blocked / Rescheduled 且 due < **as_of 的上海日期**；同时**现在**仍 Open / In Progress / Blocked / Rescheduled、未归档，当前 due 也 < as_of 日期。完成、归档或改期都会清除。as_of 时商机须处于 S1–S6，且**现在**仍处于 S1–S6（收到 PO 或丢单即清除，与记录“下一步”的校验一致）。保存“下一步”不清除 | 历史周期需要 stage 和 actions ≤ as_of（选了销售还需要 fields） | 按（商机, 行动）计 = 行数 | 销售取 as_of 时的**商机负责人**（不是 action_owner） | `actions_at`、`build_review`、`action_count` |
| 概率降档 · `warnings[downgrade]` · `downgrade`、`downgrade_history` | Probability History.`changed_at` | 期间发生量 [周期开始, as_of]，处理状态看当前 | 档位下降才算（low_probability < pipeline < upside < committed）。待处理 = 没有 Recovery 记录或 acted_at 为空；只改计划不清除 | **当前周期也需要** probability ≤ 周期开始 | 待处理按商机去重；列表每次降档一行，行数 ≥ 数字 | 销售取**当前**负责人 | `build_review` |
| 报价即将到期 · `warnings[quotation_expiry]` · `quotation_expiry` | 当前正式版本的 `valid_until` | 参考日 = as_of 的上海日期；版本状态看当前 | 0 ≤ valid_until − 参考日 ≤ N（含两端），并要求 valid_until ≥ **今天**、published_at ≤ as_of、版本为 Published；商机当前是 po_received 或 lost 的跳过。保存“下一步”不清除 | 不需要；正式版本数据缺失时显示数据不足（`quotation_expiry_data_missing`） | 报价单数 = 行数 | 客户取报价 account；销售取 quotation_owner 当前值；设备看关联商机，没有商机的排除 | `quotation_expiry` |
| 第 6 阶段超期无 PO · `warnings[stage6_no_po]` · `stage6_no_po`、`stage6_no_po_handled` | 最后一次进入 S6 的 `reached_at`（为空用 `recorded_at`） | 截至 as_of 的存量，且**现在**仍在 S6 | as_of 日期 − 进入日期 ≥ N 天。进入记录早于覆盖起点、或商机在覆盖起点前创建而没有进入记录时，按覆盖起点算；进入记录是 migration / unknown / upper_bound 时，按该记录的 `reached_at` 算（为空用 `recorded_at`；实际进入可能更早）。这两种情况都显示“≥N”。**已记录行动且复核日晚于今天的转入 handled，只列出不计数；到复核日重新计入** | 进入时间精确且未到阈值时不需要；其余需要 stage ≤ as_of，否则数据不足 | 去重商机数 = `stage6_no_po` 行数 | 同阶段分布 | `stage6_stay`、`handling_state` |
| 其他提醒（Warnings 卡片） | — | — | 前端把报价到期和第 6 阶段两个数相加；任一项不是 ready，整体显示数据不足 | — | — | — | `WarningsPage.vue` `otherCount` |

预计 PO 跨季度推迟使用字段审计 `po_date`，只取当前仍有效、所选截止日前发生的最新延期实例。Q4 到次年 Q1 算跨季度，同季度调整保持身份；新跨季度延期产生新身份。恢复到该次延期前的季度或关闭商机清除提醒；经理记录行动与未来复核日暂移到已处理列表，复核日仍有效时恢复。按当前商机负责人、当前客户地域和设备筛选；`fields` 审计覆盖不足时计数显示数据不足。卡片 `close_date_slip` 与相同键的明细逐条对应，`close_date_slip_handled` 只列出不计数。

**阈值来源**（`cockpit_settings.thresholds`）：Warnings 页“阈值设置”（CRM Cockpit Settings；报价 0–365，0 表示只提醒当天到期；第 6 阶段 1–365）优先；其次 site config（`crm_cockpit_quote_expiry_days` 0–365，`crm_cockpit_stage6_no_po_days` 1–365）；默认 14 / 56（已有经理设置和站点配置不覆盖）。改动当期立即生效，每次保存留版本记录。

**处理记录**（CRM Warning Handling）：每条逾期行动（行动 + 到期日）、报价（报价 + 版本）、第 6 阶段（商机 + 进入事件）是一个提醒实例。改期、换版或重新进入 S6 就是新实例；同一行动改回同一个到期日（完成后又重新打开，或改期后又改回）仍是同一个实例，沿用之前的下一步，通知也只发一次。“下一步”只记录、不清除；第 6 阶段和预计 PO 跨季度推迟可记录已采取行动 + 复核日。阈值只决定哪些行显示，处理记录绑定提醒实例：阈值调高后，先前记录的行动仍然有效，商机再次达到阈值时按已处理列出、到复核日重新计入，不会因为阈值变动而丢失；但商机未达当前阈值时不能再记录新的行动（提醒已变化，页面提示重新加载），避免旧动作压掉之后才出现的预警。

**通知**（每日任务 `send_warning_notifications`）：每个提醒实例只通知一次，且只通知最近 3 天内新出现的提醒（`NOTICE_DAYS`；首次启用或清库后不补发旧提醒，旧提醒在页面上看）。“新出现”按提醒第一次满足条件的日子算：逾期行动是到期次日，报价是进入提醒窗口的日子，第 6 阶段是停留天数第一次达到阈值的日子（只知道下界时按下界算，也就是第一次列出的日子）；已记录行动的第 6 阶段商机，在复核日和重新达到阈值两者中较晚的那天再通知一次。覆盖起点（`crm_cockpit_history_complete_from`）是部署设置；上线后再改它，只知道下界的商机“第一次列出”的日子会跟着变：改晚，已在页面上的商机可能补一次通知（每个提醒实例、每个收件人最多一次）；改早，3 天窗口内还没发出的提醒可能不再补发，提醒仍在 Warnings 页上。Manager 收全部；逾期行动的执行人、报价负责人及跨季度延期商机的当前负责人也收自己的（须仍具备来源访问权限）。降档仍在变更当时通知。

## 三、Plan（`build_plan`；只读当前记录，不回放历史，也不需要历史覆盖）

**周期**：`plan_period` 必须传 anchor，按 `bounds` 对齐，start 和 end 都含；允许查看未来周期，asOf = now。前端默认打开下一周（下一个周一，今天是周一也跳到下周一）；切换周期类型时跳到下个月、下个季度或下一年的第一天。查看过去的周期时，只显示现在仍未完成的记录。

| 指标（UI · API · 明细 key） | 业务日期 | 类型 | 规则 | 计数单位 | 筛选：销售 / 设备 | 函数 |
|---|---|---|---|---|---|---|
| 计划拜访 · `summary.visits` · `visits` | Visit.`visit_date` ∈ [start, end] | 周期内，状态看当前 | 当前 status = Planned。范围内任一 Planned 拜访缺日期，显示数据不足（`missing_date`） | 拜访条数 | 销售取 visit_owner。设备看关联商机；没有商机的计入 `equipmentUnclassified.visits` | `build_plan` |
| 计划测试 · `summary.tests` · `tests` | **不按日期筛选**；`test_run_deadline` 只用来排列 | 当前存量，与所选周期无关 | Evaluation 状态 ∈ Scheduled / Testing，准备项都不是 Pending，Demo Request 未取消 | **Evaluation 数** | 销售取 Request.sales_owner。设备看 Request.opportunity | `build_plan` |
| 到期行动 · `summary.actions` · `actions` | Action.`due` ∈ [start, end] | 周期内，状态看当前 | Open / In Progress / Blocked / Rescheduled、未归档，商机当前处于 S1–S6。缺 due 显示数据不足。due < 周期开始的是结转（逾期已移到 Warnings），不计入本期 | 行动条数 | 销售取当前**商机负责人** | `build_plan` |
| 本期预计 PO · `summary.po`、`expectedPO` · `po` | Opportunity.`po_date` ∈ [start, end] | 周期内，状态看当前 | 商机当前处于 S1–S6。金额 = 当前 amount_cny > 0，S1 不给金额，不加权；已知金额相加，缺的标“部分金额数据不足” | 商机数 | 销售取当前商机负责人 | `build_plan` |
| 销售计划汇总 · `sales[*]` / 按市场汇总 · `markets[*]` | 同上 | — | 按负责人或客户市场分行；有缺日期的记录时对应列显示数据不足 | 计数 / 金额 | 同上 | `build_plan` |

## 四、通用规则

1. **周期**：week 是周一到周日（ISO 周，跨年周归属周一所在的周期，例如 2026-12-28 至 2027-01-03 是 2026 年第 53 周）；month、quarter、year 是自然月、季、年；财年等于自然年。Review 和 Warnings 不允许查看未来周期；Review、Warnings 和 Plan 都不接受在 2000-01-01 之前结束的周期（返回 `VALIDATION_ERROR`），最早的周期是包含 2000-01-01 的那一个；previousAnchor = 上一期开始日，nextAnchor = 本期结束后第一天。**不带 anchor 时**，Review 显示上一整周（`period()` 的默认），Warnings 显示当前周期（`get_warnings` 补上今天：每日提醒指向的商机详情页上的复盘卡片链接、Plan 与看板的 Warnings 标签引来的都是本周的行）；两页互相跳转时显式带上 anchor（没有 anchor 且数据尚未加载完成时标签不可点，因为还没有可带的周期），所以看到的是同一周期。
2. **与上期对比**：进行中的周期和上期相同已过时长比，但不超过上期结束（例如 3 月 31 日看 3 月，只和整个 2 月比）；已结束的周期和完整的上期比。
3. **时区**：见开头。所有“逾期、N 天”都按上海日历日相减；UTC 16:00 已是上海次日。
4. **区域和市场**：取客户主档当前的 `custom_crm_region` / `custom_crm_segment`，不回放历史。报价类取报价或版本上的 account 快照；线索取转化客户。区域筛选只有在 `crm_cockpit_region_migration_verified` 已设置、且所有客户区域值合法时才开放。区域按销售区域树（`CRM Sales Territory`：全球 → 洲 → 国家 → 区域）列出：`filters.regions` 是树的显示顺序（上级在前），其后是树里没有同名节点的区域；`filters.regionParents` 是每个名称的上级。区域节点与客户区域同名；选一个上级（如 China）等于选它下面的全部区域，不改客户主档的存储值。树只用于分类和汇总，不进入任何权限条件。任何区域筛选下个人目标仍为"不适用"。
5. **销售**：筛选值必须是 CRM Sales 用户。需要回放负责人的口径，缺 fields 覆盖时显示数据不足。
6. **设备**：设备属于商机，用 `equipment_key` 比较（忽略大小写、全半角、空格和标点）。没有关联商机的记录不推测，按表内规则排除或单列“未关联商机”。
7. **金额**：全部用人民币，不做汇率换算（销售手填原币和人民币金额）。商机金额 = amount_cny（> 0 才算已填），历史时点按字段历史回放。Booking：人民币订单用 amount，外币订单用 amount_cny。Review 合计里任一行缺金额就显示数据不足；Plan 和 Warnings 卡片副文案把已知金额相加并标出缺失条数。
8. **按当前状态判断**：复盘、重开、降档行动、第 6 阶段行动和复核日、行动完成或归档、报价版本状态、商机是否仍在 S6，都按现在的状态判断，所以查看历史周期时这些处理也会让提醒消失。保存“下一步”永远不清除提醒。
9. **空范围**：筛选后没有任何记录时显示 0（ready），不是数据不足。
10. **卡片 = 明细**：每个卡片数字等于它下钻明细的行数（计数单位见表内：商机、行动、事件或 Booking），金额合计等于明细金额之和。由 `tests/test_cockpit_boundaries.py` 校验。
11. **写死的常量**：停滞 21 / 35 天，丢单窗口 28 天，丢单统计 12 个月，转化率窗口 24 个月，覆盖倍数参考 3–4×。

## 五、待确认

1. **丢单计数单位不一致**：丢单预警按商机去重，近 12 个月丢单按事件计。再次丢单前必须先重开，所以实际数字通常一样，但口径不同。
2. **横幅文案**：Review 横幅只写“丢单”，实际数的是“近 4 周、待复盘”，与所选周期无关（年视图也只看最近 28 天）。
3. **历史周期的报价到期**：要求 valid_until ≥ 今天，所以参考日比今天早 N 天以上的历史周期一定显示 0。
4. **线索缺负责人的范围**：选了销售时，fields 覆盖起点之前转化的线索会让所有周期的线索数显示数据不足，是否只限窗口内的线索需要确认。


## PR03 统一活动事实与客户关系快照（2026-10-05）

Review 与 Plan 共用 `services/activities.py` 的来源身份与业务日期投影；同一来源通过不同关联读到时只保留一条。事实包含 sourceDoctype / sourceId / sourceKey、eventId、关联客户与商机、负责人、状态、计划日期、发生日期、记录日期及时间依据。它是当前源记录的投影，不是另一套可编辑业务记录；更正、取消与重开反映源记录当前状态，源记录审计仍用于历史解释。

- 拜访完成状态仍是 Visited / Minutes Submitted / Manager Reviewed，业务日期仍取 visit_date。客户主档 customerKind 为 Prospect / Existing / 空；首次完成时锁定读取主档并保存 customer_kind、customer_kind_captured_at、completed_at。后两者是完成登记时间，不能证明回填拜访日期当天的客户关系。之后修改客户主档不重写快照；旧记录不补猜分类。
- Demo 每个 Completed Test Run 按 run_date 计一次，复测是另一次测试。Plan 的 Scheduled / Testing Demo 仍按评估计一项，准备未完成或请求取消时不纳入。
- 报价只按首次发布版本计算活动，其客户、负责人、金额来自该版本；版本金额币种为 CNY 才提供 amountCny，其余为空，不自动换汇。新金额与分类拆分指标的显示由 PR04 实现。
- 商机行动进入 Done 时由服务器记录 completed_at；备注、标题等后续编辑不改完成时间。重开清空；再次完成记录新的当前周期。迁移仅使用审计里 actionCreated(Done) 或非 Done → Done 的真实转换，并拒绝断裂的状态链；无证据的历史 Done 保持未知。
- 停滞的最后实质活动时间取：已完成拜访、Lead 转化、已完成 Test Run、首次报价发布、已完成行动的业务时间，以及既有实质行动变更时间的最大值。不取未来计划或仅改备注。没有实质活动时仍以商机创建时间为起点，保留既有历史覆盖门槛；有无日期的完成事实且可能影响停滞判断时，计数显示数据不足，不将其当成确定的停滞商机。

旧行动在完整审计覆盖起点之前已创建、当前为 Done，且完整覆盖期间没有该行动的新建／重开／新完成转换或断裂审计时，可证明完成早于覆盖起点；完成时间字段仍保持未知，停滞继续按既有覆盖下界计算，不误使全范围数据不足。回填同时识别旧审计中的 Completed 为 Done。全团队线索计数不要求历史负责人已知；选定销售时仍保留归属不确定性。活动按商机预先分组，避免每个商机扫描全部活动。
