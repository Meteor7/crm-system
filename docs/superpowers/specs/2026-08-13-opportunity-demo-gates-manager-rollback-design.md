# 商机 Demo 自动门禁与 Manager 回退设计

日期：2026-08-13
状态：已确认（2026-08-14 澄清：纯状态机逻辑，不在 Opportunity 增加 Demo 链路展示）

## 1. 目标

把商机、Demo Request 和 Demo Test（Evaluation）串成一个不可手工越过的业务状态机：

1. 新建 Demo Request 时必须关联一个商机。
2. 成功新建 Request 后，商机由“需求发现”自动进入“技术确认”。
3. Request 经 Manager 审批通过并成功创建 Evaluation 后，商机由“技术确认”自动进入“Demo验证”。
4. Evaluation 完成全部门禁并进入 `Accepted` 后，商机由“Demo验证”自动进入“预算审批”。
5. “技术确认”和“Demo验证”不能通过商机编辑表单或普通商机更新接口手工进入、离开或跳过。
6. 只有 Manager 能通过独立回退动作把商机退回更早阶段；回退必须填写原因并写入历史。

本设计只约束演示员工152产品入口和业务 API，不扩展到主动演示员工106 Frappe 通用 REST 请求的攻击面。

## 2. 业务语义

“Request 通过”固定解释为：Manager 将 Demo Request 从 `Pending` 审批为 `Converted`，且 Evaluation 已在同一事务内创建成功。

“Demo Test 通过”固定解释为：Evaluation 按现有流程完成测试、报告和评审门禁，最终状态进入 `Accepted`。单个 Test Run 的 `Completed` 只满足 Evaluation 的内部门禁，不直接推进商机。

拒绝结果不自动把商机改为 `Lost`：

- Request 被拒绝时，商机保留在“技术确认”。
- Evaluation 被拒绝时，商机保留在“Demo验证”。
- 页面明确显示失败原因和当前阻塞项，由业务人员决定重开新的 Request，或由 Manager 回退。

## 3. 唯一合法的自动推进链

| 当前商机阶段 | 业务事件 | 新阶段 | 触发者 |
| --- | --- | --- | --- |
| 需求发现 | 成功创建已关联的 Demo Request | 技术确认 | 后端事务自动推进 |
| 技术确认 | Request 审批通过，且 Evaluation 创建成功 | Demo验证 | 后端事务自动推进 |
| Demo验证 | Evaluation 进入 Accepted | 预算审批 | 后端事务自动推进 |

这些转换不能由 `update_strategy_opportunity`、编辑弹窗、Mock adapter 或任何普通“下一阶段”按钮完成。

“预算审批”之后保留现有顺序推进规则：预算审批 → 报价 → 采购流程 → Won。`Lost` 保留现有演示员工152业务入口，但必须遵守现有权限和审计。

## 4. 新建 Request 的强制关联

创建 Demo Request 时：

- `opportunity` 改为必填；前端、API 校验和 DocType schema 三层保持一致。
- 商机必须存在、当前用户必须可访问，并且商机的 Account 必须等于 Request 的 Account。
- 只允许对当前处于“需求发现”或“技术确认”的商机新建 Request。
- 若商机处于“需求发现”，Request 与商机阶段变更必须在同一个 savepoint 内成功或一起回滚。
- 若商机已经处于“技术确认”，创建新 Request 是幂等兼容场景，不重复写阶段历史。
- 若商机已经到“Demo验证”或更后阶段，拒绝创建新 Request；如确需重测，Manager 先执行有审计的阶段回退。
- 允许同一商机先后存在多个 Request，用于被拒后的重新申请或回退后的重新验证；每个 Request 仍最多生成一个 Evaluation。

历史数据兼容：既有未关联 Request 可查看，但不得继续提交、审批或创建 Evaluation。必须先通过受控补链动作关联到同 Account 的商机；已经终态且未关联的历史记录只显示数据质量警告，不反向猜测或自动绑定。

## 5. Manager 专用回退

新增独立能力 `deal:rollback` 和独立接口 `rollback_opportunity_stage`：

- 仅 Manager 拥有，Sales 和 Engineer 均无此能力。
- 目标阶段必须严格早于当前阶段，禁止用回退接口向前推进。
- `reason` 必填，去除空白后必须有有效内容。
- 在行锁内重新读取当前阶段，使用乐观版本或等价冲突检查；过期页面提交返回 409。
- 回退写一条明确的阶段历史，包含原阶段、目标阶段、操作者、时间和原因。
- 允许 Manager 从 Won/Lost 重开，但仍只能回到更早阶段。
- 回退不删除、不修改既有 Request、Evaluation、报告或测试证据。
- 旧证据不会令商机在回退后立即“弹回”到后续阶段；必须发生新的合格业务事件。例如退回“技术确认”后，需要新 Request 再次审批通过，才能重新进入“Demo验证”。

前端仅对 Manager 展示“阶段回退”动作；自动门禁阶段不展示普通“推进阶段”按钮。

## 6. 后端事务与并发规则

三个自动推进点都在原业务 mutation 的同一个 savepoint 内完成，并统一遵循：

