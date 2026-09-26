import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
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
})
