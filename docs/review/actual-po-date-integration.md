# Review 实际 PO 日期接入（2026-09-18）

## 合并依赖

Claude 的 7d48bc2（父提交 35259c0）提供 Booking.actual_po_date 和确认、补录、更正、回退流程。本次仅接入 Review，不新增业务字段，不修改阶段事件或 Plan 预计 PO 日期。请在 Claude 集成分支保留区域中文标签，合入本次增量后部署并完成真实接口验收；Codex 未部署测试服。

## 统计规则

- source=Opportunity，当前 status 为 Confirmed 或 Completed。
- 按 Booking.actual_po_date 的上海日历日，统计所选参考日期当年 1 月 1 日至截止日（含两端）的 Booking 数。完整周期取周期末日，进行中周期取今天。
- 按当前 CRM Opportunity.opportunity_owner 归属，与当前订单状态一致；不使用 booking_owner，也不回放负责人历史。区域、市场仍读客户主档。
- 补录和更正会重算过去年度；取消或回退到 Pending 会移出统计。替换 Booking 无需新的 po_confirmed 事件也能计入。
- 缺日期不猜年份，单列“PO 日期待补录”。该清单保留销售、区域、市场筛选，不限制年份；只包含上述状态与来源，不包含 Upsell、Pending、Cancelled。
- S1–S6 历史状态、丢单事件、po_confirmed 的写入规则保持不变。实际人民币金额与达成率自 2026-09-18 起按订单人民币金额计算（见 approved-ui-backend-contract.md 第 4 点）。
- 读取前用 get_meta("CRM Booking").has_field("actual_po_date") 检查。旧 schema 不查询新列；S7、销售 PO 数量和待补录数返回 insufficient，reason=actual_po_date_unavailable。新 schema 无匹配订单则返回 ready / 0。不再依赖历史覆盖配置的 po 键。

## 业务接口增量

- get_review.orders.count、pipeline[key=po].count、sales[].poCount 使用同一口径。
- get_review.orders.missingDate: Metric，独立缺日期计数。
- get_details(metric=po) 返回 Booking 行，id/title 为 Booking 编号，kind=booking，at 为实际日期上海零点的 ISO UTC 表示，owner 为当前商机负责人，附 status、opportunityId。
- get_details(metric=po_missing_date) 返回同结构，at=null，复用既有筛选、分页和 Manager 权限。
- 前端待补录入口打开 cockpit 明细，再链接到 /booking/:bookingId，供经理补录。这样保留完整看板筛选范围；无需依赖订单列表对 actualPoDateMissing 的路由解析。bookings.list_bookings 的缺日期筛选保持原样。

## 验收

1. 当年 1 月 1 日、截止日计入；上年最后一天、截止日次日排除。系统确认时间与实际日期跨年时，以实际日期为准。
2. Confirmed 和 Completed 计入；Upsell、Pending 和 Cancelled 排除，包括取消但仍保留日期的订单。
3. 旧订单日期为空显示待补录，打开正确 Booking。补录到当年后计入，更正到上年后移出；所选过去周期也重算。
4. 7→6 回退不再计入，重新确认后按新实际日期计入。取消旧 Booking 后生成的替代 Booking 只计新记录。
5. 商机转给另一销售后，数量和明细归属新负责人；Booking 自己的负责人不改变这一归属。区域、市场筛选与客户主档一致。
6. 新列不存在时页面无 SQL 错误、不显示伪零值；有新列但历史覆盖配置为空时，PO 数量仍可用。
7. 在迁移后的隔离站点运行 test_cockpit_api（含 schema 兼容读取测试），并以 Manager / Sales / Engineer 验证 get_review 和 get_details 权限。

本地验证：前端全量 127 个文件、941 项测试通过；20 项 Python 统计测试通过；Review / AppShell / API 表现层 35 项针对性前端测试通过；类型检查及生产构建通过。浏览器检查了正式 Review + AppShell 的本地夹具，新增说明和待补录入口无溢出。站点集成测试和真实 HTTP 数据验收需要 Claude 部署后执行，本地没有 Frappe 站点。
