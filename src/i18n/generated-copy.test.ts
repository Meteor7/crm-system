import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import { useNotificationStore } from '@/stores/notifications'
import AppShell from '@/app/AppShell.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import InstalledToolServiceModal from '@/features/installed-tools/InstalledToolServiceModal.vue'
import InstalledToolTransitionModal from '@/features/installed-tools/InstalledToolTransitionModal.vue'
import LeadConvertModal from '@/features/leads/LeadConvertModal.vue'
import StakeholderEditorModal from '@/features/opportunities/StakeholderEditorModal.vue'
import { bookingTitle } from '@/features/shared/system-labels'
import { notificationCopy } from './notification-copy'
import { setLocale } from './index'
import type { NotificationInput } from '@/types/notifications'

it.each(['service', 'transition'])('localizes the untouched %s form default in the submitted language while preserving user edits', async (kind) => {
  const api = createMockApi({latency:0,role:'Manager'})
  const tool = (await api.getInstalledTool((await api.listInstalledTools({pageSize:1})).data.items[0].id)).data
  const wrapper = kind === 'service' ? mount(InstalledToolServiceModal, {props:{tool,actionOwners:[]}}) : mount(InstalledToolTransitionModal,{props:{stage:'FAT'}})
  const issues = wrapper.findAll('textarea').find(input=>(input.element as HTMLTextAreaElement).value==='无')!
  expect(issues.exists()).toBe(true)
  setLocale('en-US'); await flushPromises()
  expect((issues.element as HTMLTextAreaElement).value).toBe('None')
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({openIssues:'None'})
  await issues.setValue('用户填写的原始说明')
  setLocale('zh-CN'); await flushPromises(); setLocale('en-US'); await flushPromises()
  expect((issues.element as HTMLTextAreaElement).value).toBe('用户填写的原始说明')
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  expect(wrapper.emitted('submit')?.[1]?.[0]).toMatchObject({openIssues:'用户填写的原始说明'})
  wrapper.unmount()
})

it('localizes lead-conversion defaults on submit without translating the lead or user edits', async () => {
  const api = createMockApi({latency:0,role:'Manager'})
  const lead = {...(await api.listLeads({pageSize:1})).data.items[0], company:'客户公司', interest:''}
  const wrapper = mount(LeadConvertModal,{props:{lead,accounts:[],contacts:[],sites:[],segments:['Frontend']},global:{plugins:[createPinia()]}})
  setLocale('en-US'); await flushPromises()
  const inputs = wrapper.findAll('input').map(input=>(input.element as HTMLInputElement).value)
  expect(inputs).toContain('客户公司 · New project')
  expect(inputs.filter(value=>value==='To be confirmed')).toHaveLength(1)
  expect(wrapper.get<HTMLSelectElement>('select[aria-label="Equipment type"]').element.value).toBe('')
  await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
  await wrapper.get('[data-testid="lead-convert-probability-level"]').setValue('pipeline')
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({opportunityTitle:'客户公司 · New project',newSite:{process:'To be confirmed'},opportunityProbabilityLevel:'pipeline',qualificationConfirmed:true})
  await wrapper.get('select[aria-label="Equipment type"]').setValue('__custom_account_segment__')
  const tool = wrapper.get<HTMLInputElement>('input[aria-label="Equipment type"]')
  await tool.setValue('客户自定义设备')
  setLocale('zh-CN'); await flushPromises();setLocale('en-US');await flushPromises()
  expect(tool.element.value).toBe('客户自定义设备')
  wrapper.unmount()
})

it('localizes new stakeholder coverage while preserving an edited value', async () => {
  const wrapper=mount(StakeholderEditorModal,{props:{contacts:[],accountId:'ACC-1'}})
  const field=wrapper.findAll('input').find(input=>(input.element as HTMLInputElement).value==='待建立覆盖')!
  setLocale('en-US');await flushPromises()
  expect((field.element as HTMLInputElement).value).toBe('Coverage not established')
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({coverage:'Coverage not established'})
  await field.setValue('客户自行填写')
  setLocale('zh-CN');await flushPromises();setLocale('en-US');await flushPromises()
  expect((field.element as HTMLInputElement).value).toBe('客户自行填写')
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  expect(wrapper.emitted('submit')?.[1]?.[0]).toMatchObject({coverage:'客户自行填写'})
  wrapper.unmount()
})

