# Contacts 主数据与销售关联设计

**日期：** 2026-07-28
**状态：** 设计已确认，待实施计划
**范围：** 当前 Vue/TypeScript CRM 前端、Mock Adapter 数据闭环，以及与现有 Frappe Contact / CRM Opportunity Stakeholder 模型的接口边界

## 1. 背景与目标

当前项目已经存在客户级 `ContactDto`、关键人与组织关系页面，以及 Opportunity 内独立维护的 Stakeholder 数据。两套数据没有共享联系人 ID，Booking 与 Demo Request 仍保存联系人姓名文本，拜访也没有结构化客户参与人，因此会产生重复人员、信息不一致和跨模块无法追溯的问题。

本次将现有“关键人”升级为 Sales 下的 **Contacts / 联系人** 主模块，并建立以下单一事实来源：

1. 联系人基础资料只在 Contacts 主档维护。
2. Opportunity、Booking、Demo Request 和拜访通过联系人 ID 引用主档。
3. Opportunity 的购买角色、影响力和支持态度保留在机会关联记录中，不覆盖联系人主档。
4. Contacts 列表点击姓名进入独立详情子页，不使用抽屉。
5. 联系人详情页能够跳转到所属客户、厂区、汇报对象和所有关联销售记录。
6. 现有 Opportunity 关键人完整同步到 Contacts，不丢弃无法自动匹配的数据。

## 2. 交付边界

当前 `.env.local` 使用 `VITE_API_ADAPTER=mock`。本次实现必须在 Mock Demo 中形成可操作、可验证的完整闭环，同时保持 `CrmApi` 接口可以由 Frappe Adapter 实现。

现有归档 Frappe 方案已经使用：

- Frappe Core `Contact` 作为联系人主档；
- `Dynamic Link` 将 Contact 关联到 Customer；
- `CRM Opportunity Stakeholder.contact` Link 指向 Contact；
- `(opportunity, contact)` 唯一约束防止同一联系人重复进入同一商机。

本次不把 Mock 成功描述为正式 Frappe 后端完成。若当前后端没有 Contacts 写接口，Frappe Adapter 必须返回明确的 `NOT_IMPLEMENTED`，不能静默保存到浏览器或演示员工106成功。

首版不包含 Campaign、群发邮件、标签管理、Cases、文件上传和联系人 CSV 导入。这些 Salesforce 能力不属于当前销售闭环的必要范围。

## 3. 页面与路由

### 3.1 Sales 导航

Sales 模块新增：

- `Contacts / 联系人`
- 路径：`/contacts`
- 可见能力：`contact:view`

现有 `/stakeholders` 路由兼容重定向到 `/contacts`，不再保留第二套关键人入口。

### 3.2 联系人列表页

联系人列表遵循当前项目的海军蓝、暖白、琥珀色设计语言，借鉴 Salesforce 的高密度列表，而不是复制 Salesforce 外壳。

默认列：

- 姓名；
- 所属客户；
- 所属厂区；
- 职位 / 部门；
- 电话；
- 邮箱；
- 联系人负责人；
- 在职状态；
- 最近更新时间。

支持：

- 按姓名、客户、职位、电话、邮箱搜索；
- 按客户、厂区、负责人、状态筛选；
- 新增联系人；
- 点击姓名进入 `/contacts/:contactId`；
- 空状态、加载状态、权限拒绝和请求错误；
- 列表数量以联系人明细集合为事实来源。

### 3.3 独立联系人详情子页

路由：`/contacts/:contactId`

页面顶部：

- 返回联系人列表；
- 姓名、客户、职位、Owner、状态；
- `新建 Opportunity`；
- `记录拜访`；
- `编辑联系人`。

主体采用三栏结构，小屏改为单栏：

1. **联系人资料与组织关系**
   - 客户、厂区、职位、部门、电话、邮箱、关系强度、汇报对象、状态；
   - 客户、厂区和汇报对象均为真实路由链接；
   - 组织关系只展示已维护的数据，不推断缺失汇报线。
