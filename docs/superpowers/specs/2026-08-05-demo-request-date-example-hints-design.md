# Demo Request 日期控件与示例提示设计

## 目标

降低 Demo Request 新增和编辑时的格式错误：将 `Timing` 改为日期选择器，并为表单中的文本输入项提供统一、可直接参考的灰色 `e.g. ` 示例。

## 范围

- 仅修改 Demo Request 新增与编辑共用表单。
- `Timing` 使用原生 `input[type="date"]`，提交值保持 `YYYY-MM-DD`。
- 集中维护 `DEMO_REQUEST_HINTS`，不在组件模板中分散硬编码示例。
- 为以下字段提供以 `e.g. ` 开头的示例：Industry、Size & Shape、Material、Specific Request、What to Detect / Measure、Expected Results、Other Tools、Primary Tool、Complementary Tool、Key Success Factors、Internal Questions、Customer Questions，以及 Wafer Details 的六个字段。
- Company Name、Primary Contact、Sales Contact、Demo Owner 等选择控件继续使用选择提示，不增加 `e.g.`。
- Customer Expected Date 保持现有日期选择器。
- Contact Person 继续由后端根据 Primary Contact 生成，不新增手工输入要求。

## 示例文案

- Industry: `e.g. Semiconductor Frontend Fab`
- Size & Shape: `e.g. 300 mm round wafer, 775 um thickness, standard notch`
- Material: `e.g. Bare silicon wafer, Si(100)`
- Specific Request: `e.g. Frontside inspection with 3 mm edge exclusion; non-contact handling required.`
- What to Detect / Measure: `e.g. Detect frontside particles, scratches and surface defects above 1 um.`
- Expected Results: `e.g. Defect map, defect images, CSV data and PDF summary report.`
- Other Tools: `e.g. KLA Surfscan comparison; enter N/A when none`
- Primary Tool: `e.g. Aconca FS Edge`
- Complementary Tool: `e.g. Nansi`
- Key Success Factors: `e.g. Capture rate >= 95%, false positive rate <= 5%, complete defect map output.`
- Internal Questions: `e.g. Confirm recipe preparation and machine availability.`
- Customer Questions: `e.g. Confirm sample delivery date and required report format.`
- Slot ID: `e.g. 1`
- WID: `e.g. DEMO-ACONCA-001`
- Wafer Specificity: `e.g. 300 mm bare Si(100), 775 um thickness`
- Notch / Flat: `e.g. Standard notch, notch at 6 o'clock`
- DOI / Metrology Items: `e.g. Particles, scratches and surface defects above 1 um`
- Result File Provided: `e.g. Customer will provide reference defect map and KLARF baseline.`

## 保持不变

- 不修改字段名、API payload、后端校验或数据库结构。
- 不改变必填标记与必填规则；Complementary Tool 仍为可选。
- 不改变 Sales Owner、Engineer Owner、客户与联系人校验。
- 不修改其他 CRM 表单。

## 验收标准

1. `Timing` 显示为日历日期选择器，并提交 `YYYY-MM-DD`。
2. 规定范围内的灰色提示均以 `e.g. ` 开头并使用已批准文案。
3. 下拉框、必填标记和错误提示行为保持不变。
4. Demo Request 表单聚焦测试与 Frappe 前端生产构建通过。
