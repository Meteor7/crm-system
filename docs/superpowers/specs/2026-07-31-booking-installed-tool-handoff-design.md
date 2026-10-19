# Booking 转 Installed Tool 设计

## 目标

建立 `Booking → Installed Tool` 的 Demo 数据闭环。Sales 可以将已确认的 Opportunity 或 Upsell Booking 转入设备台账、指定负责工程师并补充设备主数据；Booking 保留且自动进入 Completed。

## Booking 来源与状态

- 来源仅保留 `Opportunity` 与 `Upsell`。
- `Opportunity` 必须关联一个 Won Opportunity，并继承其客户、设备与 Sales Owner。
- `Upsell` 直接选择客户与联系人，不要求关联 Opportunity 或现有 Installed Tool。
- 状态为 `Pending / Confirmed / Completed / Cancelled`。
- 只有 `Confirmed` Booking 可以转 Installed Tool。
- 转出完成后 Booking 状态变为 `Completed`，记录 `installedToolId` 与转出时间，不能重复转换。

## 转出表单

必填字段：

- 客户厂区：限定 Booking 客户名下厂区。
- 负责工程师：可选演示员工14（FAE）或演示员工15（设备工程师）。
- Serial Number：Installed Tool 全局唯一。
- 设备型号：从 Booking 设备需求预填，可修改。

选填字段：

- 现场位置
- Sales Order
- Contract
- Software
- Firmware
- Configuration

未填写的选填字段在设备台账中显示“待确认”。

## Installed Tool 初始记录

- 状态：`Delivery Preparation`
- 生命周期：FAT 为 Current；Shipment、Installation、SAT、Warranty 为 Waiting。
- 保留来源 Booking、来源 Opportunity（如有）、客户、厂区、Sales Owner 与负责工程师。
- 软件、固件、演示员工116、现场位置等字段使用转出表单值或“待确认”。

## Installed Tools 页面

- 删除客户设备、量产运行、交付进行中、质保临期四张统计卡。
- 增加筛选栏：
  - 关键词：编号、Serial Number、型号。
  - 客户。
  - 状态。
  - 负责工程师。
  - 重置。
- 新转入设备立即出现在列表并可查看 FAT 起始生命周期。

## 权限与边界

- 具有 `deal:write` 的 Sales、Sales Manager、CRM Administrator 可以执行转出。
- 工程师只能查看其原有权限范围内的数据，本轮不增加工程师写入能力。
- Frappe 适配器返回明确的 `NOT_IMPLEMENTED`，本轮只证明 Mock Demo 的界面与数据闭环。

## 验收

- Opportunity 与 Upsell Booking 均可创建。
- 两种来源的 Confirmed Booking 均可转 Installed Tool。
- 非 Confirmed、已转出或重复 Serial Number 会被拒绝。
- 转出后 Booking 保留并显示 Completed 与 Installed Tool 编号。
- Installed Tools 筛选栏可按关键词、客户、状态、工程师组合过滤。
- 原四张统计卡不再显示。