1. 先锁定商机行，再锁定或更新 Request/Evaluation，所有入口使用相同锁顺序，避免死锁。
2. 锁内重新校验关联、Account、当前阶段和终态。
3. 业务对象、商机阶段、历史和通知要么全部成功，要么全部回滚。
4. 重复提交同一事件不得重复推进、重复创建 Evaluation 或重复写相同历史。
5. 若商机已处于目标阶段之后，合法重复事件不得使其回退；返回当前真实状态。
6. 若商机异常落后于事件要求，例如 Evaluation Accepted 时商机仍在“技术确认”，整个事件失败并返回稳定 409，不能悄悄跨越缺失门禁。
7. 任一通知或历史写入失败时不得留下半完成的 Request、Evaluation 或商机阶段。

自动推进使用内部专用函数，不暴露可由客户端直接指定目标阶段的公共参数。普通商机更新接口发现阶段变化时执行显式白名单：自动门禁转换一律返回 422；只允许预算审批之后的顺序推进和现有 Lost 规则。

## 7. 前端边界

关联关系只服务于后端状态机，不在 Opportunity 详情新增 Demo Request、Evaluation、Test Run 或门禁说明板块。Request 和 Test 的详情仍只在 Demo 模块查看。

前端规则：

- Opportunity 编辑弹窗移除可编辑阶段下拉框，只读显示当前阶段。
- “需求发现”“技术确认”“Demo验证”均不提供手工推进按钮。
- Demo 模块完成自动推进后，Opportunity 按现有刷新方式显示新的当前阶段；不增加跨模块详情组件。
- Manager 的回退弹窗只列出更早阶段，并强制填写原因。
- 所有 mutation 失败保留原 UI 数据，区分 409 冲突、422 业务门禁、403 权限和普通接口错误，并显示 Request ID。
- 快速切换商机或重复点击时使用请求序号/提交锁，旧响应不得覆盖新页面。

## 8. 必须封堵的演示员工152业务漏洞

| 漏洞 | 防线 |
| --- | --- |
| 编辑商机时直接选择 Demo验证/预算审批 | 前端移除阶段编辑；普通 API 拒绝自动门禁转换 |
| 调用“下一阶段”跳过 Request/Test | 自动阶段不渲染按钮；后端显式拒绝 |
| Request 不关联商机 | schema、前端和服务三层必填 |
| Request 关联其他 Account 的商机 | 锁内校验 Account 一致性 |
| 重复审批生成多个 Evaluation | Evaluation 唯一约束、行锁和终态重检 |
| 并发审批重复推进或重复历史 | 锁内幂等判断和唯一事件语义 |
| Evaluation 关联链串到另一商机 | 只沿 Evaluation → Request → Opportunity 推导，并锁内复核 |
| 旧页面把新阶段覆盖回去 | 版本冲突返回 409 |
| 自动事件把已到后续阶段的商机回退 | 只前进、不回退；已越过目标时保持原阶段 |
| Manager 回退后旧 Accepted 证据立即自动推进 | 仅新发生的合格事件触发，不扫描旧证据回填 |
| Request/Evaluation 成功但商机推进失败 | 同一 savepoint 原子回滚 |
| Mock 测试通过而 Frappe 行为不同 | Mock adapter 同步规则，并以真实后端测试为最终门禁 |

## 9. 测试策略

先写失败测试，再写实现。

后端：

- Request 缺少 Opportunity、跨 Account、错误阶段均返回稳定 422。
- 创建 Request 原子推进到技术确认；故障注入后 Request 和阶段均不残留。
- Request Converted + Evaluation 创建原子推进到 Demo验证；拒绝不推进。
- Evaluation Accepted 原子推进到预算审批；Rejected 不推进。
- 普通更新 API 无法手工进入、离开或跳过自动门禁阶段。
- Manager 可回退且历史含原因；Sales/Engineer 返回 403；并发旧版本返回 409。
- 重复审批、并发审批、重复 Accepted 不重复 Evaluation 或历史。
- Manager 回退后旧证据不触发自动前进，新 Request 的新事件可以再次推进。
- 已在更后阶段时重复事件不回退；异常落后时整笔事件失败。

前端：

- Demo Request 表单强制选择商机，并只列当前 Account 下可用商机。
- 商机编辑器无阶段选择器。
- 三个自动阶段均无手工推进按钮。
- 只有 Manager 看见回退按钮；原因必填；冲突不污染页面状态。
- Mock 与 Frappe adapter 对新增契约行为一致。

验收顺序：相关前端单测、相关后端模块测试、前端全量、生产构建、Backend JUnit 门、真实 `.test` HTTP 场景、Manager/Sales/Engineer 浏览器验收。

## 10. 完成标准

- 三个自动推进事件均有事务、并发和失败回滚证据。
- 所有演示员工152 UI 和业务 API 均无法绕过技术确认或 Demo 验证。
- 只有 Manager 可以带原因回退，且旧证据不会造成状态反弹。
- 新 Request 不能脱离商机存在，跨 Account 关联被拒绝。
- Opportunity 不增加 Demo 链路展示，只反映状态机产生的当前阶段。
- 新增测试与现有全量测试全部通过，测试失败能够真实阻断外层命令。
