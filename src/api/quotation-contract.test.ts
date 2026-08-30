import { describe, expect, it, vi } from 'vitest'
import { createFrappeApi, FRAPPE_METHODS } from './frappe-adapter'

function success(data: unknown) {
  return new Response(JSON.stringify({ message: { data, meta: { requestId: 'req-q' }, warnings: [] } }), { headers: { 'Content-Type': 'application/json' } })
}

describe('Quotation Frappe contract', () => {
  it('maps the full quotation lifecycle to v1 endpoints', () => {
    expect(FRAPPE_METHODS).toMatchObject({
      listQuotations: 'quotations.list_quotations', listQuotationCatalog: 'quotations.list_catalog', getQuotation: 'quotations.get_quotation',
      createQuotation: 'quotations.create_quotation', saveQuotationDraft: 'quotations.save_draft',
      createQuotationVersion: 'quotations.create_version', discardQuotationDraft: 'quotations.discard_draft',
      publishQuotation: 'quotations.publish_version', recordQuotationDecision: 'quotations.record_decision',
      submitQuotationForApproval: 'quotations.submit_for_approval', reviewQuotationApproval: 'quotations.review_approval',
      linkQuotationOpportunity: 'quotations.link_opportunity',
      getQuotationPreviewPdf: 'quotations.preview_pdf',
      getQuotationPdf: 'quotations.download_pdf',
    })
  })

  it('sends optimistic concurrency tokens for every mutable lifecycle action', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ quotation: {}, version: {}, versions: [] })))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    await api.saveQuotationDraft('CRM-QTN-00001', { items: [] } as never, '2026-08-10T10:00:00Z')
    await api.discardQuotationDraft('CRM-QTN-00001', '2026-08-10T10:01:00Z')
    await api.submitQuotationForApproval('CRM-QTN-00001', '2026-08-10T10:02:00Z')
    await api.reviewQuotationApproval('CRM-QTN-00001', { decision: 'Rejected', comment: 'Revise price', expectedModified: '2026-08-10T10:03:00Z' })
    await api.recordQuotationDecision('CRM-QTN-00001', { decision: 'Accepted', feedbackDate: '2026-08-10', feedbackNote: 'PO confirmed', expectedModified: '2026-08-10T10:04:00Z' })
    await api.linkQuotationOpportunity('CRM-QTN-00001', 'CRM-OPP-00001', '2026-08-10T10:05:00Z')
    const saveBody = new URLSearchParams(String((fetchMock.mock.calls[0]![1] as RequestInit).body))
    const discardBody = new URLSearchParams(String((fetchMock.mock.calls[1]![1] as RequestInit).body))
    const submitBody = new URLSearchParams(String((fetchMock.mock.calls[2]![1] as RequestInit).body))
    const reviewBody = new URLSearchParams(String((fetchMock.mock.calls[3]![1] as RequestInit).body))
    const decisionBody = new URLSearchParams(String((fetchMock.mock.calls[4]![1] as RequestInit).body))
    const linkBody = new URLSearchParams(String((fetchMock.mock.calls[5]![1] as RequestInit).body))
    expect(saveBody.get('expectedModified')).toBe('2026-08-10T10:00:00Z')
    expect(JSON.parse(saveBody.get('input')!)).toEqual({ items: [] })
    expect(discardBody.get('expectedModified')).toBe('2026-08-10T10:01:00Z')
    expect(submitBody.get('expectedModified')).toBe('2026-08-10T10:02:00Z')
    expect(reviewBody.get('decision')).toBe('Rejected')
    expect(reviewBody.get('comment')).toBe('Revise price')
    expect(decisionBody.get('decision')).toBe('Accepted')
    expect(decisionBody.get('expectedModified')).toBe('2026-08-10T10:04:00Z')
    expect(linkBody.get('opportunityId')).toBe('CRM-OPP-00001')
    expect(linkBody.get('expectedModified')).toBe('2026-08-10T10:05:00Z')
  })
})
