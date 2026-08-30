import { describe, expect, it } from 'vitest'
import { createAppRouter } from './router'

describe('Leads, Opportunities and Booking routes', () => {
  it('keeps Lead detail inside the Leads navigation section', async () => {
    const router = createAppRouter()
    await router.push('/leads/LEAD-001')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('lead-detail')
    expect(router.currentRoute.value.meta.navigationPath).toBe('/leads')
  })

  it('keeps Opportunity detail inside the Opportunities navigation section', async () => {
    const router = createAppRouter()
    await router.push('/opportunities/OPP-003')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('opportunity-detail')
    expect(router.currentRoute.value.meta.navigationPath).toBe('/opportunities')
  })

  it('keeps Quotation detail inside the Quotations navigation section', async () => {
    const router = createAppRouter()
    await router.push('/quotations/CRM-QTN-00001')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('quotation-detail')
    expect(router.currentRoute.value.meta.navigationPath).toBe('/quotations')
  })

  it('keeps Demo detail inside the Demo archive navigation section', async () => {
    const router = createAppRouter()
    await router.push('/demo-workflow/DR-105')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('demo-detail')
    expect(router.currentRoute.value.meta.navigationPath).toBe('/demo-workflow')
  })

  it('redirects retired combined routes without losing useful query context', async () => {
    const router = createAppRouter()

    await router.push('/pipeline')
    expect(router.currentRoute.value).toMatchObject({ path: '/opportunities', query: {} })

    await router.push('/opportunity-strategy?contactId=CON-001')
    expect(router.currentRoute.value).toMatchObject({
      path: '/opportunities',
      query: { contactId: 'CON-001' },
    })

    await router.push('/opportunities-booking?view=bookings&contactId=CON-009')
    expect(router.currentRoute.value).toMatchObject({ path: '/booking', query: { contactId: 'CON-009' } })

    await router.push('/opportunities-booking?view=opportunities&accountId=ACC-001')
    expect(router.currentRoute.value).toMatchObject({
      path: '/opportunities',
      query: { accountId: 'ACC-001' },
    })

    await router.push('/leads-opportunities?view=leads&source=event')
    expect(router.currentRoute.value).toMatchObject({ path: '/leads', query: { source: 'event' } })
  })
})
