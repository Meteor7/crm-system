# Opportunities 看板后端对接（2026-09-22）

状态：后端本地完成并通过本地测试，**未推送、未部署**。
分支：`feat/opportunity-board-api`（工作区 `Desktop/CRM-opportunity-board`），基线 `origin/codex/plan-integration` @ `b7cf8ee`。
分工：后端 API、service、保存查询存储和后端测试由 Claude 完成；页面、组件、前端类型、API adapter、mock 和前端测试由 Codex 完成。本分支没有改动任何前端文件。

## 迁移

- 只需 `bench migrate`：新增 DocType `CRM Opportunity Saved Query`（表 `tabCRM Opportunity Saved Query`）。
- 没有数据补丁，也不改动已有表。
- 该 DocType 不给任何角色分配权限，`/api/resource`、`frappe.client` 和 Desk 都无法读写，只能通过下面的自有接口访问。
- `query_name` 和 `definition` 开启了 `ignore_xss_filter`，按原样存储，由输出端负责转义。`query_name` 在 DocType 上没有设为必填，因为 Frappe 会把只含标签的文本（如 `<x>`）判为空值；非空校验由服务端完成。
- `setup/staging_dataset.py` 的 wipe 列表同时清空保存的查询。
- 设备类型目录（2026-09-22 追加，见文末「设备类型目录」）：新增 DocType `CRM Equipment Type`，同样不给任何角色权限；每次 `bench migrate` 的 `after_migrate` 会把商机上已有的设备值登记进目录，并清掉没人用的自定义类型。不改任何商机数据。

## 接口

统一前缀 `/api/method/rayher_crm.api.v1.cockpit.`，返回现有 `{data, meta, warnings}` 封装和错误码。POST 请求沿用现有 adapter 的写法：表单编码，对象参数先转成 JSON 字符串，并带 CSRF 头。

| 接口 | 方法 | 参数 | data |
|---|---|---|---|
| `query_opportunities` | POST | `input` | `{items, asOf, summary, groups}`；分页信息放在 `meta.page / pageSize / total` |
| `get_opportunity_filters` | GET | 无 | `{sales, regions, regionParents, markets, equipment, stages, probabilityLevels, regionReady}` |
| `list_opportunity_queries` | GET | 无 | `{items: SavedQuery[]}`，只返回当前用户自己的查询 |
| `save_opportunity_query` | POST | `input`，可选 `id`、`expectedModified` | 完整的 `SavedQuery` |
| `delete_opportunity_query` | POST | `id`, `expectedModified` | `{id, status: "Deleted"}` |

请求和响应的真实样例见 `docs/opportunity-board/api-sample.json`，取自本地测试站点的 HTTP 调用。

### 权限

- 三个接口族都要求 `deal:view`。Manager、Sales、Engineer 都有这个权限，各自只能看到自己的商机行级范围，与商机列表和详情用的是同一段 SQL 条件（`conditions_for_doctype("CRM Opportunity")`）。
- 最终条件：权限范围 AND `scope` AND 条件组合。`match: "any"` 只在条件之间取 OR，不会越过权限范围或 `scope`。
- 保存的查询只属于创建它的用户。别人的查询 ID 一律返回 `NOT_FOUND`，与不存在的 ID 无法区分。

## query_opportunities 的 input

```ts
{
  scope?: { sales?: string[]; regions?: string[]; markets?: string[]; equipment?: string[] }  // 空数组或省略 = 不限
  match?: "all" | "any"                      // 默认 all
  conditions?: Array<{ field; operator; value } | { match; conditions }> // 根算一级，最多三级、30 条叶子条件
  periodFilter?: { field: "createdAt" | "stageChangedAt" | "poDate"; kind: "week" | "month" | "quarter" | "year"; anchor: string }
  sort?: { field; direction?: "asc" | "desc" }     // 默认 { field: "stageChangedAt", direction: "asc" }
  groupBy?: "region" | "sales" | "stage" | "probabilityLevel" | "equipment" | "market" | null
  page?: number                               // 默认 1
  pageSize?: number                           // 默认 20，上限 200（超过按 200，沿用全站分页规则）
}
```