2. **活动时间线**
   - 汇总 Opportunity 联系人关系变更、拜访、Demo Request 和 Booking；
   - 每项显示来源、日期、标题和业务摘要；
   - 点击进入来源记录。
3. **关联业务**
   - Opportunities；
   - 拜访记录；
   - Demo Requests；
   - Bookings；
   - 显示真实计数和最近记录；
   - `查看全部` 跳转到目标模块并携带联系人筛选参数。

不使用抽屉作为联系人详情承载方式。

## 4. 数据模型

### 4.1 Contact 主档

联系人主档包含：

```ts
type ContactStatus = 'Active' | 'Left Company' | 'Archived'

interface ContactDto {
  id: string
  accountId: string
  siteId?: string
  name: string
  title: string
  department: string
  phone?: string
  email?: string
  reportsToContactId?: string
  relationship: 'Strong' | 'Developing' | 'Weak'
  owner: string
  status: ContactStatus
  dataQuality: 'Complete' | 'Needs Review'
  updatedAt: string
}
```

规则：

- 每位联系人只有一个当前所属客户；
- 所属厂区可为空，但必须属于同一客户；
- 汇报对象必须属于同一客户；
- 禁止自我汇报和循环汇报；
- `Left Company` 与 `Archived` 联系人保留历史关联，但不能新增到业务记录；
- 已有关联的联系人不做硬删除；
- 快速新增默认继承当前客户和客户负责人。

### 4.2 Opportunity 联系人关联

```ts
interface OpportunityContactDto {
  id: string
  opportunityId: string
  contactId: string
  buyingRole: string
  influence: 'High' | 'Medium' | 'Low' | 'Unknown'
  attitude: 'Champion' | 'Supportive' | 'Neutral' | 'Detractor' | 'Unknown'
  isCoach: boolean
  coverageEvidence: string
  winResult?: string
  opportunityNotes?: string
}
```

规则：

- 一个 Opportunity 可以关联多位联系人；
- 同一联系人只能在同一 Opportunity 出现一次；
- 可在不同 Opportunity 中拥有不同购买角色、影响力和态度；
- Opportunity 页面选择联系人时，只显示该 Opportunity 客户下的 Active 联系人；
- 当前表单可快速新增联系人，保存后自动加入 Contacts 主档并完成 Opportunity 关联。

### 4.3 拜访联系人关联

```ts
interface VisitParticipantDto {
  contactId: string
  isPrimary: boolean
  meetingRole?: string
}
```

规则：

- 一次拜访可以关联多位客户参与人；
- 最多一位主要联系人；
- 参与人必须属于拜访客户；
- 从联系人详情点击“记录拜访”时，自动带入客户和当前联系人。

### 4.4 Booking 与 Demo Request

- Booking 增加 `primaryContactId`；
- Demo Request 增加 `primaryContactId`；
- 两者各关联一位主要联系人；
- 选择范围限制为当前客户下的 Active 联系人；
- 表单显示姓名、职位和联系方式，但持久化事实来源为联系人 ID；
- 已生成的 DOCX/PDF 在生成时写入当时的联系人显示值，历史文件不随主档修改而变化；
- 旧的 `customerContact`、`contactPerson` 文本仅用于迁移兼容，迁移完成后不再作为新数据入口。

## 5. API 与聚合

`CrmApi` 增加或调整：

```ts
listContacts(query: ContactListQuery): Promise<ApiResponse<PageData<ContactSummaryDto>>>
getContact(id: string): Promise<ApiResponse<ContactDetailDto>>
saveContact(input: ContactInput): Promise<ApiResponse<ContactDto>>
listOpportunityContacts(opportunityId: string): Promise<ApiResponse<OpportunityContactDto[]>>
saveOpportunityContact(opportunityId: string, input: OpportunityContactInput): Promise<ApiResponse<OpportunityContactDto>>
deleteOpportunityContact(opportunityId: string, linkId: string): Promise<ApiResponse<{ id: string }>>
```

`ContactDetailDto` 聚合：

