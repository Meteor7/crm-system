import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import AccountsPage from './AccountsPage.vue'
import PipelinePage from './PipelinePage.vue'

async function testGlobal(path: string) {
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  return { plugins: [createPinia(), router, ElementPlus], stubs: { teleport: true } }
}

describe('MVP workflow pages', () => {
  it('opens the Account detail page from a filtered customer row', async () => {
    const wrapper = mount(AccountsPage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: await testGlobal('/accounts'),
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('列表 Pipeline')
    expect(wrapper.findAll('th').map((cell) => cell.text())).not.toContain('Pipeline')
    await wrapper.get('[aria-label="城市"]').setValue('上海')
    await vi.waitFor(() => expect(wrapper.find('[data-account-id="ACC-002"]').exists()).toBe(false))
    await wrapper.get('[data-open-account-detail="ACC-001"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.vm.$route.name).toBe('account-detail'))
    expect(wrapper.vm.$route.params.accountId).toBe('ACC-001')
  })

  it('keeps open pipeline and confirmed booking visibly separate', async () => {
    const wrapper = mount(PipelinePage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: await testGlobal('/pipeline'),
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Open Pipeline')
    expect(wrapper.text()).toContain('Confirmed Booking')
    expect(wrapper.text()).toContain('商机口径不包含 Won / Lost')
  })

  it('keeps stage filters after removing the page search box', async () => {
    const wrapper = mount(PipelinePage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: await testGlobal('/pipeline'),
    })
    await flushPromises()

    expect(wrapper.find('[aria-label="搜索商机"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="商机阶段"]').exists()).toBe(true)
  })

})
