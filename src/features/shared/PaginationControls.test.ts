import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PaginationControls from './PaginationControls.vue'

describe('PaginationControls', () => {
  it('shows total and emits only valid previous and next pages', async () => {
    const wrapper = mount(PaginationControls, { props: { page: 2, pageSize: 20, total: 45 } })

    expect(wrapper.text()).toContain('第 2 / 3 页')
    expect(wrapper.text()).toContain('共 45 条')
    await wrapper.get('[data-page-previous]').trigger('click')
    await wrapper.get('[data-page-next]').trigger('click')
    expect(wrapper.emitted('change')).toEqual([[1], [3]])
  })

  it('disables movement at the only page', () => {
    const wrapper = mount(PaginationControls, { props: { page: 1, pageSize: 20, total: 0 } })
    expect(wrapper.get('[data-page-previous]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-page-next]').attributes('disabled')).toBeDefined()
  })

  it('offers standard sizes and emits a size change', async () => {
    const wrapper = mount(PaginationControls, { props: { page: 1, pageSize: 12, total: 80 } })
    expect(wrapper.get('[aria-label="每页数量"]').findAll('option').map((item) => item.text())).toEqual(['10', '12', '25', '50'])
    await wrapper.get('[aria-label="每页数量"]').setValue('25')
    expect(wrapper.emitted('page-size-change')).toEqual([[25]])
  })
})
