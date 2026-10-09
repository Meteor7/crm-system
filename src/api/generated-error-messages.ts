import { localeMessage } from '@/i18n'
import { isOpportunityStage, opportunityStageLabel } from '@/domain/opportunity-stages'

type CopyPair = readonly [english: string, chinese: string]

// Fixed service-generated messages, keyed by the normalized error code. Arbitrary backend diagnostics remain untouched.
const FIXED_MESSAGES: Partial<Record<string, Record<string, CopyPair>>> = {
  INVALID_TRANSITION: {
    'RFQ can only be created when the Opportunity is at customer_budget_approved.': ['RFQ can only be created when the Opportunity is at Customer budget approved.', '只有处于客户预算批准阶段的商机可以创建 RFQ。'],
    'Demo Request can only be created for an Opportunity in qualified_opportunity or demo_done.': ['Demo Request can only be created for an Opportunity at Qualified opportunity or Demo done.', '只有处于合格商机或 Demo 完成阶段的商机可以创建 Demo Request。'],
    'New Opportunity must start at qualified_opportunity.': ['A new Opportunity must start at Qualified opportunity.', '新建商机必须从合格商机阶段开始。'],
    'Opportunity stages change only through their workflow actions.': ['Opportunity stages change only through their workflow actions.', '商机阶段只能通过对应的流程操作变更。'],
    'The probability level is frozen once the PO is received or the Opportunity is lost.': ['The success probability is frozen once the PO is received or the Opportunity is lost.', '收到 PO 或丢单后，成功概率不能再修改。'],
    'Internal validation is only available for equipment Opportunities.': ['Internal validation is only available for equipment Opportunities.', '只有设备类商机可以申请内部生产审批。'],
    'The internal validation was already decided or cancelled.': ['The internal validation was already decided or cancelled.', '该内部生产审批申请已审批或已撤销。'],
    'Rollback target must be an earlier stage.': ['The rollback target must be an earlier stage.', '回退目标必须早于当前阶段。'],
    'internal_validation requires the Booking created by an approved internal validation.': ['Rolling back to Internal validation requires the Booking created by an approved internal validation.', '只有当前 Booking 来自已批准的内部生产审批时，才能回退到内部生产审批阶段。'],
    'A lost Opportunity cannot be advanced by workflow completion.': ['A lost Opportunity cannot be advanced by workflow completion.', '已丢单的商机不能由流程完成自动推进。'],
    'Source Opportunity must belong to the Account.': ['The source Opportunity must belong to the Account.', '来源商机必须属于该客户。'],
    'Opportunity Bookings are created by confirming the PO or approving an internal validation.': ['Opportunity Bookings are created by confirming the PO or approving an internal validation.', '商机来源的 Booking 只能通过确认收到 PO 或批准内部生产审批生成。'],
    'Account, source, Opportunity and type of an Opportunity Booking cannot change.': ['The account, source, Opportunity, and type of an Opportunity Booking cannot change.', '商机来源 Booking 的客户、来源、商机和类型不能修改。'],
    "A Booking's source cannot change.": ["A Booking's source cannot change.", 'Booking 的来源不能修改。'],
    'An Opportunity Booking can only be changed to Cancelled.': ['An Opportunity Booking can only be changed to Cancelled.', '商机来源的 Booking 只能改为已取消。'],
    'The currency of a confirmed order cannot change through an ordinary edit.': ['The currency of a confirmed order cannot change through an ordinary edit.', '已确认订单的币种不能通过普通编辑修改。'],
    'Only a Confirmed or Completed Booking has an actual PO date.': ['Only a Confirmed or Completed Booking has an actual PO date.', '只有已确认或已完成的 Booking 才有实际 PO 日期。'],
    'Only a Confirmed or Completed Booking has a CNY amount to record.': ['Only a Confirmed or Completed Booking has an amount in CNY to record.', '只有已确认或已完成的订单需要补录人民币金额。'],
    'This Demo is no longer awaiting testing.': ['This Demo is no longer being prepared or tested, so its resources cannot be arranged.', '这个 Demo 已不在测试准备或测试阶段，不能再安排设备。'],
    // The Warnings page's handling records (services/warning_handling.py).
    'Only stage 6 and postponed PO warnings take a recorded action; the others clear through their own records.': ['Only stage 6 and postponed PO warnings take a recorded action; the others clear through their own records.', '只有“第 6 阶段超期无 PO”和“预计 PO 跨季度推迟”预警可以记录处理行动，其他预警通过各自的记录解除。'],
    'This warning has changed or cleared. Reload the page.': ['This warning has changed or cleared. Reload the page.', '这条预警已变化或已解除，请刷新页面。'],
    // The archive (a Manager's, in place of a delete).
    'An archived Lead cannot be edited; a Manager can restore it from the archive.': ['This Lead is archived and cannot be edited; a Manager can restore it from the archive.', '该 Lead 已归档，不能编辑；经理可取消归档。'],
    'An archived Lead cannot be converted; a Manager can restore it from the archive.': ['This Lead is archived and cannot be converted; a Manager can restore it from the archive.', '该 Lead 已归档，不能转换；经理可取消归档。'],
    "A converted Lead is part of its Account's history and cannot be archived.": ["A converted Lead is part of its Account's history and cannot be archived.", '已转换的 Lead 是客户的历史记录，不能归档。'],
    'An Opportunity Booking cannot be archived; cancel it instead.': ['An Opportunity Booking cannot be archived; cancel it instead.', '商机来源的 Booking 不能归档，请改为取消。'],
    'An archived Booking cannot be changed; a Manager can restore it from the archive.': ['This Booking is archived and cannot be changed; a Manager can restore it from the archive.', '该 Booking 已归档，不能修改；经理可取消归档。'],
    'A completed Booking is the record of a delivered order and cannot be archived.': ['A completed Booking is the record of a delivered order and cannot be archived.', '已完成的 Booking 是交付记录，不能归档。'],
    'An archived Opportunity cannot be changed; a Manager can restore it from the archive.': ['This Opportunity is archived and cannot be changed; a Manager can restore it from the archive.', '该商机已归档，不能修改；经理可取消归档。'],
    'An archived Opportunity takes no new record; a Manager can restore it from the archive.': ['This Opportunity is archived and takes no new record; a Manager can restore it from the archive.', '该商机已归档，不能新增关联记录；经理可取消归档。'],
    'An Opportunity with a Booking that is not cancelled cannot be archived; cancel the Booking first.': ['An Opportunity with a Booking that is not cancelled cannot be archived. Cancel the Booking first.', '商机还有未取消的 Booking，不能归档；请先取消该 Booking。'],
    'An Opportunity with a Demo Request in progress cannot be archived; cancel the Demo Request first.': ['An Opportunity with a Demo Request in progress cannot be archived. Cancel the Demo Request first; one under review is returned or rejected before that.', '商机还有进行中的 Demo Request，不能归档；请先取消该 Demo Request（审核中的需先退回或驳回）。'],
    'An Opportunity with a demo test in progress cannot be archived; finish or terminate the demo test first.': ['An Opportunity with a demo test in progress cannot be archived. Finish or terminate the demo test first.', '商机还有进行中的 Demo 测试，不能归档；请先完成或终止该测试。'],
    'An archived Account cannot be changed; a Manager can restore it from the archive.': ['This Account is archived and cannot be changed; a Manager can restore it from the archive.', '该客户已归档，不能修改；经理可取消归档。'],
    'An archived Account takes no new record; a Manager can restore it from the archive.': ['This Account is archived and takes no new record; a Manager can restore it from the archive.', '该客户已归档，不能新增关联记录；经理可取消归档。'],
    'Nothing is reopened or restored under an archived Account; a Manager can restore the Account first.': ['Nothing is reopened or restored under an archived Account; a Manager can restore the Account first.', '该客户已归档，其下的记录不能重新打开或取消归档；请经理先取消客户归档。'],
    'An Account with an open Opportunity cannot be archived; close or archive the Opportunity first.': ['An Account with an open Opportunity cannot be archived. Close or archive the Opportunity first.', '客户还有进行中的商机，不能归档；请先关闭或归档该商机。'],
    'An Account with a Demo Request in progress cannot be archived; cancel the Demo Request first.': ['An Account with a Demo Request in progress cannot be archived. Cancel the Demo Request first.', '客户还有进行中的 Demo Request，不能归档；请先取消该 Demo Request。'],
    'An Account with a demo test in progress cannot be archived; finish or terminate the demo test first.': ['An Account with a demo test in progress cannot be archived. Finish or terminate the demo test first.', '客户还有进行中的 Demo 测试，不能归档；请先完成或终止该测试。'],
    'An Account with a Booking in progress cannot be archived; cancel or complete the Booking first.': ['An Account with a Booking in progress cannot be archived. Cancel or complete the Booking first.', '客户还有进行中的 Booking，不能归档；请先取消或完成该 Booking。'],
  },
  VALIDATION_ERROR: {
    'Invalid Review period or anchor.': ['This period cannot be shown. Choose another date.', '无法显示这个周期，请重新选择日期。'],
    'Invalid Plan period or anchor.': ['This period cannot be shown. Choose another date.', '无法显示这个周期，请重新选择日期。'],
    'The reporting line would create a cycle.': ['The reporting line would create a cycle.', '汇报关系不能形成环。'],
    'The merge would make the reporting line a cycle.': ['The merge would make the reporting line a cycle.', '合并后汇报关系会形成环。'],
    'Lost Reason is required for a lost Opportunity.': ['A lost reason is required for a lost Opportunity.', '丢单商机必须填写丢单原因。'],
    'probabilityLevel cannot be cleared once the demo is done.': ['The success probability cannot be cleared once the demo is done.', 'Demo 完成后不能清空成功概率。'],
    'Confirm the customer need and the budget owner before creating the Opportunity.': ['Confirm the customer need and the budget owner before creating the Opportunity.', '请先确认客户需求与预算负责人，再创建商机。'],
    'Set the probability level before this step.': ['Set the success probability before this step.', '请先设置成功概率，再执行此操作。'],
    'approvedOn is required.': ['Enter the budget approval date.', '请填写预算批准日期。'],
    'approvedOn cannot be in the future.': ['The budget approval date cannot be in the future.', '预算批准日期不能晚于今天。'],
    'expectedPoDate is required.': ['Enter the expected PO date.', '请填写预计 PO 日期。'],
    'A comment is required to reject an internal validation.': ['A comment is required to reject an internal validation.', '驳回内部生产审批时必须填写审批意见。'],
    // A controlled-document approval (services/document_access.py): the page refuses the same before sending.
    'An approval carries no note: clear it, or reject the request or ask for more information.': ['An approval carries no note to the applicant. Clear the note, or reject the request or ask for more information instead.', '批准时不会把说明发给申请人。请清空说明，或改为拒绝/要求补充信息。'],
    'This document has no PDF preview. Approve the original file instead.': ['This document has no PDF preview. Approve the original file instead.', '该文档没有 PDF 预览，请改为批准原件。'],
    'booking is required.': ['Enter the Booking details.', '请填写 Booking 信息。'],
    'amountCny is required.': ['Enter the amount in CNY.', '请填写人民币金额。'],
    'The amount and the amount in CNY are required from Demo done.': ['Enter the amount and the amount in CNY on the Opportunity first: they are required from Demo done on.', '请先在商机上填写金额和人民币金额：从 Demo 完成阶段起必须有金额。'],
    'amountCny is unchanged.': ['The amount in CNY has not changed.', '人民币金额没有变化。'],
    'A CNY Booking uses its amount.': ['A CNY Booking uses its own amount; no separate amount in CNY is needed.', '人民币订单直接使用订单金额，不需要另填人民币金额。'],
    'A reason is required to correct the CNY amount.': ['Enter a reason to correct the amount in CNY.', '更正人民币金额必须填写原因。'],
    'amountCny must be positive with at most two decimal places.': ['The amount in CNY is not valid: enter a positive number with at most two decimal places.', '人民币金额无效：请填写正数，最多两位小数。'],
    'opportunityAmount must be blank or a non-negative amount with at most two decimal places.': ['The amount can be left blank; otherwise it cannot be negative and can have at most two decimal places.', '金额可以留空；填写时不能为负数，最多两位小数。'],
    'amount must be positive with at most two decimal places.': ['The amount is not valid: enter a positive number with at most two decimal places.', '金额无效：请填写正数，最多两位小数。'],
    'originalAmount must be positive with at most two decimal places.': ['The original amount is not valid: enter a positive number with at most two decimal places.', '原始金额无效：请填写正数，最多两位小数。'],
    'singleSalesObjective is too long.': ['The single sales objective is too long (2000 characters at most).', '本单目标过长（最多 2000 个字符）。'],
    'competitors must be a list of competitors.': ['The competitors could not be read. Reload the page and try again.', '竞争对手信息无法识别，请刷新页面后重试。'],
    'competitors cannot have more than 10 rows.': ['An Opportunity can list at most 10 competitors.', '一个商机最多填写 10 个竞争对手。'],
    'Each competitor needs a name.': ['Enter a name for every competitor.', '每个竞争对手都必须填写名称。'],
    'A competitor is listed twice.': ['A competitor can be listed only once.', '同一个竞争对手只能填写一次。'],
    'A competitor entry is too long.': ['A competitor entry is too long (140 characters for the name, 1000 for each text).', '竞争对手信息过长（名称最多 140 个字符，每段说明最多 1000 个字符）。'],
    'opportunityAmountCny is required.': ['Enter the amount in CNY.', '请填写人民币金额。'],
    'opportunityAmountCny must be positive with at most two decimal places.': ['The amount in CNY is not valid: enter a positive number with at most two decimal places.', '人民币金额无效：请填写正数，最多两位小数。'],
    'actualPoDate is required.': ['Enter the actual PO date.', '请填写实际 PO 日期。'],
    'actualPoDate cannot be in the future.': ['The actual PO date cannot be later than today.', '实际 PO 日期不能晚于今天。'],
    'actualPoDate is unchanged.': ['The actual PO date has not changed.', '实际 PO 日期没有变化。'],
    'A reason is required to correct the actual PO date.': ['Enter a reason to correct the actual PO date.', '更正实际 PO 日期必须填写原因。'],
    "The actual PO date changes only through a Manager's correction.": ["The actual PO date changes only through a Manager's correction.", '实际 PO 日期只能由经理更正。'],
    "The CNY amount changes only through a Manager's correction.": ["The amount in CNY changes only through a Manager's correction.", '人民币金额只能由经理更正。'],
    'region must be an English region name.': ['Enter a custom region in English, for example Northeast China.', '自定义区域请用英文填写，例如 Northeast China。'],
    'subRegion is not a known region.': ['Choose one of the account regions.', '请选择已有的客户区域。'],
    // Values the server's own checks refuse on save (api/v1/errors.py input_error) and files it cannot store.
    'The phone number is not valid: use at most 20 characters from digits, spaces and + - ( ) , . # *.': ['The phone number is not valid. Use at most 20 characters: digits, spaces and + - ( ) , . # *. Write an extension as 021-62881234-801.', '电话号码格式不被接受：最多 20 个字符，只能用数字、空格和 + - ( ) , . # *。分机请写成 021-62881234-801。'],
    'The email address is not valid.': ['The email address is not valid.', '邮箱地址格式不正确。'],
    'The name cannot contain < or >.': ['The name cannot contain < or >.', '名称不能包含 < 或 >。'],
    'A value is too long.': ['One of the values is too long. Shorten it and try again.', '有一项内容过长，请缩短后重试。'],
    'The PDF file could not be read.': ['The PDF file could not be read. It may be damaged: export it again and retry.', 'PDF 文件无法读取，可能已损坏，请重新导出后再上传。'],
    'The PDF contains scripts and cannot be uploaded.': ['The PDF contains scripts and cannot be uploaded.', 'PDF 中含有脚本，不能上传。'],
    "A Contact cannot be added to this Account: the Account's name is too long.": ["A Contact cannot be added to this Account: the Account's name is too long.", '无法在这个客户下新建联系人：客户名称过长。'],
    'Confirmed order currency is fixed': ['The currency of a confirmed order is fixed.', '已确认订单的币种不可修改。'],
    'Opportunity Booking requires a source Opportunity.': ['An Opportunity Booking requires a source Opportunity.', '商机来源的 Booking 必须关联来源商机。'],
    // A Sales user reads a Visit only on an Account they read (services/visits.py).
    'The Visit owner cannot see this Account: it is Private and not theirs.': ['The visit owner cannot see this account: it is private and belongs to someone else. Choose the account owner, or make the account public first.', '拜访负责人看不到这个客户：客户是私有的，负责人不是他。请选客户负责人，或先把客户改为公开。'],
    'The action owner cannot see this Account: it is Private and not theirs.': ['The action owner cannot see this account: it is private and belongs to someone else. Choose the account owner, or make the account public first.', '行动负责人看不到这个客户：客户是私有的，负责人不是他。请选客户负责人，或先把客户改为公开。'],
    'Mentioned user must have access to this Demo Request.': ['Only someone who can read this Demo Request can be mentioned.', '只能 @ 能看到这条 Demo Request 的人。'],
    // Demo resources: the catalogue, the unavailable intervals and a Demo's schedule (services/demo_resources.py).
    'Provide start and end with an explicit time zone.': ['Enter a valid start and end time (Shanghai time).', '请填写有效的开始和结束时间（上海时间）。'],
    'End must be later than start.': ['The end must be later than the start.', '结束时间必须晚于开始时间。'],
    'Equipment ID cannot be changed.': ['The equipment ID cannot be changed.', '设备编号不能修改。'],
    'Equipment ID already exists.': ['This equipment ID exists already.', '这个设备编号已存在。'],
    'Choose an active Manager or Engineer as maintainer.': ['Choose an active Manager or Engineer as the maintainer.', '维护负责人请选择在职的经理或工程师。'],
    'Status must be Active or Resolved.': ['The status must be Unavailable or Resolved.', '状态只能是“不可用”或“已恢复”。'],
    'Clear dates together with the resource.': ['Clear the dates together with the resource.', '清除设备时请一并清除开始和结束时间。'],
    'Choose a resource accepting new assignments.': ['Choose a resource that allows new assignments.', '请选择允许新安排的设备资源。'],
    'New equipment must not provide a previous version.': ['New equipment has no previous version to name. Reload the page and try again.', '新增设备时不应带版本号，请刷新页面后重试。'],
    'New intervals must not provide a previous version.': ['A new interval has no previous version to name. Reload the page and try again.', '新增不可用时段时不应带版本号，请刷新页面后重试。'],
    'enabled must be true or false.': ['Say whether the equipment allows new assignments.', '请选择设备是否允许新安排。'],
    // Controlled documents: the Manager's decision and note (services/document_access.py).
    'Say what the applicant should add.': ['Say what the applicant should add.', '请写明需要申请人补充什么。'],
    'The note must be text.': ['The note must be text.', '给申请人的说明必须是文字。'],
    'The note may hold at most 1000 characters.': ['The note may hold at most 1000 characters.', '给申请人的说明最多 1000 个字符。'],
    'Unknown controlled-document decision.': ['Unknown decision. Reload the page and try again.', '未知的审批操作，请刷新页面后重试。'],
    // An Opportunity's scorecard links (services/document_links.py, opportunity_documents.py).
    'Enter an absolute HTTP or HTTPS URL.': ['Enter a complete http:// or https:// link.', '请填写完整的 http:// 或 https:// 链接。'],
    'Enter an absolute HTTP or HTTPS URL without credentials.': ['Enter a complete http:// or https:// link, without a user name or password in it.', '请填写完整的 http:// 或 https:// 链接，链接里不能带用户名或密码。'],
    'Enter a URL without spaces, at most 2048 characters.': ['Enter a link without spaces, of at most 2048 characters.', '链接不能含空格，最多 2048 个字符。'],
    // Answered to a request without the two link keys, which the page always sends: a fault of the client, not of the user.
    'Supply productScorecard or dealScorecard.': ['The request was not understood. Reload the page and try again.', '请求格式不正确，请刷新页面后重试。'],
    // The Warnings page's handling records (services/warning_handling.py).
    'Pick a follow-up day after today, at most a year ahead.': ['Pick a review day after today, at most a year ahead.', '复核日期请选今天之后、一年以内的日子。'],
    'Unknown warning type.': ['Unknown warning type. Reload the page.', '未知的预警类型，请刷新页面。'],
    'sourceId and sourceEvent are required.': ['The warning to handle was not named. Reload the page.', '没有指明要处理的预警，请刷新页面。'],
    // A Lead's arrangements (services/leads.py): the list sent in full, and one arrangement added to a full Lead.
    'activities may hold at most 200 entries.': ['The Lead can hold at most 200 activities.', '一个 Lead 最多 200 条安排。'],
    'The Lead holds 200 arrangements, the most it can; remove one before adding another.': ['The Lead holds 200 activities, the most it can.', '这个 Lead 已有 200 条安排，达到上限。'],
    // Files uploaded several at a time (services/contact_files.py, api/v1/contact_files.py, opportunity_status.py).
    'Upload must contain between 1 and 10 files.': ['Upload 1 to 10 files at a time.', '一次上传 1 到 10 个文件。'],
    'Upload exceeds the 100 MiB request limit.': ['The files of one upload may not exceed 100 MiB together.', '一次上传的文件总大小不能超过 100 MiB。'],
  },
  CONFLICT: {
    'Another Lead already uses this email address.': ['Another Lead already uses this email address; it may be archived or out of your scope, so ask a Manager.', '已有其他 Lead 使用这个邮箱（可能已归档或不在你的范围内，请联系经理）。'],
    'A Contact merged or archived already cannot be merged.': ['A Contact merged or archived already cannot be merged.', '已被合并或已归档的联系人不能再合并。'],
    'An Account with this name exists already.': ['An account with this name exists already.', '已有同名的客户。'],
    'Another request is naming an Account like this; try again.': ['Another request is naming an account like this; try again.', '另一个请求正在用同样的名字新建或修改客户，请稍后再试。'],
    'Account and sale type cannot change while the Opportunity has a live Booking.': ['The account and sale type cannot change while the Opportunity has a live Booking.', '商机存在未取消的 Booking 时，不能修改客户或销售类型。'],
    'The Opportunity already has a pending internal validation.': ['The Opportunity already has a pending internal validation.', '该商机已有待审批的内部生产审批申请。'],
    'No other active Manager can review this internal validation.': ['No other active Manager can review this internal validation.', '没有其他在职 Manager 可以审批该内部生产审批申请。'],
    'The Opportunity already has a live Booking.': ['The Opportunity already has a live Booking.', '该商机已有未取消的 Booking。'],
    'Cancel the Booking before marking the Opportunity lost.': ['Cancel the Booking before marking the Opportunity lost.', '请先取消 Booking，再标记丢单。'],
    'A completed Booking blocks stage rollback.': ['A completed Booking blocks stage rollback.', 'Booking 已完成，不能回退商机阶段。'],
    'Cancel the Booking before rolling the Opportunity back.': ['Cancel the Booking before rolling the Opportunity back.', '请先取消 Booking，再回退商机阶段。'],
    'This controlled-document request has already been decided.': ['This access request has already been decided.', '这条访问申请已经审批过了。'],
    // CONTACT_MERGE_CONFLICT and QUOTATION_VERSION_LOCKED are read as CONFLICT (contracts.ts).
    'Contacts from different accounts cannot be merged.': ['Contacts of different accounts cannot be merged.', '不同客户的联系人不能合并。'],
    'Only the current draft can be discarded.': ['Only the current draft can be discarded.', '只能放弃当前的草稿版本。'],
    'A quotation pending approval cannot be discarded.': ['A quotation pending approval cannot be discarded.', '待审批的报价不能放弃。'],
    'A draft that has been through approval cannot be discarded. Revise it and submit it again.': ['A draft that has been through approval cannot be discarded. Revise it and submit it again.', '经过审批的草稿不能放弃，请修改后重新提交。'],
  },
  PERMISSION_DENIED: {
    'Only Managers maintain the resource catalogue.': ['Only a Manager maintains the resource catalogue.', '只有经理可以维护设备目录。'],
    'Approved document access is required.': ['This document can be opened only with an approved access request.', '需要先获得批准才能访问这份文档。'],
    'This document does not accept access requests.': ['This document does not accept access requests.', '这份文档不接受访问申请。'],
    'Warnings handling is available to CRM Managers only.': ['Only a Manager can record the handling of a warning.', '只有经理可以记录预警的处理。'],
    'Only the Opportunity owner can set the probability level.': ['Only the Opportunity owner can set the success probability.', '只有商机负责人可以设置成功概率。'],
    'Managers cannot review their own internal validation.': ['Managers cannot review their own internal validation.', 'Manager 不能审批自己提交的内部生产审批申请。'],
    'Only a Manager can fill in or correct the actual PO date.': ['Only a Manager can fill in or correct the actual PO date.', '只有经理可以补录或更正实际 PO 日期。'],
    'Only a Manager can fill in or correct the CNY amount.': ['Only a Manager can fill in or correct the amount in CNY.', '只有经理可以补录或更正人民币金额。'],
  },
  NOT_FOUND: {
    'Internal validation was not found.': ['Internal validation was not found.', '未找到该内部生产审批申请。'],
    // One answer for a record that does not exist and for one the user may not see (services/accounts.py, contacts.py).
    'Account was not found, or you have no access to it.': ['The account was not found, or you have no access to it.', '找不到这个客户，或者你没有查看权限。'],
    'Contact was not found, or you have no access to it.': ['The contact was not found, or you have no access to it.', '找不到这个联系人，或者你没有查看权限。'],
    'Site was not found, or you have no access to it.': ['The site was not found, or you have no access to it.', '找不到这个厂区，或者你没有查看权限。'],
    'Resource was not found.': ['The resource was not found.', '找不到这个设备资源。'],
    'Record was not found.': ['The record was not found. Reload the page.', '找不到这条记录，请刷新页面。'],
    'The controlled-document request was not found.': ['The access request was not found.', '找不到这条访问申请。'],
    'The controlled-document version is unavailable.': ['This document version is no longer available.', '这个文档版本已不可用。'],
    'Quotation version was not found.': ['The quotation version was not found.', '找不到这个报价版本。'],
    // CONTACT_FILE_NOT_FOUND is read as NOT_FOUND (contracts.ts).
    'Contact file was not found.': ['The file was not found.', '找不到这个文件。'],
  },
  SCOPE_DENIED: {
    'Sales users can only assign records to themselves.': ['A Sales user can assign records only to themselves. Choose yourself as the owner.', '销售只能把记录分配给自己，请把负责人选为本人。'],
    'Only the Account owner or a Manager may edit this Account.': ['Only the account owner or a Manager may edit this account.', '只有客户负责人或经理可以编辑这个客户。'],
    'Only the Account owner or a Manager may edit contacts.': ['Only the account owner or a Manager may edit its contacts.', '只有客户负责人或经理可以编辑这个客户的联系人。'],
    'Only the Account owner or a Manager may upload files.': ['Only the account owner or a Manager may upload files.', '只有客户负责人或经理可以上传文件。'],
    'The file is outside the current user scope.': ['This file is outside your scope.', '这个文件不在你的权限范围内。'],
    'Demo is outside your current scope.': ['This Demo is outside your scope.', '这个 Demo 不在你的权限范围内。'],
    'Only the resource maintainer or a Manager can edit availability.': ['Only the resource maintainer or a Manager can edit its availability.', '只有设备的维护负责人或经理可以编辑不可用时段。'],
    'Unavailability belongs to another resource.': ['This interval belongs to another resource.', '这个不可用时段属于另一台设备。'],
    'Only the current Demo Engineer or a Manager may arrange resources.': ['Only the current Demo Engineer or a Manager may arrange resources.', '只有当前负责的 Demo 工程师或经理可以安排设备资源。'],
    'Resource is outside your permitted Demo scope.': ['This resource is outside your Demo scope.', '这个设备资源不在你的 Demo 权限范围内。'],
  },
  VERSION_CONFLICT: {
    // The shared check of every versioned write (services/concurrency.py), and the Demo resource services' own.
    'The record was changed by another request.': ['This record was changed by another user. Refresh and try again.', '记录已被其他用户修改，请刷新后重试。'],
    'Record changed; reload before saving.': ['This record changed meanwhile. Reload it before saving.', '记录已被修改，请刷新后再保存。'],
    'Someone else already saved this warning. Reload before editing.': ['Someone else already saved this warning. Reload before editing.', '这条预警已被他人保存，请刷新后再编辑。'],
    'Someone else saved this warning at the same time. Reload.': ['Someone else saved this warning at the same time. Reload.', '这条预警刚被他人同时保存，请刷新。'],
    "This warning's handling is no longer there. Reload before editing.": ["This warning's handling is no longer there. Reload before editing.", '这条预警的处理记录已不存在，请刷新后再编辑。'],
  },
}

