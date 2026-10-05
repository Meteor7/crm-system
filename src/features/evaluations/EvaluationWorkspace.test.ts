import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { evaluations } from '@/api/mock-data'
import { setLocale } from '@/i18n'
import type { EvaluationDto } from '@/types/crm'
import EvaluationWorkspace from './EvaluationWorkspace.vue'

describe('EvaluationWorkspace', () => {
  it('pages each view on its own, counts the whole view and keeps the selected record on show', async () => {
    // Everything in progress: 8 being tested for one Account, 6 being prepared for another.
    const base = evaluations.find((item) => item.id === 'EVAL-103')!
    const make = (index: number, status: EvaluationDto['status'], accountId: string): EvaluationDto =>
      ({ ...base, id: `EVAL-P${String(index).padStart(2, '0')}`, status, accountId, accountName: `Account ${accountId}` })
    const rows = [
      ...Array.from({ length: 8 }, (_, index) => make(index, 'Testing', 'A')),
      ...Array.from({ length: 6 }, (_, index) => make(10 + index, 'Requested', 'B')),
    ]
    // The page above holds the selected record and takes the one the workspace hands up, as EvaluationsPage does.
    const wrapper = mount(EvaluationWorkspace, {
      props: { view: 'overview', evaluations: rows, selectedId: rows[0].id, canWrite: true, onSelect: (id: string) => { void wrapper.setProps({ selectedId: id }) } },
    })
    const shown = () => wrapper.findAll('[data-evaluation]').map((row) => row.attributes('data-evaluation'))
    const onShow = () => wrapper.get('tr.selected').attributes('data-evaluation')
    const held = () => wrapper.props('selectedId')
    const count = () => wrapper.get('.row-count').text()
    const pager = () => wrapper.find('.pagination-controls')
    const next = async () => { await pager().get('[data-page-next]').trigger('click'); await flushPromises() }
    const ids = (list: EvaluationDto[]) => list.map((item) => item.id)

    expect(shown()).toEqual(ids(rows.slice(0, 6)))
    expect(count()).toMatch(/· 14$/)
    expect(pager().get('small').text()).toContain('14')
    // Turning the page puts its first record on show, and that record is handed up as the selected one.
    await next()
    expect(shown()).toEqual(ids(rows.slice(6, 12)))
    expect([onShow(), held()]).toEqual([rows[6].id, rows[6].id])
    await next()
    expect(shown()).toEqual(ids(rows.slice(12)))
    expect([onShow(), held()]).toEqual([rows[12].id, rows[12].id])

    // A view that does not hold the selected record starts on its first page, is full, and counts its own records.
    await wrapper.setProps({ view: 'execution' })
    expect(shown()).toEqual(ids(rows.slice(0, 6)))
    expect(count()).toMatch(/· 8$/)
    await next()
    expect(shown()).toEqual(ids(rows.slice(6, 8)))
    await wrapper.setProps({ view: 'preparation' })
    expect(shown()).toEqual(ids(rows.slice(8)))
    expect(count()).toMatch(/· 6$/)
    expect(pager().exists()).toBe(false)
    // A view that holds the selected record shows the page it is on.
    await wrapper.setProps({ view: 'overview' })
    expect(shown()).toEqual(ids(rows.slice(6, 12)))
    expect(onShow()).toBe(rows[6].id)

    // The Account filter lists every Account in progress, not only those of the page shown.
    const account = wrapper.get<HTMLSelectElement>('select[aria-label="Evaluation 客户"]')
    expect(account.findAll('option').map((option) => option.text())).toEqual(['全部客户', 'Account A', 'Account B'])
    await account.setValue('B')
    expect(shown()).toEqual(ids(rows.slice(8)))
    expect(count()).toMatch(/· 6$/)
    await account.setValue('All')
    expect(shown()).toEqual(ids(rows.slice(6, 12)))

    // The size the list opened with stays on offer, also after a view too short for a pager, which unmounts it.
    const perPage = () => pager().get<HTMLSelectElement>('select[aria-label="每页数量"]')
    await perPage().setValue('25')
    expect(shown()).toEqual(ids(rows))
    await wrapper.setProps({ view: 'preparation' })
    expect(pager().exists()).toBe(false)
    await wrapper.setProps({ view: 'overview' })
    expect(perPage().findAll('option').map((option) => option.text())).toEqual(['6', '10', '25', '50'])
    await perPage().setValue('6')
    expect(shown()).toEqual(ids(rows.slice(6, 12)))

    // A record selected from outside is brought into view on its page.
    await wrapper.setProps({ selectedId: rows[13].id })
    expect(shown()).toEqual(ids(rows.slice(12)))
    expect(onShow()).toBe(rows[13].id)

    // Setting its DDL saves it, and the list read again has it at the top: it stays the selected record, on
    // the first page now, where the page used to stay on the last one and select what was left there.
    const first = [rows[13], ...rows.slice(0, 13)]
    await wrapper.setProps({ evaluations: first.map((item) => ({ ...item })) }); await flushPromises()
    expect(shown()).toEqual(ids(first.slice(0, 6)))
    expect(onShow()).toBe(rows[13].id)
    // The same for a record the user turned to without choosing it: a report uploaded for it moves it to the
    // top, and it is still the one on show there, not the one chosen earlier.
    await next()
    expect(onShow()).toBe(first[6].id)
    const second = [first[6], ...first.filter((item) => item !== first[6])]
    await wrapper.setProps({ evaluations: second.map((item) => ({ ...item })) }); await flushPromises()
    expect(shown()).toEqual(ids(second.slice(0, 6)))
    expect([onShow(), held()]).toEqual([first[6].id, first[6].id])
  })

  it('emits terminate with the selected evaluation when clicked', async () => {
    const testingEvaluation = evaluations.find((item) => item.id === 'EVAL-103')!
    const wrapper = mount(EvaluationWorkspace, {
      props: { view: 'overview', evaluations: [testingEvaluation], selectedId: testingEvaluation.id, canWrite: true },
    })
    const button = wrapper.get(`[data-testid="terminate-evaluation-${testingEvaluation.id}"]`)
    expect(button.text()).toBe('终止 Demo')
    await button.trigger('click')
    expect(wrapper.emitted('terminate')?.[0]).toEqual([testingEvaluation])

    await wrapper.setProps({ processing: testingEvaluation.id })
    expect(button.attributes('disabled')).toBeDefined()
    await wrapper.setProps({ processing: '', canWrite: false })
    expect(wrapper.find('[data-testid^="terminate-evaluation-"]').exists()).toBe(false)
  })

  it.each(['Requested', 'Scope Confirmed', 'Sample Received', 'Scheduled', 'Analysis', 'Internal Review', 'Customer Review'] as const)(
    'offers Terminate for a %s evaluation too', (status) => {
      const open = { ...evaluations.find((item) => item.id === 'EVAL-103')!, status }
      const wrapper = mount(EvaluationWorkspace, {
        props: { view: 'overview', evaluations: [open], selectedId: open.id, canWrite: true },
      })
      expect(wrapper.find(`[data-testid="terminate-evaluation-${open.id}"]`).exists()).toBe(true)
    },
  )

  it.each(['Accepted', 'Rejected'] as const)('does not show Terminate for an already-terminal %s evaluation', (status) => {
    const ended = { ...evaluations.find((item) => item.id === 'EVAL-103')!, status }
    const wrapper = mount(EvaluationWorkspace, {
      props: { view: 'overview', evaluations: [ended], selectedId: ended.id, canWrite: true },
    })
    expect(wrapper.find(`[data-testid="terminate-evaluation-${ended.id}"]`).exists()).toBe(false)
  })

  it('names a terminated Demo Test with its reason while historical outcomes keep their labels', async () => {
    const base = evaluations.find((item) => item.id === 'EVAL-103')!
    const terminated: EvaluationDto = { ...base, id: 'EVAL-TERMINATED', status: 'Rejected', terminationReason: '客户暂停项目' }
    const rejected: EvaluationDto = { ...base, id: 'EVAL-REJECTED', status: 'Rejected', terminationReason: '' }
    const accepted: EvaluationDto = { ...base, id: 'EVAL-ACCEPTED', status: 'Accepted' }
    const wrapper = mount(EvaluationWorkspace, {
      props: { view: 'overview', evaluations: [terminated, rejected, accepted], selectedId: terminated.id },
    })
    const stage = (id: string) => wrapper.get(`[data-evaluation="${id}"] .status-badge`).text()

    expect([stage('EVAL-TERMINATED'), stage('EVAL-REJECTED'), stage('EVAL-ACCEPTED')]).toEqual(['已终止', '已拒绝', '已接受'])
    expect(wrapper.get('[data-termination-reason]').text()).toContain('客户暂停项目')
    setLocale('en-US')
    await flushPromises()
    expect([stage('EVAL-TERMINATED'), stage('EVAL-REJECTED'), stage('EVAL-ACCEPTED')]).toEqual(['Terminated', 'Rejected', 'Accepted'])
    await wrapper.setProps({ selectedId: rejected.id })
    expect(wrapper.find('[data-termination-reason]').exists()).toBe(false)
  })

  it('presents Demo Tests as a contacts-style summary table with a separate action area', async () => {
    const activeEvaluations = evaluations
      .filter((item) => !['Accepted', 'Rejected'].includes(item.status))
      .map((item) => item.id === 'EVAL-103'
        ? {
            ...item,
            history: [{
              id: 'HIST-103',
              actor: 'zhou.ning@example.com',
              at: '2026-08-25T09:00:00+08:00',
              eventType: 'Status' as const,
              from: 'Scheduled',
              to: 'Testing',
              summary: 'Demo Test moved to Testing',
            }],
          }
        : item)
    const wrapper = mount(EvaluationWorkspace, {
      props: {
        view: 'overview',
        evaluations: activeEvaluations,
        selectedId: 'EVAL-103',
        canWrite: true,
        canReport: true,
      },
    })

    const table = wrapper.get('[data-evaluation-table]')
    expect(table.text()).toContain('Test / 项目')
    expect(table.text()).toContain('客户')
    expect(table.text()).toContain('来源 Request')
    expect(table.text()).toContain('Engineer')
    expect(table.text()).toContain('阶段')
    expect(table.text()).toContain('计划完成')
    expect(wrapper.get('[data-evaluation="EVAL-103"]').classes()).toContain('selected')
    expect(wrapper.get('[data-evaluation-actions]').text()).toContain('相关人员操作')
    expect(wrapper.find('[data-evaluation-detail-inline]').exists()).toBe(false)
    const actionPanelChildren = [...wrapper.get('[data-evaluation-actions]').element.children]
    expect(actionPanelChildren.indexOf(wrapper.get('[data-add-test-run]').element))
      .toBeLessThan(actionPanelChildren.indexOf(wrapper.get('[aria-label="评估历史记录"]').element))

    await wrapper.get('[data-open-demo-detail="EVAL-103"]').trigger('click')
    expect(wrapper.emitted('open-detail')?.[0]).toEqual([
      expect.objectContaining({ id: 'EVAL-103', demoRequestId: 'DR-107' }),
    ])
  })

  it('keeps stage-specific actions available and exposes Internal Review', async () => {
    const active = evaluations
      .filter((item) => !['Accepted', 'Rejected'].includes(item.status))
      .map((item) => item.id === 'EVAL-101'
        ? { ...item, waferPreparationStatus: 'Pending' as const, testPreparationStatus: 'Pending' as const }
        : item)
    const wrapper = mount(EvaluationWorkspace, {
      props: {
        view: 'preparation',
        evaluations: active,
        selectedId: 'EVAL-101',
        canWrite: true,
        canReport: true,
      },
    })

    expect(wrapper.find('[data-set-ddl="EVAL-101"]').exists()).toBe(true)

    await wrapper.setProps({
      view: 'internal',
      evaluations: [...active, { ...active[0], id: 'EVAL-107', status: 'Internal Review' as const }],
      selectedId: 'EVAL-107',
    })

    expect(wrapper.get('[data-evaluation-workspace="internal"]').text()).toContain('Internal Review')

    await wrapper.setProps({ view: 'execution', selectedId: 'EVAL-103' })
    expect(wrapper.find('[data-report-action="EVAL-103"]').exists()).toBe(true)
  })

  it('uses explicit parallel preparation actions instead of a status dropdown', async () => {
    const active = evaluations
      .filter((item) => !['Accepted', 'Rejected'].includes(item.status))
      .map((item) => item.id === 'EVAL-101'
        ? { ...item, waferPreparationStatus: 'Pending' as const, testPreparationStatus: 'Pending' as const }
        : item)
    const wrapper = mount(EvaluationWorkspace, {
      props: { view: 'wafer', evaluations: active, selectedId: 'EVAL-101', canWrite: true },
    })

    expect(wrapper.find('[aria-label="Evaluation 状态"]').exists()).toBe(false)
    expect(wrapper.get('[data-evaluation="EVAL-101"]').text()).toContain('Wafer 准备 · 待完成')
    expect(wrapper.find('[data-complete-preparation="wafer"]').exists()).toBe(true)
    expect(wrapper.find('[data-complete-preparation="test"]').exists()).toBe(false)

    await wrapper.setProps({ view: 'preparation' })
    expect(wrapper.get('[data-evaluation="EVAL-101"]').text()).toContain('测试准备 · 待完成')
    expect(wrapper.find('[data-complete-preparation="wafer"]').exists()).toBe(false)
    expect(wrapper.find('[data-complete-preparation="test"]').exists()).toBe(true)
    expect(wrapper.find('[data-set-ddl="EVAL-101"]').exists()).toBe(true)

    await wrapper.setProps({
      evaluations: active.map((item) => item.id === 'EVAL-101'
        ? { ...item, status: 'Scheduled' as const, waferPreparationStatus: 'Completed' as const, testPreparationStatus: 'Completed' as const }
        : item),
    })
    expect(wrapper.get('[data-advance-status="Testing"]').text()).toContain('进入 Test Execution')
  })

  it('gates Internal Review on both reports and a completed Test Run', async () => {
    const testing = { ...evaluations[2], status: 'Testing' as const, runs: [] }
    const wrapper = mount(EvaluationWorkspace, {
      props: { view: 'execution', evaluations: [testing], selectedId: testing.id, canWrite: true },
    })

    expect(wrapper.get('[data-advance-status="Internal Review"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test-report-card]').text()).toContain('Test Report')
    expect(wrapper.get('[data-test-run-review-gate]').text()).toBe('请先上传 Internal 和 External Test Report，并完成第 1 轮 Test Run。')
    expect(wrapper.get('[data-report-action]').text()).toContain('上传两份 Test Report')
    expect(wrapper.get('[data-report-action]').classes()).toContain('primary-button')
    expect(wrapper.get('[data-add-test-run]').classes()).toContain('secondary-button')
    // A retest reopens Testing with the previous round's deadline cleared, so the
    // deadline can be set again during execution, not only during preparation.
    expect(wrapper.find(`[data-set-ddl="${testing.id}"]`).exists()).toBe(true)

    const ready: EvaluationDto = {
        ...testing,
        runs: [{ id: 'CRM-RUN-00001', date: '2026-08-11', lot: 'LOT-1', round: 1, wafers: 1, status: 'Completed' as const, capture: 96, falsePositive: 1, wph: 12, summary: 'Passed' }],
        reportArtifactId: 'CRM-ART-00001',
        internalReportArtifactId: 'CRM-ART-00001',
        externalReportArtifactId: 'CRM-ART-00002',
        reportVersion: 1,
        reportStatus: 'Ready' as const,
        internalReportArtifact: {
          id: 'CRM-ART-00001', demoRequestId: testing.demoRequestId!, evaluationId: testing.id,
          type: 'Test Report', fileName: '[Internal] capture-results.xlsx',
          mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', version: 1,
          createdBy: 'Engineer Li', createdAt: '2026-08-11T10:00:00+08:00', visibility: 'Internal',
        },
        externalReportArtifact: {
          id: 'CRM-ART-00002', demoRequestId: testing.demoRequestId!, evaluationId: testing.id,
          type: 'Test Report', fileName: '[External] customer-results.pdf', mimeType: 'application/pdf', version: 1,
          createdBy: 'Engineer Li', createdAt: '2026-08-11T10:00:00+08:00', visibility: 'Customer Review',
        },
    }
    await wrapper.setProps({ evaluations: [ready] })
    expect(wrapper.get('[data-advance-status="Internal Review"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-test-run-review-gate]').exists()).toBe(false)
    expect(wrapper.get('[data-test-report-card]').text()).toContain('[Internal] capture-results.xlsx')
    expect(wrapper.get('[data-test-report-card]').text()).toContain('[External] customer-results.pdf')
    expect(wrapper.get('[data-report-action]').text()).toContain('上传新版本')
    expect(wrapper.get('[data-report-action]').classes()).toContain('secondary-button')

    // After a retest the round-1 run is still listed, so the hint must say that only a
    // run completed in the current round unlocks Internal Review.
    await wrapper.setProps({ evaluations: [{ ...ready, testRound: 2 }] })
    expect(wrapper.get('[data-advance-status="Internal Review"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test-run-review-gate]').text()).toBe('请先完成第 2 轮 Test Run，之前轮次的 Test Run 不计入。')
  })
})