| field | operator | value |
|---|---|---|
| `stage` | `in` / `not_in` | 阶段值数组（8 个 snake_case 值） |
| `probabilityLevel` | `in` / `not_in` | `low_probability` / `pipeline` / `upside` / `committed` / `pending` |
| `sales` / `region` / `market` / `equipment` | `in` / `not_in` | 用户 ID 或存储值数组 |
| `customerName` | `contains` | 字符串，不区分大小写，`%`、`_` 按普通字符处理 |
| `stageChangedAt` | `before` / `after` / `between` | `YYYY-MM-DD`，或两个日期组成的数组 |
| `stageAgeDays` | `gt` / `gte` / `lt` / `lte` | 0–36500 的整数（JSON number） |
| `amountCny` | `gt` / `gte` / `lt` / `lte` / `between` | 非负十进制字符串，最多两位小数，或两个字符串组成的数组 |

排序字段：`customerName`、`title`、`region`、`sales`（按姓名）、`stage`（漏斗顺序，丢单排最后）、`stageChangedAt`、`stageAgeDays`、`probabilityLevel`（档位高低）、`equipment`、`market`、`amountCny`、`nextAction`（按到期日）。最后按商机 ID 升序，保证顺序稳定。

### 校验（均返回 `VALIDATION_ERROR`，HTTP 422，不会静默忽略）

- 未知的键名：顶层、`scope`、条件、`sort` 里的都算。
- 未知字段、运算符不匹配、值的类型或格式不对、`in` 数组为空、`between` 前大后小。
- 枚举值不在选项里：`stage`、`probabilityLevel`、`region`、`market` 对照固定选项；`sales` 对照 `get_opportunity_filters` 返回的销售选项。`equipment` 对照设备类型目录（预设 + 自定义），按存储值精确匹配。
- `fieldErrors` 的键是出错位置，例如 `conditions[1].value`、`scope.sales`、`sort.field`。保存查询时加上 `definition.` 前缀。
- 限制：条件最多 30 条，根计入最多三级，子组不能为空；每个数组最多 100 个值；文本不超过 140 字。

## 返回的口径

### 单行（`items[]`）

```ts
{
  id, title, accountId, customerName,
  region: string | null,        // 客户主档 custom_crm_region，不用商机 sub_region
  salesId, salesName,
  stage,
  stageChangedAt: string | null,   // UTC ISO
  stageAgeDays: number | null,
  stageUnchangedOver21Days: boolean,   // 新增字段，见下文
  probabilityLevel: string | null,     // 待确认时为 null
  equipment: string | null,            // 商机 tool_type
  market: string | null,               // 客户主档 custom_crm_segment
  amount: string, currency: string,    // 原币金额，两位小数
  amountCny: string | null,            // 销售填写的人民币金额；0 或未填写时为 null
  nextAction: { id, title, due: string | null } | null
}
```

- **日期**按上海自然日解释。`before` / `after` 不包含指定日期，`between` 包含两端。
- **停留天数** = 今天（上海）减去最后阶段变更那天（上海）的自然日差。变更时间未知时返回 `null`，不当作 0；这样的行不会命中任何日期或天数条件。
- **超过 21 天**指停留天数大于 21：满 21 天还不算，22 天才算。它只说明阶段停留得久，不代表 21 天没有跟进客户。
- **`stageUnchangedOver21Days`** 是在契约之外新增的布尔字段，由后端算好。只有开放阶段（S1–S6）才可能为 true，收到 PO 或丢单的商机已经结束，不算超期。建议表格标红直接用这个字段，不要在前端另算一遍。
- **金额**只使用销售填写的 `amount_cny`，不做汇率换算。缺失的金额不会命中任何金额条件（`gte 0` 也不会），在汇总里单独计入 `missingAmountCount`，不当作 0 加总。
- **下一步行动**：未归档、状态为 Open 的行动中到期日最早的一条。无到期日的排在后面，同一天按行动 ID 排序。已完成（Done）的行动不参与。
- **`not_in` 保留空值**：客户主档没有区域的行，会命中 `region not_in ["East China"]`；`in` 不会命中空值。`market` 和 `equipment` 同理。