// "<action> is not available at <stage>." names the workflow action that the current stage does not allow.
const UNAVAILABLE_ACTIONS: Record<string, CopyPair> = {
  'Budget approval': ['Budget approval', '确认客户预算'],
  'Internal validation': ['Internal validation', '申请内部生产审批'],
  'Internal validation review': ['Internal validation review', '审批内部生产申请'],
  'PO confirmation': ['PO confirmation', '确认收到 PO'],
  'Marking the Opportunity lost': ['Marking the Opportunity lost', '标记丢单'],
}

// "<label> is too long: at most <n> characters." names the field by the label of its column. The fields
// users reach most are given the names their forms use; any other keeps its label.
const TOO_LONG_FIELDS: Record<string, CopyPair> = {
  'Customer Name': ['The customer name', '客户全称'],
  'CRM Short Name': ['The short name', '客户简称'],
  'CRM City': ['The city', '城市'],
  'CRM Region': ['The region', '区域'],
  'First Name': ['The name', '姓名'],
  Designation: ['The title', '职位'],
  Department: ['The department', '部门'],
  'Email Address': ['The email address', '邮箱'],
  'Address Title': ['The site name', '厂区名称'],
  'City/Town': ['The city', '城市'],
  'Requested Equipment': ['The primary tool', '主要设备'],
  'Sample Type': ['The material (substrate)', '材料（基底）'],
}

