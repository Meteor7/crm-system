# 已确认 UI 与后端对接清单 — 2026-09-17

用户已确认 `previews/review/index.html` 为后续 Review 的视觉实现标准。范围仍以 implementation-contract.md 为准。预览中的演示数据、日期算法、固定比例和辅助文案不能直接进入真实统计。

本次核查：GitHub #36 `5c5f27d`、#37 `6225a74`。这是已推送代码审计，不是测试服务器部署核验；GitHub 上尚未发现区域模块分支或 PR，不代表 Claude 本地没有未推送实现。

## 正式接入状态（本次更新）

已将确认稿做进 ReviewPage.vue，沿用 AppShell，并连接下述三个接口。丢单时金额已补返回并有历史回放测试。用户告知区域模块已在测试服发布版本 `119b9fc` 中运行、尚未推 GitHub；Claude 合并该版本时接区域中文显示，本分支保持接口原文。下文原始核查基线记录的是确认稿审计时的状态，不代表测试服当前部署状态。

## 接口保留三个

- GET `rayher_crm.api.v1.cockpit.get_review`：期间、筛选、活动、漏斗、预警、销售表现、订单及个人目标、停滞和丢单摘要。
- GET `rayher_crm.api.v1.cockpit.get_details`：相同筛选和期间下的分页明细，metric 分别传 visits/leads/tests/quotes、阶段、po/lost/overdue/downgrade/stalled/losses。
- POST `rayher_crm.api.v1.cockpit.save_target`：个人目标；更新携带 expectedModified。

不新增第二套看板接口，不调用 Frappe 通用 resource/client 接口。

## 逐区域映射

| UI 区域 | 已有响应字段 | 实接处理 |
| --- | --- | --- |
| 周次、日期、周期切换 | period.kind/start/end/asOf/previousAnchor/nextAnchor/hasNext | 按服务端周期绘制，移除演示日期与倍数计算。 |
| 销售、市场、区域 | filters.sales/markets/regions/regionReady | 区域待模块与迁移；正式页面不能使用预览的固定选项冒充已可用。 |
| 四项活动 | activities[].actual/previous/delta/target | 数值、比较、个人目标可接；全部销售无团队目标。保留不足/未设置/不适用状态。 |
| S1–S7 漏斗 | pipeline[].key/count/amount | S1 不展示金额；S2–S6 是估算值；S7 为 PO 数量和年累计人民币金额（2026-09-18 起，见第 4 点），不能沿用预览中的示例金额。 |
| 预警 | warnings[].key/count；get_details 的 lost/overdue/downgrade/quotation_expiry | 分别使用真实分类；不能用停滞商机列表代替逾期 Action。报价到期按报价单计数，其他分类按商机计数，不相加为商机总数。 |
| 销售表现 | sales[].id/name/activities/pipeline/poCount | 现有字段够用。姓名下的城市是演示内容，没有销售辖区接口依据，正式版先去掉这一行。 |
| 停滞商机表 | stalled.items 的 customer/stage/amount/currency/owner/days/daysAtLeast/severity/lastActionAt | 主要列全部能接；金额为参考时点估算，S1 显示无金额。保留 21/35 天口径，若按周显示不能舍去“至少”的含义。 |
| 近 12 月丢单 | losses.items 的 customer/title/owner/stage/at/reason | 名称、原因、销售、日期、阶段可接；右侧金额已补历史时点返回，见下。 |
| 个人年度计划 | orders.target/planned/elapsedFraction；orders.actual/series；个人目标写接口 | 计划线可接；实际线、达成率和差额自 2026-09-18 起按订单人民币金额计算（见第 4 点），仍不使用演示值。 |

## 必要缺口与分工

### 1. 丢单时估算金额 — 已补现有响应

`cockpit_metrics.py` 中 marked_lost 事件生成的行现已包含 amount/currency。主表和 Opportunity History 已有这些字段，不需要新建表或业务写接口。

在丢单事件时点用 field_at 回放 amount/currency，再补到 losses/lost 摘要和明细的相同行结构。字段历史无法证明完整则返回空值，前端展示数据不足；不能用当前商机金额回填旧丢单。展示名称为“丢单时商机估算金额”，不当作订单实际金额。优先沿用 ReviewRow 现有可选字段。

验证点：丢单后改金额或重新打开商机，不改变那条丢单事件的金额；缺历史时不伪造；保留原币种且不将外币直接标作人民币。

### 2. 区域字段收敛及迁移 — Claude 从 119b9fc 合入，Codex 读取原值

已推送的 setup/custom_fields.py 中 Customer.custom_crm_region 仍为 Data。需完成 Customer 区域与 Opportunity.sub_region 的 Select、共享选项、变体归一、存量 dry-run/确认/迁移/核验。