### summary（覆盖全部匹配记录，与当前页无关）

```ts
{
  count, knownAmountCny, missingAmountCount,
  stageUnchangedOver21DaysCount,  // 仅开放阶段
  unknownStageAgeCount,           // 仅开放阶段：变更时间未知的条数
  byProbability: Array<{ level, count, knownAmountCny, missingAmountCount }>  // 固定 5 项，顺序 low_probability, pipeline, upside, committed, pending
}
```

### groups

- `groupBy` 为 null 时返回 `[]`。否则返回全部分组，每组统计全部匹配记录，不受分页影响。
- `items` 先按组排列、组内按 `sort` 排序，然后再分页。所以逐页读取拼接起来就是完整的分组顺序，导出时可以按 `groups` 的顺序切分工作表。
- 组的顺序：按该字段的自然顺序（阶段按漏斗顺序，概率按档位，其余按名称），空值组排最后。如果 `sort.field` 就是分组字段，组的顺序也跟随排序方向。
- `key`：用作条件值时恰好选中这一组的值。概率待确认的组 key 为 `"pending"`；区域、市场、设备为空的组 key 为 `null`（没有条件能单独选中空值），`label` 为 `"Not set"`。
- `label`：销售组是姓名，阶段和概率组是英文标签，其余是存储值。前端按自身的 i18n 显示，不必直接用这里的英文。

## get_opportunity_filters

- `sales`：Manager 看到的是所有 CRM Sales 用户，加上自己范围内实际出现的商机负责人；Sales 只看到自己；Engineer 看到其可见商机的负责人。按姓名排序。
- `regions`、`markets`、`regionReady` 直接复用 Review 的 `cockpit.options()`，口径完全一致。区域未就绪时 `regions: []`、`regionReady: false`。此时在 `scope.regions`、region 条件或 `groupBy: "region"` 里提交区域都会返回 `VALIDATION_ERROR`；按区域排序仍然允许，行上的 `region` 照常返回客户主档的存储值。`regions` 按销售区域树的顺序列出（上级在前，树外的区域在后），`regionParents` 给出每个值的上级。区域值可以是上级节点：`scope.regions` 和 region 条件的 `in` 表示"属于该节点或其下级"，`not_in` 表示"不属于"；保存的查询里存的是节点本身，不是它当时覆盖的区域。分组和区域列仍是客户自己的区域。
- `equipment`：设备类型目录，和 `opportunities.list_equipment_types` 相同：五个预设在前，然后是自定义类型（按加入顺序）。和市场一样是全量选项，不随权限范围收窄。
- `stages`、`probabilityLevels`：固定枚举，`label` 为英文。

## 保存查询

```ts
SavedQuery = {
  id: string
  name: string
  definition: { scope, match, conditions, sort, groupBy, columns: string[] }   // 已按服务端规则规范化
  modified: string   // UTC ISO，用作 expectedModified
}
```

- `columns` 必填，不能为空、不能重复，取值限于 `customerName`、`title`、`region`、`sales`、`stage`、`stageChangedAt`、`probabilityLevel`、`equipment`、`market`、`amount`、`amountCny`、`nextAction`。如果前端需要其他列，请告诉我加进白名单。
- 定义里不能带 `page` / `pageSize`。服务端也不保存分页位置和结果快照；每次点开都按当前权限重新查询。
- 保存时用与查询相同的规则校验，并规范化后存储：去掉首尾空格、去重、金额补齐两位小数、补上默认排序。
- 名称：去掉首尾空格后 1–80 字，不能含控制字符。名称按原样存储（`<`、`>` 不会被转义），前端必须当作纯文本显示，不能用 `v-html`。同一用户下名称不区分大小写不能重复，重复返回 `CONFLICT`。每个用户最多保存 100 条。
- 新建：不传 `id`。同时传了 `expectedModified` 会返回 `VALIDATION_ERROR`。
- 更新：传 `id` 和 `expectedModified`。缺少 `expectedModified` 返回 `VALIDATION_ERROR`；版本过期返回 `VERSION_CONFLICT`。
- 删除：必须带 `expectedModified`，校验规则与更新相同。
- 已保存的查询在运行时仍会重新校验。例如某个自定义区域或市场后来被删掉，点开这条查询会得到 `VALIDATION_ERROR`，前端应提示用户修改这条查询。
- 预设查询（如“Demo 已完成”“S6 未收到 PO”）由前端提供，不在后端存储。用户需要时可以另存为个人查询。

