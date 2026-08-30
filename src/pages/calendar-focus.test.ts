import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import EvaluationsPage from './EvaluationsPage.vue'
import VisitsPage from './VisitsPage.vue'

async function routeContext(path: string) {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  return { api, pinia, router }
}

describe('Calendar focus handoff', () => {
  it('loads and selects an Evaluation that is outside the first list page', async () => {
    const { api, pinia, router } = await routeContext('/evaluations')
    const all = await api.listEvaluations({ page: 1, pageSize: 200 })
    const active = all.data.items.filter((item) => !['Accepted', 'Rejected'].includes(item.status))
    const target = active.at(-1)!
    const unrelated = active.find((item) => item.id !== target.id)!
    api.listEvaluations = async () => ({
      data: { items: [unrelated] },
      meta: { requestId: 'req_evaluation_page', page: 1, pageSize: 20, total: 21 },
      warnings: [],
    })
    ;(api as unknown as { getEvaluation: (id: string) => Promise<{ data: typeof target; meta: { requestId: string }; warnings: [] }> }).getEvaluation = async () => ({
      data: target,
      meta: { requestId: 'req_evaluation_focus' },
      warnings: [],
    })
    await router.push(`/evaluations?focus=${target.id}`)

    const wrapper = mount(EvaluationsPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.get(`[data-evaluation="${target.id}"]`).classes()).toContain('selected')
    expect(wrapper.get('[data-demo-test-focus]').text()).toContain(target.id)
  })

  it('loads, highlights, and keeps a Visit that is outside the first list page', async () => {
    const { api, pinia, router } = await routeContext('/visits')
    const all = await api.listVisits({ page: 1, pageSize: 200 })
    const target = all.data.items.at(-1)!
    const unrelated = all.data.items.find((item) => item.id !== target.id)!
    api.listVisits = async () => ({
      data: { items: [unrelated] },
      meta: { requestId: 'req_visit_page', page: 1, pageSize: 20, total: 201 },
      warnings: [],
    })
    ;(api as unknown as { getVisit: (id: string) => Promise<{ data: typeof target; meta: { requestId: string }; warnings: [] }> }).getVisit = async () => ({
      data: target,
      meta: { requestId: 'req_visit_focus' },
      warnings: [],
    })
    await router.push(`/visits?focus=${target.id}`)

    const wrapper = mount(VisitsPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.get(`[data-visit-id="${target.id}"]`).classes()).toContain('focused')
    expect(wrapper.find(`[data-visit-id="${unrelated.id}"]`).exists()).toBe(true)
  })
})
