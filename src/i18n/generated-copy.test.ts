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
  expect(inputs.filter(value=>value==='To be confirmed')).toHaveLength(2)
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({toolType:'To be confirmed',opportunityTitle:'客户公司 · New project',newSite:{process:'To be confirmed'}})
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


it('keeps unrelated server notification text intact even when its title matches local copy', () => {
  const item: NotificationInput = { category: 'Action', title: '新增推进 Action', message: '客户自定义正文 · 截止 2026-09-14', route: '/opportunities/OP-1' }
  expect(notificationCopy(item, 'en-US')).toEqual({ title: item.title, message: item.message })
  expect(notificationCopy({ ...item, generatedLocally: true }, 'en-US')).toEqual({ title: 'New opportunity action', message: '客户自定义正文 · Due 2026-09-14' })
  const incomplete: NotificationInput = { category: 'Booking', title: 'Booking DDL 提醒 · 剩余 7 天', message: '客户自行编写的通知', route: '/booking/B-1' }
  expect(notificationCopy(incomplete, 'en-US')).toEqual({ title: incomplete.title, message: incomplete.message })
})
