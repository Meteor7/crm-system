import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, expect, it } from 'vitest'
import { CrmApiError } from './contracts'
import { mapRequestError, requestErrorMessage } from './request-state'
import { resolveLocaleMessage, setLocale } from '@/i18n'

afterEach(() => setLocale('zh-CN'))

it.each([
  ['VALIDATION_ERROR', 'Invalid Review period or anchor.', 'Choose another date.', '请重新选择日期。'],
  ['VALIDATION_ERROR', 'Invalid Plan period or anchor.', 'Choose another date.', '请重新选择日期。'],
  ['INVALID_TRANSITION', 'RFQ can only be created when the Opportunity is at customer_budget_approved.', 'Customer budget approved', '客户预算批准阶段'],
  ['INVALID_TRANSITION', 'Demo Request can only be created for an Opportunity in qualified_opportunity or demo_done.', 'Qualified opportunity or Demo done', '合格商机或 Demo 完成'],
  ['INVALID_TRANSITION', 'New Opportunity must start at qualified_opportunity.', 'Qualified opportunity', '合格商机阶段'],
  ['INVALID_TRANSITION', 'Opportunity stages change only through their workflow actions.', 'workflow actions', '流程操作'],
  ['INVALID_TRANSITION', 'The probability level is frozen once the PO is received or the Opportunity is lost.', 'success probability is frozen', '成功概率不能再修改'],
  ['INVALID_TRANSITION', 'Internal validation is only available for equipment Opportunities.', 'equipment Opportunities', '设备类商机'],
  ['INVALID_TRANSITION', 'The internal validation was already decided or cancelled.', 'already decided', '已审批或已撤销'],
  ['INVALID_TRANSITION', 'Rollback target must be an earlier stage.', 'earlier stage', '早于当前阶段'],
  ['INVALID_TRANSITION', 'internal_validation requires the Booking created by an approved internal validation.', 'Internal validation requires', '已批准的内部生产审批'],
  ['INVALID_TRANSITION', 'A lost Opportunity cannot be advanced by workflow completion.', 'cannot be advanced', '不能由流程完成自动推进'],
  ['INVALID_TRANSITION', 'Budget approval is not available at qualified_opportunity.', 'Budget approval is not available at Qualified opportunity.', '当前阶段为合格商机，不能确认客户预算。'],
  ['INVALID_TRANSITION', 'Internal validation is not available at demo_done.', 'Internal validation is not available at Demo done.', '不能申请内部生产审批'],
  ['INVALID_TRANSITION', 'Internal validation review is not available at internal_validation.', 'Internal validation review is not available at Internal validation.', '不能审批内部生产申请'],
  ['INVALID_TRANSITION', 'PO confirmation is not available at rfq_validated.', 'PO confirmation is not available at RFQ validated.', '当前阶段为RFQ 通过，不能确认收到 PO。'],
  ['INVALID_TRANSITION', 'Marking the Opportunity lost is not available at po_received.', 'Marking the Opportunity lost is not available at PO received.', '不能标记丢单'],
  ['INVALID_TRANSITION', 'A lost Opportunity can only reopen at or below quotation_sent.', 'reopen at Quotation sent or an earlier stage', '重新打开到报价已发或更早的阶段'],
  ['INVALID_TRANSITION', 'The currency of a confirmed order cannot change through an ordinary edit.', 'currency of a confirmed order cannot change', '已确认订单的币种不能通过普通编辑修改'],
  ['INVALID_TRANSITION', 'An archived Lead cannot be edited; a Manager can restore it from the archive.', 'This Lead is archived and cannot be edited', '该 Lead 已归档，不能编辑；经理可取消归档'],
  ['INVALID_TRANSITION', 'An archived Lead cannot be converted; a Manager can restore it from the archive.', 'This Lead is archived and cannot be converted', '该 Lead 已归档，不能转换；经理可取消归档'],
  ['INVALID_TRANSITION', "A converted Lead is part of its Account's history and cannot be archived.", 'cannot be archived', '已转换的 Lead 是客户的历史记录，不能归档'],
  ['CONFLICT', 'Another Lead already uses this email address.', 'ask a Manager', '可能已归档或不在你的范围内，请联系经理'],
  ['BOOKING_SOURCE_INVALID', 'An Opportunity Booking cannot be archived; cancel it instead.', 'cancel it instead', '商机来源的 Booking 不能归档，请改为取消'],
  ['INVALID_TRANSITION', 'An archived Booking cannot be changed; a Manager can restore it from the archive.', 'This Booking is archived and cannot be changed', '该 Booking 已归档，不能修改；经理可取消归档'],
  ['INVALID_TRANSITION', 'A completed Booking is the record of a delivered order and cannot be archived.', 'cannot be archived', '已完成的 Booking 是交付记录，不能归档'],
  ['INVALID_TRANSITION', 'An archived Opportunity cannot be changed; a Manager can restore it from the archive.', 'This Opportunity is archived and cannot be changed', '该商机已归档，不能修改；经理可取消归档'],
  ['INVALID_TRANSITION', 'An archived Opportunity takes no new record; a Manager can restore it from the archive.', 'takes no new record', '不能新增关联记录；经理可取消归档'],
  ['INVALID_TRANSITION', 'An Opportunity with a Booking that is not cancelled cannot be archived; cancel the Booking first.', 'Cancel the Booking first.', '请先取消该 Booking'],
  ['INVALID_TRANSITION', 'An Opportunity with a Demo Request in progress cannot be archived; cancel the Demo Request first.', 'returned or rejected before that', '审核中的需先退回或驳回'],
  ['INVALID_TRANSITION', 'An Opportunity with a demo test in progress cannot be archived; finish or terminate the demo test first.', 'Finish or terminate the demo test first.', '请先完成或终止该测试'],
  ['VALIDATION_ERROR', 'The phone number is not valid: use at most 20 characters from digits, spaces and + - ( ) , . # *.', 'Write an extension as 021-62881234-801.', '分机请写成 021-62881234-801。'],
  ['VALIDATION_ERROR', 'The email address is not valid.', 'The email address is not valid.', '邮箱地址格式不正确。'],
  ['VALIDATION_ERROR', 'The name cannot contain < or >.', 'The name cannot contain < or >.', '名称不能包含 < 或 >。'],
  ['VALIDATION_ERROR', 'A value is too long.', 'One of the values is too long.', '有一项内容过长'],
  ['VALIDATION_ERROR', 'The PDF file could not be read.', 'It may be damaged', 'PDF 文件无法读取'],
  ['VALIDATION_ERROR', 'The PDF contains scripts and cannot be uploaded.', 'contains scripts', 'PDF 中含有脚本'],
  ['VALIDATION_ERROR', 'Customer Name is too long: at most 140 characters.', 'The customer name is too long: at most 140 characters.', '客户全称过长：最多 140 个字符。'],
  ['VALIDATION_ERROR', 'CRM Short Name is too long: at most 140 characters.', 'The short name is too long: at most 140 characters.', '客户简称过长：最多 140 个字符。'],
  ['VALIDATION_ERROR', 'Designation is too long: at most 140 characters.', 'The title is too long: at most 140 characters.', '职位过长：最多 140 个字符。'],
  ['VALIDATION_ERROR', 'Address Line 1 is too long: at most 240 characters.', '"Address Line 1" is too long: at most 240 characters.', '“Address Line 1”过长：最多 240 个字符。'],
  ['VALIDATION_ERROR', 'name is too long: at most 115 characters for a Contact of this Account.', 'a Contact of this Account can have at most 115 characters.', '这个客户下的联系人姓名最多 115 个字符。'],
  ['VALIDATION_ERROR', "A Contact cannot be added to this Account: the Account's name is too long.", "the Account's name is too long", '客户名称过长'],
  ['VALIDATION_ERROR', 'Requested Equipment is too long: at most 140 characters.', 'The primary tool is too long: at most 140 characters.', '主要设备过长：最多 140 个字符。'],
  ['VALIDATION_ERROR', 'Address Title is too long: at most 140 characters.', 'The site name is too long: at most 140 characters.', '厂区名称过长：最多 140 个字符。'],
  ['BOOKING_SOURCE_INVALID', 'Source Opportunity must belong to the Account.', 'must belong to the Account', '来源商机必须属于该客户'],
  ['BOOKING_SOURCE_INVALID', 'Opportunity Bookings are created by confirming the PO or approving an internal validation.', 'confirming the PO', '确认收到 PO'],
  ['BOOKING_SOURCE_INVALID', 'Account, source, Opportunity and type of an Opportunity Booking cannot change.', 'cannot change', '不能修改'],
  ['BOOKING_SOURCE_INVALID', "A Booking's source cannot change.", 'source cannot change', '来源不能修改'],
  ['BOOKING_STATUS_INVALID', 'An Opportunity Booking can only be changed to Cancelled.', 'changed to Cancelled', '只能改为已取消'],
  ['VALIDATION_ERROR', 'Lost Reason is required for a lost Opportunity.', 'lost reason is required', '丢单原因'],
  ['VALIDATION_ERROR', 'probabilityLevel cannot be cleared once the demo is done.', 'cannot be cleared', '不能清空成功概率'],
  ['VALIDATION_ERROR', 'Confirm the customer need and the budget owner before creating the Opportunity.', 'budget owner', '客户需求与预算负责人'],
  ['VALIDATION_ERROR', 'Set the probability level before this step.', 'Set the success probability', '请先设置成功概率'],
  ['VALIDATION_ERROR', 'approvedOn is required.', 'budget approval date', '预算批准日期'],
  ['VALIDATION_ERROR', 'approvedOn cannot be in the future.', 'cannot be in the future', '不能晚于今天'],
  ['VALIDATION_ERROR', 'expectedPoDate is required.', 'expected PO date', '预计 PO 日期'],
  ['VALIDATION_ERROR', 'A comment is required to reject an internal validation.', 'comment is required', '必须填写审批意见'],
  ['VALIDATION_ERROR', 'An approval carries no note: clear it, or reject the request or ask for more information.', 'Clear the note', '请清空说明'],
  ['VALIDATION_ERROR', 'This document has no PDF preview. Approve the original file instead.', 'Approve the original file instead.', '该文档没有 PDF 预览，请改为批准原件。'],
  ['VALIDATION_ERROR', 'booking is required.', 'Booking details', 'Booking 信息'],
  ['VALIDATION_ERROR', 'The amount and the amount in CNY are required from Demo done.', 'required from Demo done on', '从 Demo 完成阶段起必须有金额'],
  ['VALIDATION_ERROR', 'singleSalesObjective is too long.', 'single sales objective is too long', '本单目标过长'],
  ['VALIDATION_ERROR', 'competitors must be a list of competitors.', 'competitors could not be read', '竞争对手信息无法识别'],
  ['VALIDATION_ERROR', 'competitors cannot have more than 10 rows.', 'at most 10 competitors', '最多填写 10 个竞争对手'],
  ['VALIDATION_ERROR', 'Each competitor needs a name.', 'name for every competitor', '都必须填写名称'],
  ['VALIDATION_ERROR', 'A competitor is listed twice.', 'listed only once', '只能填写一次'],
  ['VALIDATION_ERROR', 'A competitor entry is too long.', 'competitor entry is too long', '竞争对手信息过长'],
  ['VALIDATION_ERROR', 'opportunityAmount must be blank or a non-negative amount with at most two decimal places.', 'can be left blank', '金额可以留空'],
  ['VALIDATION_ERROR', 'amount must be positive with at most two decimal places.', 'amount is not valid', '金额无效'],
  ['VALIDATION_ERROR', 'originalAmount must be positive with at most two decimal places.', 'original amount is not valid', '原始金额无效'],
  ['VALIDATION_ERROR', 'region must be an English region name.', 'custom region in English', '自定义区域请用英文填写'],
  ['VALIDATION_ERROR', 'subRegion is not a known region.', 'account regions', '已有的客户区域'],
  ['VALIDATION_ERROR', 'Confirmed order currency is fixed', 'currency of a confirmed order is fixed', '已确认订单的币种不可修改'],
  ['BOOKING_SOURCE_REQUIRED', 'Opportunity Booking requires a source Opportunity.', 'requires a source Opportunity', '必须关联来源商机'],
  ['CONFLICT', 'Account and sale type cannot change while the Opportunity has a live Booking.', 'sale type cannot change', '不能修改客户或销售类型'],
  ['CONFLICT', 'The Opportunity already has a pending internal validation.', 'pending internal validation', '待审批的内部生产审批'],
  ['CONFLICT', 'No other active Manager can review this internal validation.', 'No other active Manager', '没有其他在职 Manager'],
  ['CONFLICT', 'The Opportunity already has a live Booking.', 'already has a live Booking', '已有未取消的 Booking'],
  ['BOOKING_ALREADY_EXISTS', 'The Opportunity already has a live Booking.', 'already has a live Booking', '已有未取消的 Booking'],
  ['CONFLICT', 'Cancel the Booking before marking the Opportunity lost.', 'before marking the Opportunity lost', '再标记丢单'],
  ['CONFLICT', 'A completed Booking blocks stage rollback.', 'blocks stage rollback', '不能回退商机阶段'],
  ['CONFLICT', 'Cancel the Booking before rolling the Opportunity back.', 'before rolling the Opportunity back', '再回退商机阶段'],
  ['CONFLICT', 'Opportunity must be at customer_budget_approved before workflow completion can move it to rfq_validated.', 'at Customer budget approved before workflow completion can move it to RFQ validated', '商机必须处于客户预算批准阶段，才能在流程完成后推进至RFQ 通过。'],
  ['PERMISSION_DENIED', 'Only the Opportunity owner can set the probability level.', 'Only the Opportunity owner can set the success probability.', '只有商机负责人可以设置成功概率。'],
  ['PERMISSION_DENIED', 'Managers cannot review their own internal validation.', 'their own internal validation', '不能审批自己提交的'],
  ['INTERNAL_VALIDATION_NOT_FOUND', 'Internal validation was not found.', 'Internal validation was not found.', '未找到该内部生产审批申请'],
  ['INVALID_OWNER', 'The Visit owner cannot see this Account: it is Private and not theirs.', 'visit owner cannot see this account', '拜访负责人看不到这个客户'],
  ['INVALID_OWNER', 'The action owner cannot see this Account: it is Private and not theirs.', 'action owner cannot see this account', '行动负责人看不到这个客户'],
  ['INVALID_OWNER', 'Mentioned user must have access to this Demo Request.', 'can read this Demo Request can be mentioned', '只能 @ 能看到这条 Demo Request 的人'],
  ['ACCOUNT_NOT_FOUND', 'Account was not found, or you have no access to it.', 'account was not found, or you have no access', '找不到这个客户，或者你没有查看权限'],
  ['CONTACT_NOT_FOUND', 'Contact was not found, or you have no access to it.', 'contact was not found, or you have no access', '找不到这个联系人，或者你没有查看权限'],
  ['SITE_NOT_FOUND', 'Site was not found, or you have no access to it.', 'site was not found, or you have no access', '找不到这个厂区，或者你没有查看权限'],
  // Demo resources (services/demo_resources.py): the catalogue, the intervals, a Demo's schedule, and the field pattern.
  ['VALIDATION_ERROR', 'End must be later than start.', 'The end must be later than the start.', '结束时间必须晚于开始时间。'],
  ['VALIDATION_ERROR', 'Status must be Active or Resolved.', 'Unavailable or Resolved', '状态只能是“不可用”或“已恢复”。'],
  ['VALIDATION_ERROR', 'Equipment ID already exists.', 'exists already', '这个设备编号已存在。'],
  ['VALIDATION_ERROR', 'code must be at most 140 characters.', 'The equipment ID may hold at most 140 characters.', '设备编号最多 140 个字符。'],
  ['VALIDATION_ERROR', 'reason must be at most 1000 characters.', 'The reason may hold at most 1000 characters.', '原因最多 1000 个字符。'],
  ['VALIDATION_ERROR', 'code is required.', 'The equipment ID is required.', '设备编号不能为空。'],
  ['VALIDATION_ERROR', 'reason is required.', 'The reason is required.', '原因不能为空。'],
  ['VALIDATION_ERROR', 'Provide start and end with an explicit time zone.', 'valid start and end time', '有效的开始和结束时间'],
  ['PERMISSION_DENIED', 'Only Managers maintain the resource catalogue.', 'Only a Manager maintains the resource catalogue.', '只有经理可以维护设备目录。'],
  ['SCOPE_DENIED', 'Only the current Demo Engineer or a Manager may arrange resources.', 'current Demo Engineer or a Manager', '只有当前负责的 Demo 工程师或经理可以安排设备资源。'],
  ['INVALID_TRANSITION', 'This Demo is no longer awaiting testing.', 'no longer being prepared or tested', '已不在测试准备或测试阶段'],
  ['VERSION_CONFLICT', 'Record changed; reload before saving.', 'Reload it before saving.', '记录已被修改，请刷新后再保存。'],
  ['NOT_FOUND', 'Resource was not found.', 'The resource was not found.', '找不到这个设备资源。'],
  // The Manager's decision note and the scorecard links (services/document_access.py, document_links.py).
  ['VALIDATION_ERROR', 'The note may hold at most 1000 characters.', 'at most 1000 characters', '给申请人的说明最多 1000 个字符。'],
  ['VALIDATION_ERROR', 'Enter an absolute HTTP or HTTPS URL without credentials.', 'without a user name or password', '链接里不能带用户名或密码'],
  // The Warnings page's handling records (services/warning_handling.py).
  ['VALIDATION_ERROR', 'Pick a follow-up day after today, at most a year ahead.', 'at most a year ahead', '复核日期请选今天之后、一年以内'],
  ['VERSION_CONFLICT', "This warning's handling is no longer there. Reload before editing.", 'no longer there', '处理记录已不存在'],
  // A Lead at its arrangement cap (services/leads.py): the whole list sent, and one more arrangement.
  ['VALIDATION_ERROR', 'activities may hold at most 200 entries.', 'at most 200 activities', '最多 200 条安排'],
  ['VALIDATION_ERROR', 'The Lead holds 200 arrangements, the most it can; remove one before adding another.', 'the most it can', '达到上限'],
  ['VALIDATION_ERROR', 'activities[2].action is required.', 'Activity 3 needs its text.', '第 3 条安排未填写内容。'],
  ['VALIDATION_ERROR', 'activities[0].action may hold at most 140 characters.', 'Activity 1 may hold at most 140 characters.', '第 1 条安排的内容最多 140 个字符。'],
  // Files uploaded several at a time, and the Account's and its Contacts' scope (services/contact_files.py, accounts.py, contacts.py).
  ['VALIDATION_ERROR', 'Upload must contain between 1 and 10 files.', '1 to 10 files', '一次上传 1 到 10 个文件。'],
  ['VALIDATION_ERROR', 'Upload exceeds the 100 MiB request limit.', 'may not exceed 100 MiB together', '总大小不能超过 100 MiB'],
  ['SCOPE_DENIED', 'The file is outside the current user scope.', 'This file is outside your scope.', '这个文件不在你的权限范围内。'],
  ['SCOPE_DENIED', 'Only the Account owner or a Manager may upload files.', 'Only the account owner or a Manager may upload files.', '只有客户负责人或经理可以上传文件。'],
  ['SCOPE_DENIED', 'Only the Account owner or a Manager may edit this Account.', 'may edit this account', '只有客户负责人或经理可以编辑这个客户。'],
  ['SCOPE_DENIED', 'Only the Account owner or a Manager may edit contacts.', 'may edit its contacts', '只有客户负责人或经理可以编辑这个客户的联系人。'],
  ['VERSION_CONFLICT', 'The record was changed by another request.', 'This record was changed by another user. Refresh and try again.', '记录已被其他用户修改，请刷新后重试。'],
  // Service codes the client folds into CONFLICT and NOT_FOUND (contracts.ts).
  ['QUOTATION_VERSION_LOCKED', 'Only the current draft can be discarded.', 'Only the current draft can be discarded.', '只能放弃当前的草稿版本。'],
  ['CONTACT_MERGE_CONFLICT', 'Contacts from different accounts cannot be merged.', 'Contacts of different accounts cannot be merged.', '不同客户的联系人不能合并。'],
  ['CONTACT_FILE_NOT_FOUND', 'Contact file was not found.', 'The file was not found.', '找不到这个文件。'],
])('localizes known %s feedback "%s" while retaining raw diagnostic metadata', (code, message, english, chinese) => {
  const error = new CrmApiError(code, message, 'req_original', false, { field: '原始字段错误' })
  const mapped = mapRequestError(error)
  setLocale('en-US')
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toContain(english)
  expect(resolveLocaleMessage(requestErrorMessage(error))).not.toMatch(/\p{Script=Han}/u)
  setLocale('zh-CN')
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toContain(chinese)
  expect(mapped.message).toBe(message)
  expect(mapped.requestId).toBe('req_original')
  expect(error.fieldErrors).toEqual({ field: '原始字段错误' })
})

