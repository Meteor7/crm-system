import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import { quotationCatalogLabel } from './catalog-labels'
import QuotationCatalogFilter from './QuotationCatalogFilter.vue'
import QuotationEditor from './QuotationEditor.vue'
import type { QuotationDraftInput, QuotationItemDto } from './types'

it('covers every Chinese name in the real Frappe catalog seed', () => {
  const source = readFileSync(resolve('backend/apps/rayher_crm/rayher_crm/services/quotations.py'), 'utf8').split('INITIAL_QUOTATION_CATALOG = (')[1].split('def _normalize_catalog_name')[0]
  const names = [...new Set([...source.matchAll(/"([^"\r\n]+)"/g)].map(match => match[1]).filter(name => /\p{Script=Han}/u.test(name)))]
  expect(names.length).toBeGreaterThan(15)
  for (const name of names) {
    expect(quotationCatalogLabel(name, 'en-US'), name).not.toMatch(/\p{Script=Han}/u)
    expect(quotationCatalogLabel(name, 'zh-CN')).toBe(name)
  }
})

it('searches English catalog captions while emitting the original item', async () => {
  const item = { id: 'CAT-SYSTEM', name: '晶圆传输系统 EFEM', level: 'System' as const, parentId: 'CAT-DEVICE' }
  setLocale('en-US')
  const wrapper = mount(QuotationCatalogFilter, { props: { options: [item], label: 'System', placeholder: 'Add system', customPlaceholder: 'Custom name', testId: 'catalog' } })
  await wrapper.get('[role="combobox"]').trigger('click')
  await wrapper.get('.catalog-search input').setValue('wafer transfer')
  expect(wrapper.get('[role="option"]').text()).toBe('Wafer transfer system (EFEM)')
  await wrapper.get('[role="option"]').trigger('click')
  expect(wrapper.emitted('select')?.[0]).toEqual([item])
  expect(item.name).toBe('晶圆传输系统 EFEM')
  wrapper.unmount()
})

it('translates catalog-backed selected names without changing the quotation draft', async () => {
  const item = (lineKey: string, lineType: QuotationItemDto['lineType'], name: string, catalogItemId: string, parentDeviceKey = '', parentSystemKey = ''): QuotationItemDto => ({ lineKey, lineType, name, catalogItemId, parentDeviceKey, parentSystemKey, model: '', description: '', pricingMode: 'Included', quantity: 1, unitPrice: '0', lineAmount: '0' })
  const modelValue: QuotationDraftInput = { primaryContactId: '', addressId: '', quoteDate: '2026-09-07', validityMonths: 3, discountType: 'None', discountValue: '0', paymentTerms: [], deliveryMonths: 3, warrantyMonths: 12, items: [item('D','Device','Drakens 4482 宏观缺陷自动检测设备(6”/8”/12”)','CAT-D'), item('S','System','晶圆传输系统 EFEM','CAT-S','D'), item('A','Accessory','离子棒','CAT-A','D','S'), item('CUSTOM','Device','客户自定义设备','')] }
  const original = structuredClone(modelValue)
  const wrapper = mount(QuotationEditor, { props: { modelValue, contacts: [], sites: [], quotationType: 'Device' } })
  setLocale('en-US'); await flushPromises()
  expect(wrapper.get('.system-card header strong').text()).toBe('Wafer transfer system (EFEM)')
  expect(wrapper.get<HTMLInputElement>('input[aria-label="Accessory name"]').element.value).toBe('Ionizing bar')
  expect(wrapper.findAll('input[aria-label="Equipment name"]').map(input => (input.element as HTMLInputElement).value)).toEqual(['Drakens 4482 automatic macro defect inspection system (6”/8”/12”)', '客户自定义设备'])
  expect(modelValue).toEqual(original)
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  wrapper.unmount()
})
