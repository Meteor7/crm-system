# CRM Quotation 模块设计

**日期：** 2026-08-10

## 目标

在 Sales 模块新增独立 Quotation 功能，服务于 Opportunity 报价阶段。一个 Opportunity 只允许一份报价主档，修改通过 V1、V2、V3 版本演进；草稿实时保存并同步模板预览，发布后生成不可变正式 PDF。数据必须落入 Frappe DocType 和数据库，不能以 Mock/localStorage 作为正式数据源。

## 用户体验

- Sales 导航顺序：客户档案、联系人、Leads&Opportunities、Quotation、Booking、拜访与 Action。
- 列表复用 Contacts 的 PageHeader、FilterBar、白色表格卡片、整行点击和状态徽标交互。
- 列表核心列：Name（Ref No. + 客户）、Opportunity、上一次修改日期、Status。
- 详情页复用联系人/客户档案的页头、横向摘要与 SectionCard；默认展示最新版本，并设“历史版本”区域。
- 可从 Quotation 列表新建并选择 Opportunity，也可从 Opportunity 详情进入同一编辑器。

## 数据模型

- `CRM Quotation`：一份 Opportunity 对应一个主档；保存 `ref_no`、Opportunity、Customer、Sales owner、最新版本、最新正式版本及当前状态。
- `CRM Quotation Version`：独立顶层 DocType，保存完整报价快照、版本号、状态、金额、商务条款、客户反馈和私有 PDF。
- `CRM Quotation Item`：Version 的子表。`Device` 为父项；`Accessory` 通过 `parent_device_key` 指向设备，固定两级。
- `CRM Quotation Payment Term`：Version 的子表，保存顺序、比例、触发条件和说明。
- 发布版本不可修改。新草稿复制最新正式版本；新版本发布后，旧正式版本变为 Superseded。

## 业务规则

- 允许 Opportunity 早期阶段创建草稿，但只有进入“报价”阶段后才可发布。
- 一个 Opportunity 只能有一个报价主档；Ref No. 手工填写、非空、全局唯一；所有版本共享 Ref No.
- 设备字段：设备名称、型号、规格/描述、数量、含税单价。
- 配件字段：配件名称、型号、规格/描述、Included/Charged、整份报价总数量、含税单价。
- 设备金额 = 数量 × 含税单价；收费配件金额 = 总数量 × 含税单价；Included 配件金额为 0。
- 全部价格为 CNY 含税价，不拆税额。整单保留小计，折扣可选择百分比或固定金额，二者互斥，折后总价不得小于 0。
- 付款节点默认 30/30/30/10，可增删、编辑、排序；发布时比例合计必须为 100%。
- 商务条款使用结构化字段：Incoterm（默认 FOB Shanghai）、交期、质保、有效期、安装、培训、文档、包装。
- 客户从 Opportunity 固定带出；ATTN 和地址只能选择该客户的有效联系人/站点。正式发布时保存不可变文本快照。
- 草稿停止输入约 1 秒后自动保存；旧请求不得覆盖新请求；失败时保留上次成功预览。草稿预览无水印，但不生成可下载正式 PDF。
- 正式 PDF 文件名为 `<Ref No.>-V<version>.pdf`，存为私有文件并永久关联版本。
- 当前最新正式版本可由 Sales 标记 Accepted/Rejected，必须填写客户反馈日期和备注；旧版本只读。
- Accepted 自动把 Opportunity 推进到“采购流程”；Rejected 不改变 Opportunity。
- 有效期届满自动显示 Expired，不改变 Opportunity；继续报价需创建新版本。

## 权限

- Manager：查看全部报价并可维护。
- Sales：仅查看和维护本人负责的报价，可自行发布，无强制审批。
- Engineer：无模块、详情、API 和文件访问权限。
- 权限和行级范围必须由后端强制执行。

## 技术边界

使用 rayher_crm 自定义 DocType、服务层和 v1 API；不启用 ERPNext 标准 Quotation。前端通过 `CrmApi` 与 Frappe adapter 调用真实接口。PDF 由服务端根据同一版本快照渲染，预览与正式文件共享版式数据。