it('localizes the owner-only success probability denial in Chinese and keeps it a denied error', () => {
  const error = new CrmApiError('PERMISSION_DENIED', 'Only the Opportunity owner can set the probability level.', 'req_level_owner', false)
  setLocale('zh-CN')
  const mapped = mapRequestError(error)
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toBe('只有商机负责人可以设置成功概率。')
  expect(resolveLocaleMessage(requestErrorMessage(error))).toBe('只有商机负责人可以设置成功概率。')
  expect(mapped).toMatchObject({ message: 'Only the Opportunity owner can set the probability level.', denied: true })
})

it('tells a Sales user in their language that a record can only be their own', () => {
  const error = new CrmApiError('SCOPE_DENIED', 'Sales users can only assign records to themselves.', 'req_owner', false)
  const mapped = mapRequestError(error)
  setLocale('zh-CN')
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toBe('销售只能把记录分配给自己，请把负责人选为本人。')
  setLocale('en-US')
  expect(resolveLocaleMessage(mapped.localizedMessage!)).toBe('A Sales user can assign records only to themselves. Choose yourself as the owner.')
  // It is the error of that write: nothing says the user may no longer see the record.
  expect(mapped).toMatchObject({ message: 'Sales users can only assign records to themselves.', denied: false })
})

it('preserves arbitrary server errors, unrecognized stages and retired stage messages', () => {
  for (const [code, message] of [
    ['INVALID_TRANSITION', 'RFQ 自定义错误'],
    ['INVALID_TRANSITION', 'Budget approval is not available at 客户备注.'],
    ['INVALID_TRANSITION', 'Unknown action is not available at demo_done.'],
    ['INVALID_TRANSITION', 'Opportunity cannot move from 需求发现 to 采购流程.'],
    ['CONFLICT', 'Opportunity must be at 客户备注 before workflow completion can move it to demo_done.'],
    // A field the resource forms do not have, and a known message under another code.
    ['VALIDATION_ERROR', 'somethingElse must be at most 140 characters.'],
    ['NOT_FOUND', 'End must be later than start.'],
    // "title" is a job title on a Contact or a Lead: the resource form's name must not be read into it.
    ['VALIDATION_ERROR', 'title is required.'],
  ] as const) {
    const error = new CrmApiError(code, message, 'req_server', false)
    setLocale('en-US')
    expect(mapRequestError(error).localizedMessage).toBeUndefined()
    expect(requestErrorMessage(error)).toBe(message)
  }
})

