import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { demoRequests } from '@/api/mock-data'
import type { DemoRequestDto } from '@/types/crm'
import DemoRequestWorkspace from './DemoRequestWorkspace.vue'

describe('Demo Request workspace', () => {
  it('uses a Contacts-style summary table with a separate operation panel', async () => {
    const requests = demoRequests.filter((item) => !['Converted', 'Cancelled'].includes(item.status))
    const wrapper = mount(DemoRequestWorkspace, {
      props: {
        view: 'overview',
        requests,
        selectedId: 'DR-101',
        canCreate: true,
        canEngineer: true,
        canManager: true,
      },
    })

    expect(wrapper.get('[data-demo-request-table]').text()).toContain('Request / 项目')
    expect(wrapper.get('[data-demo-request-table]').text()).toContain('客户')
    expect(wrapper.get('[data-demo-request-table]').text()).toContain('目标日期')
    expect(wrapper.get('[data-demo-request-actions]').text()).toContain('相关人员操作')
    expect(wrapper.get('[data-demo-request-actions]').text()).toContain('工程评估')
    expect(wrapper.find('[data-demo-request-inline-detail]').exists()).toBe(false)
    expect(wrapper.find('.workspace-main').exists()).toBe(true)
    expect(wrapper.find('.toolbar').exists()).toBe(true)
    expect(wrapper.find('.toolbar-search').exists()).toBe(false)
    expect(wrapper.get('[data-demo-request-actions]').classes()).toContain('action-panel')

    await wrapper.get('[data-open-demo-detail="DR-101"]').trigger('click')
    expect(wrapper.emitted('open-detail')?.[0]?.[0]).toMatchObject({ id: 'DR-101' })
  })

  it('pages each view on its own, counts the whole view and keeps the selected record on show', async () => {
    // Everything in progress: 13 with Sales, 6 with engineering, 4 with the Manager.
    const base = demoRequests.find((item) => !['Converted', 'Cancelled'].includes(item.status))!
    const make = (index: number, status: DemoRequestDto['status'], salesOwner = base.salesOwner): DemoRequestDto =>
      ({ ...base, id: `DR-P${String(index).padStart(2, '0')}`, status, salesOwner })
    const requests = [
      ...Array.from({ length: 13 }, (_, index) => make(index, 'Draft', index < 3 ? 'other-sales' : base.salesOwner)),
      ...Array.from({ length: 6 }, (_, index) => make(20 + index, 'Engineer Review')),
      ...Array.from({ length: 4 }, (_, index) => make(30 + index, 'Manager Approval')),
    ]
    // The page above holds the selected record and takes the one the workspace hands up, as DemoRequestsPage does.
    const wrapper = mount(DemoRequestWorkspace, {
      props: { view: 'overview', requests, selectedId: requests[0].id, onSelect: (id: string) => { void wrapper.setProps({ selectedId: id }) } },
    })
    const shown = () => wrapper.findAll('[data-demo-request]').map((row) => row.attributes('data-demo-request'))
    const onShow = () => wrapper.get('tr.selected').attributes('data-demo-request')
    const held = () => wrapper.props('selectedId')
    const count = () => wrapper.get('.row-count').text()
    const pager = () => wrapper.find('.pagination-controls')
    const next = async () => { await pager().get('[data-page-next]').trigger('click'); await flushPromises() }
    const ids = (rows: DemoRequestDto[]) => rows.map((item) => item.id)
    const reread = async (rows: DemoRequestDto[]) => { await wrapper.setProps({ requests: rows.map((item) => ({ ...item })) }); await flushPromises() }

    expect(shown()).toEqual(ids(requests.slice(0, 10)))
    expect(count()).toBe('Demo Request · 23')
    expect(pager().get('small').text()).toContain('23')
    // Turning the page puts its first record on show, and that record is handed up as the selected one.
    await next()
    expect(shown()).toEqual(ids(requests.slice(10, 20)))
    expect([onShow(), held()]).toEqual([requests[10].id, requests[10].id])
    await next()
    expect(shown()).toEqual(ids(requests.slice(20)))
    expect([onShow(), held()]).toEqual([requests[20].id, requests[20].id])

    // A view that does not hold the selected record starts on its first page, is full, and counts its own records.
    await wrapper.setProps({ view: 'sales' })
    expect(shown()).toEqual(ids(requests.slice(0, 10)))
    expect(count()).toBe('Demo Request · 13')
    expect(pager().get('small').text()).toContain('13')
    await next()
    expect(shown()).toEqual(ids(requests.slice(10, 13)))
    expect(held()).toBe(requests[10].id)
    await wrapper.setProps({ view: 'engineer' })
    expect(shown()).toHaveLength(6)
    expect(count()).toBe('Demo Request · 6')
    expect(pager().exists()).toBe(false)
    await wrapper.setProps({ view: 'manager' })
    expect(shown()).toHaveLength(4)
    // A view that holds the selected record shows the page it is on.
    await wrapper.setProps({ view: 'sales' })
    expect(shown()).toEqual(ids(requests.slice(10, 13)))
    expect(onShow()).toBe(requests[10].id)

    // The Sales filter lists every owner in progress and narrows the view by the same rule.
    const sales = wrapper.get<HTMLSelectElement>('select[aria-label="工作区 Sales"]')
    expect(sales.findAll('option').map((option) => option.text())).toEqual(['全部 Sales', 'other-sales', base.salesOwner])
    await sales.setValue(base.salesOwner)
    expect(shown()).toEqual(ids(requests.slice(3, 13)))
    expect(count()).toBe('Demo Request · 10')
    expect(onShow()).toBe(requests[10].id)
    await sales.setValue('other-sales')
    expect(shown()).toEqual(ids(requests.slice(0, 3)))
    await sales.setValue('All')
    expect(shown()).toEqual(ids(requests.slice(10, 13)))

    // A larger page leaves the pager in place, so the smaller one can be taken back.
    await pager().get('select').setValue('25'); await flushPromises()
    expect(shown()).toHaveLength(13)
    await pager().get('select').setValue('10'); await flushPromises()
    expect(shown()).toEqual(ids(requests.slice(10, 13)))

    // A record selected from outside is brought into view on its page.
    await wrapper.setProps({ view: 'overview', selectedId: requests[22].id })
    expect(shown()).toEqual(ids(requests.slice(20)))
    expect(onShow()).toBe(requests[22].id)
    // The list is read again after a save, which moves the saved record to the top: it stays the selected one
    // and the page follows it there.
    const first = [requests[22], ...requests.filter((item) => item !== requests[22])]
    await reread(first)
    expect(shown()).toEqual(ids(first.slice(0, 10)))
    expect(onShow()).toBe(requests[22].id)
    // The same for a record the user turned to without choosing it: where the page used to follow it and show
    // the one chosen earlier, which stands on that page too.
    await next()
    expect(onShow()).toBe(first[10].id)
    const second = [first[10], ...first.filter((item) => item !== first[10])]
    await reread(second)
    expect(shown()).toEqual(ids(second.slice(0, 10)))
    expect([onShow(), held()]).toEqual([first[10].id, first[10].id])

    // When the list gets shorter and the selected record is gone, the page shown is one that still exists.
    await next(); await next()
    expect(held()).toBe(second[20].id)
    await reread(second.slice(0, 12))
    expect(shown()).toEqual(ids(second.slice(10, 12)))
    expect(onShow()).toBe(second[10].id)
    // Its first record is on show without having been chosen. Saved, it is followed to the top and is the
    // selected one from then on, in another view as well.
    const third = [second[10], ...second.slice(0, 10), second[11]]
    await reread(third)
    expect(shown()).toEqual(ids(third.slice(0, 10)))
    expect([onShow(), held()]).toEqual([second[10].id, second[10].id])
    await wrapper.setProps({ view: 'sales' })
    expect(onShow()).toBe(second[10].id)
  })

  it('keeps a record selected from outside that the view does not show, until the user works on another', async () => {
    const base = demoRequests.find((item) => !['Converted', 'Cancelled'].includes(item.status))!
    const make = (id: string, status: DemoRequestDto['status']): DemoRequestDto => ({ ...base, id, status })
    const waiting = ['DR-M0', 'DR-M1', 'DR-M2'].map((id) => make(id, 'Manager Approval'))
    const drafts = Array.from({ length: 12 }, (_, index) => make(`DR-D${String(index).padStart(2, '0')}`, 'Draft'))
    const wrapper = mount(DemoRequestWorkspace, {
      props: { view: 'manager', requests: [...waiting, ...drafts], selectedId: 'DR-M1', onSelect: (id: string) => { void wrapper.setProps({ selectedId: id }) } },
    })
    const onShow = () => wrapper.get('tr.selected').attributes('data-demo-request')
    const held = () => wrapper.props('selectedId')
    const reread = async (rows: DemoRequestDto[]) => { await wrapper.setProps({ requests: rows.map((item) => ({ ...item })) }); await flushPromises() }
    expect(onShow()).toBe('DR-M1')

    // The page creates a request from this view and selects it before it reads the list again. It is a draft,
    // which the approval view does not show: the first record of the view is on show, and the new request is
    // still the selected one after the read, for the view that shows it.
    const created = make('DR-NEW', 'Draft')
    await wrapper.setProps({ selectedId: created.id })
    expect(onShow()).toBe('DR-M0')
    await reread([created, ...waiting, ...drafts])
    expect([onShow(), held()]).toEqual(['DR-M0', 'DR-NEW'])
    await wrapper.setProps({ view: 'overview' })
    expect(onShow()).toBe('DR-NEW')

    // Back in the approval view the user works on the record on show there. Read again after that save, the
    // list has it at the top, and it is the selected record from then on.
    await wrapper.setProps({ view: 'manager' })
    expect([onShow(), held()]).toEqual(['DR-M0', 'DR-NEW'])
    await reread([waiting[0], created, waiting[1], waiting[2], ...drafts])
    expect([onShow(), held()]).toEqual(['DR-M0', 'DR-M0'])
  })
})
