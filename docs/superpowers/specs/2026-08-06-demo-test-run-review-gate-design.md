# Demo Test Run Review Gate Design

**日期：** 2026-08-06
**状态：** 已确认，进入实施

## 目标

Demo Test 从 `Testing` 推进到 `Internal Review` 前，必须至少存在一条状态为 `Completed` 的 Test Run。仅有 `Planned` Test Run 或没有 Test Run 时不得推进。

## 完成判定

沿用现有 Test Run 契约：测试日期、Wafer Lot、Wafer 数量、缺陷捕获率、误报率、Throughput WPH 和结果摘要均有效时，Test Run 状态为 `Completed`。任何指标缺失时不视为完成。

## 行为设计

- Test Execution 页面保留“完成 Test Execution”按钮。
- 无 Completed Test Run 时按钮禁用，并在操作区域显示“请先完成至少一条 Test Run，再进入 Internal Review”。
- 保存完整 Test Run 并刷新 Evaluation 后，按钮立即开放。
- Mock API 和 Frappe 服务均在 `Testing -> Internal Review` 边界执行相同校验，绕过页面调用接口仍会被拒绝。
- 其他状态推进、Test Run 录入和 Customer Review 报告校验保持不变。

## 错误处理

后端与 Mock 使用现有 `INVALID_TRANSITION` 业务错误，消息明确指出 Completed Test Run 前置条件。页面继续使用现有行内操作错误区域，不切换为整页加载失败。

## 测试范围

- Evaluation Workspace：无 Completed Test Run 时按钮禁用并显示提示；存在 Completed Test Run 时可用。
- Mock API：无记录及仅 Planned 记录均拒绝，Completed 记录允许。
- Frappe 服务：直接状态推进同样执行门禁。

## 非目标

- 不修改 Test Run 字段定义。
- 不要求所有 Test Run 完成。
- 不改变 Internal Review 到 Customer Review 的报告前置规则。
