import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { formatMoney } from '@/domain/money'
import { useAppStore } from '@/stores/app'
import AccountProfile from './AccountProfile.vue'

enableAutoUnmount(afterEach)

async function profile(confirmed: boolean) {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const pinia = createPinia()
  const app = useAppStore(pinia)
  app.bootstrap = (await api.getBootstrap()).data
  app.activeApi = api
  const router = createAppRouter()
  await router.push('/accounts/ACC-001')
  const response = await api.getAccount360('ACC-001')
  const sample = (await api.listBookings({ pageSize: 1 })).data.items[0]!
  response.data.bookings = confirmed ? [{ ...sample, accountId: 'ACC-001', status: 'Confirmed' }] : []
  vi.spyOn(api, 'getAccount360').mockResolvedValue(response)
  const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, bookings: response.data.bookings }
}

// A Private Account of someone else and an Account that does not exist answer the same (F1-12): one state, no retry.
it('shows one state, without a retry, for an Account the user cannot open', async () => {
  const api = createMockApi({ latency: 0, role: 'Sales' })
  const pinia = createPinia()
  const app = useAppStore(pinia)
  app.bootstrap = (await api.getBootstrap()).data
  app.activeApi = api
  const router = createAppRouter()
  await router.push('/accounts/ACC-001')
  vi.spyOn(api, 'getAccount360').mockRejectedValue(new CrmApiError('NOT_FOUND', 'Account was not found, or you have no access to it.', 'req_hidden'))
  const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  const state = wrapper.get('.data-state')
  expect(state.text()).toContain('无法打开这条记录')
  expect(state.text()).toContain('找不到这个客户，或者你没有查看权限。')
  expect(state.text()).toContain('req_hidden')
  expect(state.find('button').exists()).toBe(false)
})

// The figure was left blank when the Account had no confirmed Booking (#137).
it('shows a dash for the confirmed Booking figure when the Account has none', async () => {
  const { wrapper } = await profile(false)

  expect(wrapper.get('[data-testid="confirmed-booking-none"]').text()).toBe('—')
})

it('shows the confirmed Booking amount and no dash when the Account has one', async () => {
  const { wrapper, bookings } = await profile(true)

  expect(wrapper.text()).toContain(formatMoney(bookings[0]!.amount, bookings[0]!.currency))
  expect(wrapper.find('[data-testid="confirmed-booking-none"]').exists()).toBe(false)
})