默认值是 East China / South China / West China / North China / Central China，支持已约定的共享自定义选项。Review 仅按客户主档区域筛选。区域核验完成后才设置 crm_cockpit_region_migration_verified 并启用筛选；不需要新建区域主数据表。（2026-10-03 补充：客户区域仍是唯一的存储值；其上叠加了销售区域树 `CRM Sales Territory`，筛选可选上级节点，口径见 `docs/sales-cockpit-metric-definitions.md`。）

### 3. 历史覆盖证据 — 部署方提供，Codex 使用状态

部署方需给出阶段/字段/Action/PO/概率的实际上线、迁移和写入路径证据，以配置 crm_cockpit_history_complete_from。不能以 Git 时间或最早历史行当可信起点。没有证据的区间保持数据不足，同时可以展示已记录明细。

这是数据完整性与部署核验，不是缺一个历史读接口。丢单金额、历史漏斗、停滞判断和个人归属都受它影响。

### 4. 年度实际金额曲线 — 2026-09-18 已接入订单人民币金额

响应给出 orders.actual（年累计人民币金额）和 orders.series（按实际 PO 日期的累计序列，fraction 与 elapsedFraction 同一坐标）。口径：商机来源、Confirmed / Completed、实际 PO 日期在年初到统计时点之间的 Booking；人民币订单取 amount，外币订单取 Claude `5c44a82` 的 amount_cny，0 视为未填。范围内有一张订单缺人民币金额，年累计金额、S7 金额和销售表 orders 都为数据不足；缺的订单在 orders.missingAmount 计数，get_details(metric=po_missing_amount) 列出，经理在订单页补录后自动恢复。不以系统确认时间或商机预计日期代替实际 PO 日期，不用商机估算冒充订单金额。

页面：S7 显示年累计金额；订单卡片画实际累计曲线（单调平滑：经过每个累计点，两点之间不越界，末段平直到统计日）和按天计划线，页头显示实际 / 目标、达成率和较计划差额；缺日期与缺人民币金额的订单各有一个待补录入口。S7 数量仍按实际 PO 日期归年，缺日期单列待补录；详见 [实际 PO 日期接入](actual-po-date-integration.md)。

## 前端接入修正，不要求 Claude 新增字段

- 预警标题的“9 项”来自演示计算。现有三类 count 各自按商机去重，同一商机可跨类出现，不能相加后声称是“需关注商机总数”。正式标题可直接用“本期需关注”，下方保留三类计数；数据不足也不能当 0。
- 预警详情使用三个现有 metric，按类型展示，不用统一假的记录列表。分类内总数和历史事件条数是不同含义。
- 停滞商机下方的“预算推迟”等句子没有可靠的停滞原因字段。正式版先去掉这类演示说明；如以后展示 Action 标题，可复用现有 Action/历史，不创建停滞原因字段。
- 城市属于客户资料，不代表销售辖区，不能把客户城市拼接到销售姓名下充当辖区。
- 图表独立选销售可再调用一次 get_review，传相同期间和明确的单销售；无需新增接口。区域/市场筛选下个人目标不可分摊，必须遵守现有 not_applicable，不能静默取消筛选后显示成同口径对比。
- 恢复个人目标编辑入口，复用 save_target 和旧页的并发冲突处理；纯视觉预览没有目标持久化。
- 预览里的空数据切换按钮、假金额曲线和示例活动说明只用于设计确认，不进入正式业务页面。

## 联调尚需验证

部署方核对真实站点提交、#35 迁移演练、#36 reason 字段和 CRM Cockpit Target 的 schema；运行站点测试及真实 Manager/Sales/Engineer 会话验证。尤其核验目标持久化/并发版本、历史不足状态、降档原因、同筛选下摘要和分页明细。已有本地通过记录不能代替此步骤。

当前交付状态：正式 Review 展示组件和丢单时金额返回已完成 → Claude 合入测试服区域模块、接中文标签并提供历史覆盖证据 → 在测试站点联调。实际金额数据不具备时保留相同 UI 布局与数据不足状态。


## 统一应用外壳（用户补充确认）

保留左侧功能导航及右上角姓名、角色、语言、通知和账户入口，正式页直接复用 `src/app/AppShell.vue`。角色来自现有 bootstrap，菜单沿用 capability 权限过滤；不在 Review 内复制身份或权限逻辑，不新增后端接口。Philippe 的设计用于 Review 内容区，按侧栏展开后实际剩余宽度重排，空卡不塌缩。独立预览中的演示身份和禁用导航仅用于展示，正式接入继续使用已有真实路由与账户功能。

## 2026-09-18 人民币金额接入

S2–S6 和销售 Pipeline 按 Claude `5543485` 提供的 `amount_cny` 汇总，保持 ¥M 展示；阶段明细、停滞和丢单使用同口径人民币估算。缺值和 0 不当成零金额，不回退到原币金额。S1 仍只计数量；S7 的年累计金额取订单本身的人民币金额（见第 4 点），商机估算不冒充订单实际金额。详见 [接入与验收](cny-amount-integration.md)。
