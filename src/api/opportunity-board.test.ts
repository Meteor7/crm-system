import { describe, expect, it, vi } from 'vitest'
import { createFrappeApi } from './frappe-adapter'
import { defaultDefinition, toQuery } from '@/features/opportunity-board/model'
describe('board API transport', () => {
  it('posts nested inputs with CSRF and keeps saved-query versions outside input', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ message: { data: {}, warnings: [] } }), { status: 200 }))
    const api = createFrappeApi({ fetchImpl, csrfToken: () => 'test-csrf' })
    const query = toQuery(defaultDefinition())
    await api.queryOpportunities(query)
    await api.getOpportunityFilters()
    await api.listOpportunityQueries()
    await api.saveOpportunityQuery({ name: '<test>', definition: defaultDefinition() }, 'saved', 'version')
    await api.deleteOpportunityQuery('saved', 'version')
    const calls = fetchImpl.mock.calls as unknown as [string, RequestInit][]
    expect(calls.map(c => String(c[0]))).toEqual([
      '/api/method/rayher_crm.api.v1.cockpit.query_opportunities',
      '/api/method/rayher_crm.api.v1.cockpit.get_opportunity_filters',
      '/api/method/rayher_crm.api.v1.cockpit.list_opportunity_queries',
      '/api/method/rayher_crm.api.v1.cockpit.save_opportunity_query',
      '/api/method/rayher_crm.api.v1.cockpit.delete_opportunity_query',
    ])
    expect(calls[0][1].method).toBe('POST')
    expect(new Headers(calls[0][1].headers).get('X-Frappe-CSRF-Token')).toBe('test-csrf')
    expect(JSON.parse(new URLSearchParams(String(calls[0][1].body)).get('input')!)).toEqual(query)
    const save = new URLSearchParams(String(calls[3][1].body))
    expect(save.get('id')).toBe('saved'); expect(save.get('expectedModified')).toBe('version')
    expect(JSON.parse(save.get('input')!).name).toBe('<test>')
    expect(new URLSearchParams(String(calls[4][1].body)).get('expectedModified')).toBe('version')
  })
})

