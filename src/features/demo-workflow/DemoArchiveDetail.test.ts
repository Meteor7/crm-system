import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import type { EvaluationDto } from '@/types/crm'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoArchiveDetail from './DemoArchiveDetail.vue'

function completedRun(id: string, round: number, date: string, capture: number) {
  return {
    id, round, date, lot: `LOT-${id}`, wafers: 1, status: 'Completed' as const,
    capture, falsePositive: 1, wph: 12, summary: `Round ${round} result`,
  }
}

describe('DemoArchiveDetail', () => {
  it('names the retest round of every archived Test Run', () => {
    // A retest keeps the earlier round's runs next to the new ones, so each row has
    // to say which round its metrics belong to.
    const evaluation = {
      id: 'EVAL-1', status: 'Testing', testRound: 2,
      runs: [completedRun('RUN-1', 1, '2026-08-11', 90), completedRun('RUN-2', 2, '2026-08-20', 97)],
    } as unknown as EvaluationDto
    const item = {
      id: 'DR-1', title: 'Retested Demo', status: 'Testing', evaluation,
      artifacts: [], customerReviews: [], testRound: 2, conclusion: { status: 'Pending' },
    } as unknown as DemoWorkflowDto

    const wrapper = mount(DemoArchiveDetail, { props: { item, showOverview: false, showTimeline: false } })
    const table = wrapper.get('[data-demo-sensitive="test-runs"]')

    expect(table.get('thead').text()).toContain('轮次')
    expect(table.findAll('tbody tr').map((row) => [row.get('td strong').text(), row.get('[data-run-round]').text()]))
      .toEqual([['RUN-1', '第 1 轮'], ['RUN-2', '第 2 轮']])
  })

  // The archive projection as the server returns it after a reload: termination keeps the
  // Rejected status, records a reason and leaves the customer acceptance as it was.
  function archived(status: 'Accepted' | 'Rejected', acceptance: 'Pending' | 'Accepted' | 'Rejected', terminationReason = '') {
    const evaluation = { id: 'EVAL-9', status, testRound: 1, runs: [] } as unknown as EvaluationDto
    return {
      id: 'DR-9', title: 'Archived Demo', status, terminationReason, evaluation, account: 'Customer',
      salesOwner: 'sales', engineerOwner: 'engineer', archiveCategory: 'Completed',
      artifacts: [], customerReviews: [], testRound: 1, conclusion: { status: acceptance },
    } as unknown as DemoWorkflowDto
  }
  const labels = (wrapper: ReturnType<typeof mount>) => [
    wrapper.get('.archive-overview .workspace-badge').text(),
    wrapper.get('[data-demo-sensitive="test-runs"] header span').text(),
    wrapper.get('.conclusion-panel .workspace-badge').text(),
  ]

  it('shows a terminated Demo as terminated with its reason and the untouched customer review apart', async () => {
    const item = archived('Rejected', 'Pending', 'Customer paused the project')
    const wrapper = mount(DemoArchiveDetail, { props: { item, showTimeline: false } })

    expect(labels(wrapper)).toEqual(['已终止', '已终止', '已终止'])
    expect(wrapper.get('.conclusion-panel [data-termination-reason]').text()).toBe('终止原因Customer paused the project')
    expect(wrapper.get('.conclusion-panel [data-customer-review-status]').text()).toBe('客户评审未评审')
    expect(wrapper.get('.conclusion-panel').text()).not.toContain('暂无正式结论')
    expect(wrapper.get('.conclusion-panel').text()).not.toContain('待确认')
    setLocale('en-US')
    await flushPromises()
    expect(labels(wrapper)).toEqual(['Terminated', 'Terminated', 'Terminated'])
    expect(wrapper.get('.conclusion-panel [data-customer-review-status]').text()).toBe('Customer reviewNot reviewed')
    expect(wrapper.get('.conclusion-panel [data-termination-reason]').text()).toContain('Customer paused the project')
  })

  it.each([
    ['a historical rejection', archived('Rejected', 'Rejected'), '已拒绝'],
    ['an accepted Demo', archived('Accepted', 'Accepted'), '已接受'],
  ])('keeps the original labels for %s', (_label, item, label) => {
    const wrapper = mount(DemoArchiveDetail, { props: { item, showTimeline: false } })
    expect(labels(wrapper)).toEqual([label, label, label])
    expect(wrapper.get('.conclusion-panel').text()).toContain('暂无正式结论')
    expect(wrapper.text()).not.toContain('已终止')
    expect(wrapper.find('[data-termination-reason]').exists()).toBe(false)
  })
})