- 联系人主档；
- 所属客户与厂区摘要；
- 汇报对象与直接下属；
- Opportunity 关联；
- 拜访关联；
- Demo Request 关联；
- Booking 关联；
- 按时间倒序的活动时间线。

所有聚合都以 `contactId` 为连接键，不使用姓名模糊连接。

## 6. 操作与数据流

### 6.1 新建联系人

1. 用户从 Contacts、Opportunity、Booking、Demo Request 或拜访表单发起新增。
2. 从业务表单发起时，客户固定为当前业务对象客户，不能切换到其他客户。
3. 用户填写联系人主档字段并保存。
4. API 先执行权限、客户范围、厂区归属、重复提示和汇报关系校验。
5. 保存成功后，Contacts 立即可检索到该联系人。
6. 原业务表单自动选中新建 Contact ID；如果业务对象本身尚未保存，只更新表单草稿，不提前创建关联记录。
7. 后续业务对象保存成功时再写入 Opportunity、拜访、Booking 或 Demo Request 关联。

联系人创建成功但业务对象保存失败时，联系人主档仍然保留，并在表单中保持选中，用户可以修正业务字段后重试；系统不能重复创建第二位同名联系人。

### 6.2 Opportunity 关键人维护

1. 用户在 Opportunity 中选择当前客户下的 Active 联系人。
2. 表单只编辑机会级购买角色、影响力、态度、覆盖证据和备注。
3. 保存时写入 `OpportunityContactDto`，不复制姓名、职位、电话和邮箱。
4. 联系人详情通过 Contact ID 聚合到该 Opportunity。
5. 从 Opportunity 点击联系人姓名进入联系人详情子页。

### 6.3 Booking、Demo Request 与拜访

- Booking 与 Demo Request 选择一位主要联系人，保存 `primaryContactId`。
- 拜访选择多位参与人，并可标记一位主要联系人。
- 更换业务对象客户时，已经选择的其他客户联系人必须清空并提示用户重新选择。
- 读取记录时由 API 返回联系人摘要供页面展示；主档不存在时显示数据质量错误，不回退为自由文本输入。
- 所有关联写入成功后，联系人详情的计数和时间线必须同步刷新。

## 7. 路由跳转协议

联系人详情页的“查看全部”使用以下查询参数：

- 客户：`/accounts?accountId=<accountId>`
- Opportunity：`/opportunities-booking?view=opportunities&contactId=<contactId>`
- Booking：`/opportunities-booking?view=bookings&contactId=<contactId>`
- Demo Request：`/demo-requests?contactId=<contactId>`
- 拜访：`/visits?contactId=<contactId>`
- 汇报对象：`/contacts/<reportsToContactId>`

目标页面必须读取查询参数并应用筛选；如果 ID 不存在、无权限或不属于当前数据范围，应显示明确提示并保留页面可操作性，不能显示其他客户数据。

从目标页面返回联系人详情时使用标准浏览器历史，不维护第二套自定义返回栈。

## 8. 数据迁移

迁移按以下顺序执行：

1. 现有客户级 `ContactDto` 直接升级为 Contacts 主档。
2. 遍历所有 Opportunity Stakeholder。
3. 在同一客户内优先按规范化邮箱匹配。
4. 无邮箱时按“规范化姓名 + 职位”匹配。
5. 唯一匹配时复用 Contact ID，并创建 Opportunity 联系人关联。
6. 无匹配时创建 `Needs Review` 联系人主档，再建立关联。
7. 多个可能匹配时不自动合并；保留独立记录并标记待确认。
8. 保存来源 Stakeholder ID 或稳定迁移键，使迁移幂等。

迁移不丢弃现有关键人，不跨客户合并同名人员，不根据姓名猜测邮箱、电话、汇报线或厂区。

## 9. 权限

- `CRM Administrator`：全部联系人读写、处理重复项、调整负责人。
- `Sales Manager`：本团队联系人读写，可在团队内调整负责人。
- `Sales User`：负责客户范围内联系人读写。
- `Management Viewer`：全部只读。
- `FAE / Applied Engineer` 与 `Equipment Engineer`：不进入完整 Contacts 模块；只在被分配的 Demo、拜访或客户上下文中查看必要联系人信息，不能编辑。