// Every fixed message these services raise has a translation; a new one must be added to generated-error-messages.ts,
// or it reads in English on a zh-CN screen. The pattern sees a plain double-quoted message only: one built from values
// (an f-string) is read by pattern in generated-error-messages.ts, written out with its constant and checked below, or
// answered by the page from the field errors it comes with (the Warnings page's text limits).
const FIXED_MESSAGE = /CrmApiException\(\s*"([A-Z_]+)",\s*"((?:[^"\\]|\\.)*)"/g
it.each([
  ['backend/apps/rayher_crm/rayher_crm/services/demo_resources.py', FIXED_MESSAGE],
  ['backend/apps/rayher_crm/rayher_crm/services/document_access.py', FIXED_MESSAGE],
  ['backend/apps/rayher_crm/rayher_crm/services/warning_handling.py', FIXED_MESSAGE],
  ['backend/apps/rayher_crm/rayher_crm/services/opportunity_documents.py', FIXED_MESSAGE],
  // Its ValueError texts are answered as VALIDATION_ERROR by opportunity_documents.py.
  ['backend/apps/rayher_crm/rayher_crm/services/document_links.py', /raise (ValueError)\("([^"]+)"\)/g],
])('has a translation for every fixed message of %s', (file, pattern) => {
  const source = readFileSync(resolve(file), 'utf8')
  const found = [...source.matchAll(pattern)].map(([, code, message]) => [code === 'ValueError' ? 'VALIDATION_ERROR' : code!, message!] as const)
  expect(found.length).toBeGreaterThan(0)
  for (const [code, message] of found) {
    const mapped = mapRequestError(new CrmApiError(code, message, 'req_coverage', false))
    expect(mapped.localizedMessage, `${code}: ${message}`).toBeDefined()
  }
})

it('keeps the limits written into the fixed messages in step with the services\' constants', () => {
  const constant = (file: string, name: string) => {
    const source = readFileSync(resolve(`backend/apps/rayher_crm/rayher_crm/services/${file}`), 'utf8')
    return new RegExp(`^${name} = (\\d+)$`, 'm').exec(source)![1]
  }
  const note = constant('document_access.py', 'MAX_DECISION_NOTE')
  const cap = constant('leads.py', 'MAX_ACTIVITIES')
  for (const message of [
    `The note may hold at most ${note} characters.`,
    `activities may hold at most ${cap} entries.`,
    `The Lead holds ${cap} arrangements, the most it can; remove one before adding another.`,
  ]) expect(mapRequestError(new CrmApiError('VALIDATION_ERROR', message, 'req_constant', false)).localizedMessage, message).toBeDefined()
})