it.each([
  ['Equipment',2,'units'], ['Equipment',1,'unit'], ['Service',1,'item'], ['Service',3,'items'],
] as const)('localizes generated %s booking title units', (bookingType,quantity,unit) => {
  const item = {equipment:'Tool X',quantity,title:`Tool X · ${quantity} 台`,bookingType}
  const original=structuredClone(item)
  expect(bookingTitle(item,'en-US')).toBe(`Tool X · ${quantity} ${unit}`)
  expect(bookingTitle(item,'zh-CN')).toBe(item.title)
  expect(item).toEqual(original)
})

it.each([
  ['Booking','Booking'], ['Demo','Demo 客户期望'], ['Evaluation','Test Run'],
] as const)('localizes both reminder thresholds for %s', (category,label) => {
  for (const days of [7,15]) {
    const item:NotificationInput={category,title:`${label} DDL 提醒 · 剩余 ${days} 天`,message:`SOURCE-1 的 ${label} DDL 为 2026-10-12，距离截止还有 ${days} 天，请及时跟进。`,route:'/demo-workflow'}
    const translated=notificationCopy(item,'en-US')
    expect(translated.title).toContain(`${days} days remaining`)
    expect(translated.message).toContain('SOURCE-1')
    expect(translated.message).toContain('2026-10-12')
    expect(translated.message).toContain(`${days} days remain`)
    expect(`${translated.title} ${translated.message}`).not.toMatch(/\p{Script=Han}/u)
    expect(notificationCopy(item,'zh-CN')).toEqual({title:item.title,message:item.message})
  }
})

it('changes existing shell notification copy without rewriting business content', async () => {
  const api=createMockApi({latency:0,role:'Manager'})
  const pinia=createPinia()
  const app=useAppStore(pinia)
  app.bootstrap=(await api.getBootstrap()).data
  app.activeApi=api
  const store=useNotificationStore(pinia)
  const item:NotificationInput={category:'Demo',title:'Alex @你确认 Demo',message:'DR-1 · 客户原始备注',route:'/demo-workflow/DR-1'}
  store.add(item)
  const router=createAppRouter();await router.push('/dashboard')
  const wrapper=mount(AppShell,{global:{plugins:[pinia,router],stubs:{RouterView:true}}})
  await wrapper.get('[data-testid="notification-button"]').trigger('click');await flushPromises()
  expect(wrapper.get('.notification-list strong').text()).toBe(item.title)
  setLocale('en-US');await flushPromises()
  expect(wrapper.get('.notification-list strong').text()).toBe('Alex mentioned you on a Demo')
  expect(wrapper.get('.notification-list small').text()).toBe(item.message)
  expect(store.items[0].title).toBe(item.title)
  wrapper.unmount()
})


it.each([
  ['Opportunity', '预警：丢单待复盘', 'Edge inspection（长飞先进）已丢单，请完成复盘。', 'Warning: lost deal awaiting review', 'Edge inspection（长飞先进） was lost; please complete the loss review.'],
  ['Action', '预警：行动逾期', 'Edge inspection（长飞先进）的行动「送样确认」原定 2026-09-30 完成，已逾期。', 'Warning: action overdue', 'Edge inspection（长飞先进）: the action "送样确认" was due 2026-09-30 and is overdue.'],
  ['Quotation', '预警：报价即将到期', '报价 Edge inspection（长飞先进）V2 将于 2026-10-12 到期，还剩 7 天。', 'Warning: quotation expiring', 'Quotation Edge inspection（长飞先进）V2 expires on 2026-10-12; 7 days remain.'],
  ['Quotation', '预警：报价即将到期', '报价 Edge inspection（长飞先进）V2 将于 2026-10-06 到期，还剩 1 天。', 'Warning: quotation expiring', 'Quotation Edge inspection（长飞先进）V2 expires on 2026-10-06; 1 day remains.'],
  ['Opportunity', '预警：第 6 阶段超期无 PO', 'Edge inspection（长飞先进）已在第 6 阶段 1 天，仍未收到 PO。', 'Warning: stage 6 overdue without PO', 'Edge inspection（长飞先进） has been at stage 6 for 1 day with no PO received.'],
  ['Opportunity', '预警：第 6 阶段超期无 PO', 'Edge inspection（长飞先进）已在第 6 阶段 45 天以上，仍未收到 PO。', 'Warning: stage 6 overdue without PO', 'Edge inspection（长飞先进） has been at stage 6 for 45 days or more with no PO received.'],
] as const)('reads the server\'s %s warning notice in English, keeping its data', (category, title, message, englishTitle, englishMessage) => {
  const item: NotificationInput = { category, title, message, route: '/opportunities/OP-1' }
  expect(notificationCopy(item, 'en-US')).toEqual({ title: englishTitle, message: englishMessage })
  expect(notificationCopy(item, 'zh-CN')).toEqual({ title, message })
  // A body the server did not write this way (an older format) keeps its text; the title still reads in English.
  const other = { ...item, message: '自定义正文' }
  expect(notificationCopy(other, 'en-US')).toEqual({ title: englishTitle, message: '自定义正文' })
})