前端能力用于体验控制；Mock Adapter 和正式 Frappe 写接口必须再次执行权限与客户范围校验。

能力命名统一为：

- `contact:view`
- `contact:write`
- `contact:merge`

旧的 `stakeholder:view`、`stakeholder:write` 在迁移期兼容映射，实施完成后不再作为页面级能力名称。

## 10. 错误处理与数据质量

- 联系人与业务对象客户不一致：拒绝保存，返回 `CONTACT_ACCOUNT_MISMATCH`。
- 联系人不存在：返回 `CONTACT_NOT_FOUND`。
- 联系人已演示员工166或归档：拒绝新增关联，返回 `CONTACT_INACTIVE`。
- Opportunity 重复关联：返回 `DUPLICATE_OPPORTUNITY_CONTACT`。
- 自我或循环汇报：返回 `INVALID_REPORTING_LINE`。
- 目标路由无权限：显示 denied 状态，不泄露联系人或客户摘要。
- 详情聚合部分失败：保留联系人主档，相关区块显示独立错误，不把缺失集合伪装为零。
- 没有电话、邮箱、厂区或汇报对象时显示“—”，不生成虚构数据。

## 11. 并发修改策略

实施前重新读取工作树和目标文件修改时间。若演示员工114 subagent 正在修改同一文件：

1. 不覆盖未完成内容；
2. 先实施不重叠的领域模型、测试或新增组件；
3. 等待目标文件稳定后重新读取最新内容；
4. 以最新工作树为基础做小范围补丁；
5. 不使用 `git reset --hard`、`git checkout --` 或整文件覆盖恢复。

## 12. 测试与验收

### 12.1 领域与 API 测试

- Stakeholder 到 Contact 的唯一匹配、无匹配和疑似重复迁移；
- 迁移幂等；
- 同客户与跨客户联系人选择约束；
- Opportunity 多联系人与重复关联保护；
- 拜访多人、唯一主要联系人；
- Booking / Demo Request 主要联系人写入；
- 快速新增联系人后自动选择；
- 演示员工166与归档联系人保留历史但不能新增关联；
- 汇报关系自我与循环保护；
- 角色权限和客户范围；
- 联系人详情聚合与关联计数。

### 12.2 页面与路由测试

- Sales 导航显示 Contacts；
- `/stakeholders` 重定向；
- 列表筛选、空状态、错误状态；
- 点击姓名进入 `/contacts/:contactId`；
- 独立详情页不渲染为抽屉；
- 客户、厂区、汇报对象跳转；
- Opportunity、Booking、Demo Request、拜访筛选跳转；
- 从联系人详情快速新建 Opportunity 和拜访；
- 无权限或无效 ID 不泄露数据。

### 12.3 工程验证

- 运行 Contacts、Opportunity、拜访、Demo Request、Booking 和权限相关 Vitest；
- 运行 `vue-tsc --noEmit`；
- 运行生产构建；
- 启动本地浏览器，验证列表、详情子页、快速新增和所有关联跳转；
- 分别使用 Sales User、Sales Manager、Management Viewer 和工程角色验收可见性与写权限。

## 13. 完成标准

以下条件全部满足才算完成：

1. Sales 中存在可用的 Contacts 列表页和独立详情子页。
2. 现有关键人数据已迁移到联系人主档，不再保留未关联的 Opportunity 姓名副本。
3. Opportunity、Booking、Demo Request 和拜访通过 Contact ID 关联。
4. 联系人详情能展示真实关联数量，并跳转到已应用联系人筛选的目标模块。
5. 快速新增不会产生孤立联系人或跨客户关联。
6. 权限、异常、空状态和并发修改策略经过验证。
7. 定向测试、类型检查、构建和浏览器验收均有当前运行证据。
8. Mock 完成与正式 Frappe 后端完成边界在交付说明中明确区分。
