import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { createMockApi } from '@/api/mock-adapter'
import { accountSitesOf } from '@/features/accounts/mock-account-sites'
import { useAppStore } from '@/stores/app'
import { createAppRouter } from '@/app/router'
import OpportunityListView from '@/features/opportunities/OpportunityListView.vue'
import ContactsPage from './ContactsPage.vue'
import LeadDetailPage from './LeadDetailPage.vue'
import OpportunityDetailPage from './OpportunityDetailPage.vue'
import OpportunityStrategyPage from './OpportunityStrategyPage.vue'

// These pages offer the Sites of every Account. They used to read one Account 360 per Account (#136).
async function open(page: Component, path: string) {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const sites = await accountSitesOf(api)
  const account360 = vi.spyOn(api, 'getAccount360')
  const accountSites = vi.spyOn(api, 'listAccountSites').mockResolvedValue({ data: sites, warnings: [] })
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(page, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { api, wrapper, sites, account360, accountSites }
}

describe('pages that offer the Sites of every Account', () => {
  it.each([
    ['Opportunities list', OpportunityListView, '/leads-opportunities?view=opportunities'],
    ['Opportunity detail', OpportunityDetailPage, '/opportunities/OPP-001'],
    ['Opportunity strategy', OpportunityStrategyPage, '/leads-opportunities?view=opportunities'],
    ['Contacts', ContactsPage, '/contacts'],
    ['Lead detail', LeadDetailPage, '/leads/LEAD-002'],
  ] as const)('%s reads them in one request and no Account 360', async (_name, page, path) => {
    const { wrapper, account360, accountSites } = await open(page, path)

    expect(accountSites).toHaveBeenCalledTimes(1)
    expect(account360).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('offers the Sites of the chosen Account in the Opportunity editor', async () => {
    const { api, wrapper, sites } = await open(OpportunityDetailPage, '/opportunities/OPP-001')
    const opportunity = (await api.getStrategyOpportunity('OPP-001')).data
    const expected = sites.filter((site) => site.accountId === opportunity.accountId)

    await wrapper.get('[data-testid="edit-opportunity"]').trigger('click')
    await flushPromises()

    const select = wrapper.findAll('select').find((item) => item.element.value === opportunity.siteId)!
    expect(expected.length).toBeGreaterThan(0)
    expect(select.findAll('option').map((option) => option.element.value)).toEqual(expected.map((site) => site.id))
    wrapper.unmount()
  })
})