## 导出

POST `export_opportunities` 接收同一规范化查询，一次返回全部匹配行、汇总、分组和 asOf。前端不再逐页拼接，数据来自同一请求事务。共享查询额外传 `savedQuery: {id, modified}`，列表和导出均重新校验当前访问与版本。

Excel 保留所选列和分组，并增加 Summary 元数据页。人民币以百万元输出，15 位有效数字以内为数值，超出 Excel 精度时使用精确文本，汇总遵守相同规则。日期使用上海业务日历的 Excel 日期，未知值留空；文本不执行公式。完整演示员工116见 [PR10](../superpowers/plans/2026-10-05-philippe-pr10-sharing.md)。

## 联调重点

1. 列表与汇总一致：任意条件下，`summary.count == meta.total`，各分组 `count` 之和等于 `summary.count`。
2. 21 天边界：变更满 21 天的不标红，22 天的标红；变更时间为空的显示为未知，计入 `unknownStageAgeCount`。
3. 缺失金额：`amountCny: null` 的行不参与金额条件，汇总单列 `missingAmountCount`。
4. 分页分组：翻到最后一页再往后，返回空 `items`，但 summary 和 groups 不变。
5. 保存查询的用户隔离：列表仅包含自己的查询和明确共享给自己的只读定义；非所有者更新、删除或再次共享返回 `NOT_FOUND`。
6. Sales 账号即使用 `match: "any"`，也只能查到自己的商机；在 `scope.sales` 里填别人的 ID 会返回 `VALIDATION_ERROR`。

## 测试

- `rayher_crm/tests/test_opportunity_board_rules.py`：纯规则测试，不依赖 Frappe（`python -m unittest rayher_crm.tests.test_opportunity_board_rules`），覆盖校验、上海日期边界、21 天边界、缺失值、AND/OR、排序、分组和汇总。
- `rayher_crm/tests/test_opportunity_board_api.py`：站点集成测试，覆盖行级权限、跨页汇总、筛选选项、区域未就绪、保存查询的用户隔离与版本校验、标准文档 API 拒绝访问、名称按原样保存、超范围输入（`inf` 页码、越界时间戳、超深嵌套 JSON）返回校验错误，以及接口封装。
- HTTP 层另外核对过：Sales 和 Manager 两个账号，看板返回的商机与现有商机列表接口完全一致（ID、阶段、概率、`stageChangedAt`、`amountCny`）；`/api/resource`、`frappe.client.get_list` 和 `reportview` 对保存查询的表一律返回 403，包括查询的所有者本人。

## 设备类型目录（2026-09-22 追加）

商机的设备类型从自由文本改为目录，用法和客户区域一样：从下拉里选五个预设之一，或者选“＋自定义设备类型”手填，新值会加进共享目录，之后所有人都能选。