it('keeps the brackets and line breaks of the data inside a warning notice', () => {
  // An action's title may hold the notice's own brackets, even its "的行动「"; a record's title may break a line.
  const action: NotificationInput = { category: 'Action', title: '预警：行动逾期', message: 'Edge inspection（长飞先进）的行动「复核客户的行动「送样确认」」原定 2026-09-30 完成，已逾期。', route: '/opportunities/OP-1' }
  expect(notificationCopy(action, 'en-US').message).toBe('Edge inspection（长飞先进）: the action "复核客户的行动「送样确认」" was due 2026-09-30 and is overdue.')
  const broken = { ...action, message: 'Edge\ninspection（长飞先进）的行动「送样\n确认」原定 2026-09-30 完成，已逾期。' }
  expect(notificationCopy(broken, 'en-US').message).toBe('Edge\ninspection（长飞先进）: the action "送样\n确认" was due 2026-09-30 and is overdue.')
  const lost: NotificationInput = { category: 'Opportunity', title: '预警：丢单待复盘', message: 'Edge\ninspection（长飞先进）已丢单，请完成复盘。', route: '/opportunities/OP-1' }
  expect(notificationCopy(lost, 'en-US').message).toBe('Edge\ninspection（长飞先进） was lost; please complete the loss review.')
})

it('keeps an action notice as written when its record or customer could be split in more than one place', () => {
  const base = { category: 'Action' as const, title: '预警：行动逾期', route: '/opportunities/OP-1' }
  // The Opportunity's title holds the notice's own separator: two places to split, no reading.
  const record = { ...base, message: '复核客户（旧厂）的行动「送样确认」（长飞先进）的行动「联系采购」原定 2026-09-30 完成，已逾期。' }
  expect(notificationCopy(record, 'en-US')).toEqual({ title: 'Warning: action overdue', message: record.message })
  // The customer holds it.
  const customer = { ...base, message: 'Edge inspection（长飞（旧厂）的行动「x」）的行动「联系采购」原定 2026-09-30 完成，已逾期。' }
  expect(notificationCopy(customer, 'en-US')).toEqual({ title: 'Warning: action overdue', message: customer.message })
  // Brackets of their own, one place to split: read.
  const plain = { ...base, message: '复核客户（旧厂）（长飞先进）的行动「联系采购」原定 2026-09-30 完成，已逾期。' }
  expect(notificationCopy(plain, 'en-US').message).toBe('复核客户（旧厂）（长飞先进）: the action "联系采购" was due 2026-09-30 and is overdue.')
  expect(notificationCopy(plain, 'zh-CN')).toEqual({ title: plain.title, message: plain.message })
})

it('keeps unrelated server notification text intact even when its title matches local copy', () => {
  const item: NotificationInput = { category: 'Action', title: '新增推进 Action', message: '客户自定义正文 · 截止 2026-09-14', route: '/opportunities/OP-1' }
  expect(notificationCopy(item, 'en-US')).toEqual({ title: item.title, message: item.message })
  expect(notificationCopy({ ...item, generatedLocally: true }, 'en-US')).toEqual({ title: 'New opportunity action', message: '客户自定义正文 · Due 2026-09-14' })
  const incomplete: NotificationInput = { category: 'Booking', title: 'Booking DDL 提醒 · 剩余 7 天', message: '客户自行编写的通知', route: '/booking/B-1' }
  expect(notificationCopy(incomplete, 'en-US')).toEqual({ title: incomplete.title, message: incomplete.message })
})
