import { createPinia } from 'pinia'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import DashboardHomePage from './DashboardHomePage.vue'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'

enableAutoUnmount(afterEach)

const stubs = {
  ReviewPage: { template: '<div data-testid="sales-cockpit" />' },
  DashboardPage: { template: '<div data-testid="information-centre" />' },
}

async function mountAs(role: UserRole) {
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role }).getBootstrap()).data
  const wrapper = mount(DashboardHomePage, { global: { plugins: [pinia], stubs } })
  await flushPromises()
  return wrapper
}

describe('Dashboard home', () => {
  it('opens the sales cockpit for Manager', async () => {
    const wrapper = await mountAs('Manager')

    expect(wrapper.find('[data-testid="sales-cockpit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="information-centre"]').exists()).toBe(false)
  })

  it('waits for the session instead of opening the information centre for a Manager', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const pinia = createPinia()
    const wrapper = mount(DashboardHomePage, { props: { apiClient: api }, global: { plugins: [pinia], stubs } })

    expect(wrapper.find('[data-testid="information-centre"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="sales-cockpit"]').exists()).toBe(false)

    await flushPromises()

    expect(wrapper.find('[data-testid="sales-cockpit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="information-centre"]').exists()).toBe(false)
  })

  it('keeps the information centre for Sales and Engineer', async () => {
    for (const role of ['Sales', 'Engineer'] as const) {
      const wrapper = await mountAs(role)

      expect(wrapper.find('[data-testid="information-centre"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="sales-cockpit"]').exists()).toBe(false)
    }
  })
})