- **预设**：`Aconca`、`Drakens`、`Kibo`、`Nansi`、`Veymont`（`services/equipment.py` 的 `EQUIPMENT_PRESETS`）。
- **新输入的写法**：和某个预设只差大小写、空格或标点的，存成预设（`NANSI`、`nan-si` → `Nansi`）；和已有自定义类型只差这些的，沿用已有写法；其他的作为新的自定义类型加入目录。中间的连续空格合并成一个。不能为空，不超过 140 字，不能含控制字符和 `<` `>`（Frappe 会改写商机字段里的尖括号）。
- **存储**：商机仍存 `CRM Opportunity.tool_type` 文本，字段类型没变。自定义类型存在 `CRM Equipment Type`，只有 `services/equipment.py` 读写，通用接口一律 403。新类型在保存商机的同一个 savepoint 里登记，保存失败就一起回滚。
- **历史数据按同一设备处理，不改写**：商机保存时如果设备类型没改，原来的写法原样保留。只差大小写、空格或标点的写法算同一种设备（`services/equipment_names.py` 的 `equipment_key`）：看板里 `NANSI`、`nan-si` 的商机显示为 `Nansi`，按 `Nansi` 筛选和分组都能命中；`kibo-4895c` 和 `Kibo 4895C` 同理，显示为目录里登记的那个写法。migrate 时 `sync` 每种设备只登记一次（预设不登记；新类型取最常见的写法），并清掉多余的重复写法；目录表的 `equipment_name` 有唯一索引，补丁 `dedupe_equipment_types` 在建索引前先去重。商机数据不动。
- **待人工确认的清单**：`bench --site <site> execute rayher_crm.setup.equipment_types.report` 只读，列出每个已存的值、商机数和提示：`spelling_of_preset`（只差大小写/空格/标点）、`contains_preset`（如 `Kibo 4895C` 含 `Kibo`）、`same_as`（两个旧值只差这些）。本地测试站点的示例数据里只有 `Kibo 4895C`（8 条商机）需要确认。
- **接口**：`GET /api/method/rayher_crm.api.v1.opportunities.list_equipment_types`，需要 `deal:view`，返回 `string[]`（预设在前）。前端商机新建/编辑、线索转换都用它；读取失败时退回五个预设。
- **看板**：`get_opportunity_filters.equipment` 返回整个目录；`scope.equipment` 和设备条件里不在目录中的值返回 `VALIDATION_ERROR`。因为所有已存的值都在目录里，已保存的查询不受影响；但 migrate 清掉没人用的自定义类型后，引用它的保存查询再运行会报校验错误，和区域一致。
- **比对规范化（审查后补充）**：比对和保存前先做 NFKC（全角字母、数字转半角），并去掉零宽空格、BOM 等不可见字符；只由标点组成的输入（如 `...`、`/`）直接拒绝。
- **并发（审查后补充）**：凡是用到自定义类型的保存，都会先锁住一个固定行（`tabDocType` 里 `CRM Equipment Type` 这一行），再用当前读读取目录；两个请求同时新增同一类型时不会重复登记，新增不同类型时也不会死锁。migrate 时的 `sync_after_migrate` 先提交一次事务，再在同一把锁下读取，不会误删刚被使用的类型。
- **测试**：`tests/test_equipment_types.py`（6 项），并更新了看板规则和接口测试。
- **导出（审查后补充）**：Excel 里的人民币金额在 15 位有效数字内写成数值（PR10 起以人民币百万元输出），可以直接求和；超出精度的金额保留精确文本。XML 不允许的控制字符在写入前去掉，避免整个文件打不开。PR10 全量导出等待响应的默认超时为 120 秒，普通接口保持 30 秒。


## PR09 扩展（2026-10-05）

新增 createdAt、lastActivityAt、poDate 日期条件（before／after／between）和 status 条件（in／not_in；open／won／lost），也可显示及排序这些列。lastActivityIncomplete 表示关联完成活动中存在未知业务日期，该行最后活动日期不参与筛选／排序；已有证据日期仍可显示。业务事实和实质历史沿用 Review 公共读模型，范围先受商机权限约束。

periodFilter 可省略，省略表示没有期间限制。选定字段后，期间与全局范围、根条件组取交集；规范化 anchor 为期间首日，采用上海日期的半开期间。页面显示业务字段与实际日期范围，不把跨页携带的 Review 期间隐含应用到查询。完整演示员工116见 [PR09](../superpowers/plans/2026-10-05-philippe-pr09-queries.md)。


## PR10 共享接口（2026-10-05）

`SavedQuery` 新增 owner、readOnly、recipients，旧查询默认只有所有者可读；recipients 仅向所有者返回。GET get_query_recipients 返回可选人员，POST share_opportunity_query 接收 id、recipients、expectedModified，空名单撤销共享。授权的是定义，查询结果始终使用当前用户自己的商机及来源权限。另存生成不共享的独立副本。