// "<key> must be at most <n> characters." and "<key> is required." name a field by its payload key: the Demo resource
// forms (services/demo_resources.py), and the other forms that raise the same text for `reason` (a termination, a
// rollback, a rejection, an access request: "原因" fits each) and for `reason`'s length (the Demo Test termination).
const RESOURCE_FIELDS: Record<string, CopyPair> = {
  code: ['The equipment ID', '设备编号'],
  title: ['The name', '名称'],
  platform: ['The platform / model', '平台／型号'],
  maintainer: ['The maintainer', '维护负责人'],
  reason: ['The reason', '原因'],
  resourceId: ['The resource', '设备资源'],
}

const stageLabels = (stage: string) => [opportunityStageLabel(stage, 'en-US'), opportunityStageLabel(stage, 'zh-CN')] as const

export function generatedErrorMessage(code: string, message: string) {
  const fixed = FIXED_MESSAGES[code]?.[message]
  if (fixed) return localeMessage(fixed[0], fixed[1])
  if (code === 'INVALID_TRANSITION') {
    const unavailable = /^(.+) is not available at ([a-z_]+)\.$/.exec(message)
    const action = unavailable ? UNAVAILABLE_ACTIONS[unavailable[1]] : undefined
    if (unavailable && action && isOpportunityStage(unavailable[2])) {
      const [english, chinese] = stageLabels(unavailable[2])
      return localeMessage(`${action[0]} is not available at ${english}.`, `当前阶段为${chinese}，不能${action[1]}。`)
    }
    const reopen = /^A lost Opportunity can only reopen at or below ([a-z_]+)\.$/.exec(message)
    if (reopen && isOpportunityStage(reopen[1])) {
      const [english, chinese] = stageLabels(reopen[1])
      return localeMessage(`A lost Opportunity can only reopen at ${english} or an earlier stage.`, `丢单商机只能重新打开到${chinese}或更早的阶段。`)
    }
  }
  if (code === 'VALIDATION_ERROR') {
    const contactName = /^name is too long: at most (\d+) characters for a Contact of this Account\.$/.exec(message)
    if (contactName) {
      return localeMessage(
        `The name is too long: a Contact of this Account can have at most ${contactName[1]} characters.`,
        `姓名过长：这个客户下的联系人姓名最多 ${contactName[1]} 个字符。`,
      )
    }
    const tooLong = /^(.+) is too long: at most (\d+) characters\.$/.exec(message)
    if (tooLong) {
      const [english, chinese] = TOO_LONG_FIELDS[tooLong[1]] ?? [`"${tooLong[1]}"`, `“${tooLong[1]}”`]
      return localeMessage(`${english} is too long: at most ${tooLong[2]} characters.`, `${chinese}过长：最多 ${tooLong[2]} 个字符。`)
    }
    const fieldLimit = /^(\w+) must be at most (\d+) characters\.$/.exec(message)
    const limitLabel = fieldLimit ? RESOURCE_FIELDS[fieldLimit[1]!] : undefined
    if (fieldLimit && limitLabel) {
      return localeMessage(`${limitLabel[0]} may hold at most ${fieldLimit[2]} characters.`, `${limitLabel[1]}最多 ${fieldLimit[2]} 个字符。`)
    }
    // Not `title`: Contact and Lead raise the same text for a job title, Opportunity, Action and document uploads for
    // their own titles; and `resourceId` is never required.
    const fieldRequired = /^(code|platform|maintainer|reason) is required\.$/.exec(message)
    const requiredLabel = fieldRequired ? RESOURCE_FIELDS[fieldRequired[1]!] : undefined
    if (fieldRequired && requiredLabel) return localeMessage(`${requiredLabel[0]} is required.`, `${requiredLabel[1]}不能为空。`)
    // A Lead's arrangements, sent as a list (services/leads.py): the one at fault is named by its place.
    const activity = /^activities\[(\d+)\]\.action (?:is required|may hold at most (\d+) characters)\.$/.exec(message)
    if (activity) {
      const ordinal = Number(activity[1]) + 1
      return activity[2]
        ? localeMessage(`Activity ${ordinal} may hold at most ${activity[2]} characters.`, `第 ${ordinal} 条安排的内容最多 ${activity[2]} 个字符。`)
        : localeMessage(`Activity ${ordinal} needs its text.`, `第 ${ordinal} 条安排未填写内容。`)
    }
  }
  if (code === 'CONFLICT') {
    const workflow = /^Opportunity must be at ([a-z_]+) before workflow completion can move it to ([a-z_]+)\.$/.exec(message)
    if (workflow && isOpportunityStage(workflow[1]) && isOpportunityStage(workflow[2])) {
      const [fromEnglish, fromChinese] = stageLabels(workflow[1])
      const [toEnglish, toChinese] = stageLabels(workflow[2])
      return localeMessage(
        `The Opportunity must be at ${fromEnglish} before workflow completion can move it to ${toEnglish}.`,
        `商机必须处于${fromChinese}阶段，才能在流程完成后推进至${toChinese}。`,
      )
    }
  }
  return undefined
}
