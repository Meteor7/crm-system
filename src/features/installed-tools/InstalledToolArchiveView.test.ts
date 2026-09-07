import { setLocale } from '@/i18n'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import type { InstalledToolDetailDto } from '@/types/workspaces'
import InstalledToolArchiveView from './InstalledToolArchiveView.vue'

async function fixture() {
  const api = createMockApi({ latency: 0 })
  const items = (await api.listInstalledTools({ pageSize: 2 })).data.items
  const detail = (await api.getInstalledTool(items[0].id)).data
  return { items, detail }
}

describe('InstalledToolArchiveView', () => {
  it('renders only the selected API detail and emits audited operations', async () => {
    const { items, detail } = await fixture()
    const apiDetail: InstalledToolDetailDto = {
      ...detail,
      canOperate: true,
      lifecycleCompleted: false,
      versionHistory: [{
        id: 'version-api-1',
        at: '2026-08-12T09:00:00+08:00',
        actor: 'engineer@example.com',
        changeDate: '2026-08-12',
        changeType: 'Software',
        fromValue: '6.4.1',
        toValue: '9.9.9-real-api',
        reason: '真实接口返回',
        comment: '',
      }],
    }
    const wrapper = mount(InstalledToolArchiveView, {
      props: { items, selectedId: items[0].id, detail: apiDetail },
    })

    expect(wrapper.get('[data-installed-tool-archive]').text()).toContain(items[0].serial)
    expect(wrapper.findAll('.workspace-select-card')).toHaveLength(2)
    expect(wrapper.text()).not.toContain('FAT-AX9-260018-Report.pdf')
    const masterData = wrapper.get('[data-testid="installed-tool-master-data"]').text()
    expect(masterData).toContain(apiDetail.salesOrder)
    expect(masterData).toContain(apiDetail.contract)
    expect(masterData).toContain('工程师负责人')
    expect(masterData).not.toContain('@crm.example.invalid')
    expect(masterData).toContain(apiDetail.sourceBookingId)
    expect(masterData).toContain(apiDetail.warrantyStart)

    await wrapper.findAll('.detail-tabs button')[1].trigger('click')
    expect(wrapper.text()).toContain('9.9.9-real-api')
    expect(wrapper.text()).toContain('真实接口返回')

    await wrapper.get('[data-testid="advance-installed-tool"]').trigger('click')
    await wrapper.get('[data-testid="add-installed-tool-version"]').trigger('click')
    await wrapper.get('[data-testid="add-installed-tool-service"]').trigger('click')
    await wrapper.get('[data-testid="edit-installed-tool"]').trigger('click')
    expect(wrapper.emitted('advance')).toHaveLength(1)
    expect(wrapper.emitted('version')).toHaveLength(1)
    expect(wrapper.emitted('service')).toHaveLength(1)
    expect(wrapper.emitted('edit')).toHaveLength(1)

    await wrapper.get(`[data-installed-tool-archive-id="${items[1].id}"]`).trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(items[1])
  })

  it('preserves the Demo archive visual hierarchy and lifecycle state semantics', async () => {
    const { items, detail } = await fixture()
    const wrapper = mount(InstalledToolArchiveView, {
      props: { items, selectedId: items[0].id, detail },
    })

    const hero = wrapper.get('[data-testid="installed-tool-hero"]')
    expect(hero.attributes('data-stage')).toBe(detail.lifecycleStage)
    expect(hero.find('.workspace-badge').classes()).toContain(detail.status === 'Production' ? 'positive' : 'warning')
    expect(wrapper.findAll('[data-master-tone]')).toHaveLength(17)
    expect(wrapper.findAll('.detail-tabs button svg')).toHaveLength(3)

    const currentStep = wrapper.get('.lifecycle-step.is-current')
    expect(currentStep.attributes('aria-current')).toBe('step')
    expect(wrapper.get('.stage-record-head .workspace-badge.warning').text()).toBe('进行中')
    expect(wrapper.get('.stage-record-head .workspace-badge.positive').text()).toBe('已完成')

    await wrapper.findAll('.detail-tabs button')[2].trigger('click')
    expect(wrapper.get('.health-score').attributes('aria-label')).toContain('设备档案完整度')
  })

  it('hides all mutation actions when the server says the user cannot operate', async () => {
    const { items, detail } = await fixture()
    const wrapper = mount(InstalledToolArchiveView, {
      props: { items, selectedId: items[0].id, detail: { ...detail, canOperate: false } },
    })

    expect(wrapper.find('[data-testid="advance-installed-tool"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="add-installed-tool-version"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="add-installed-tool-service"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-installed-tool"]').exists()).toBe(false)
  })

  it('shows loading/error states and does not render stale detail', async () => {
    const { items } = await fixture()
    const loading = mount(InstalledToolArchiveView, {
      props: { items, selectedId: items[0].id, detail: null, detailLoading: true },
    })
    expect(loading.text()).toContain('正在读取设备档案')

    const failed = mount(InstalledToolArchiveView, {
      props: { items, selectedId: items[0].id, detail: null, detailError: '无权查看该设备' },
    })
    expect(failed.text()).toContain('无权查看该设备')
    expect(failed.find('.tool-header').exists()).toBe(false)
  })
})

it.each([['Production', '生产中'], ['Upgrade Due', '待升级'], ['Installation', '安装中']])('translates %s without changing the selected equipment or raw status', async (status, chinese) => {
  const { items } = await fixture()
  items[0].status = status
  const wrapper = mount(InstalledToolArchiveView, { props: { items, selectedId: items[0].id } })
  const row = wrapper.get(`[data-installed-tool-archive-id="${items[0].id}"]`)
  expect(row.text()).toContain(chinese)
  setLocale('en-US')
  await flushPromises()
  expect(row.text()).toContain(status)
  await row.trigger('click')
  expect(wrapper.emitted('select')?.[0]).toEqual([items[0]])
  expect(items[0].status).toBe(status)
  wrapper.unmount()
})


it('localizes stored system defaults across equipment lifecycle, version and service views', async () => {
  const { detail } = await fixture()
  Object.assign(detail, { location: '待确认', software: '待确认', firmware: '待确认', operatingSystem: '待确认', configuration: '待确认', salesOrder: '待确认', contract: '待确认', serviceContract: '待确认', pmCycle: '待确认', warrantyStart: '待确认', warrantyEnd: '待确认', lastService: '尚未开始' })
  detail.milestones = detail.milestones.map(stage => ({ ...stage, date: '待确认' }))
  detail.versionHistory = [{ id: 'V-1', at: '2026-09-07', actor: 'Engineer', changeDate: '2026-09-07', changeType: 'Software', fromValue: '待确认', toValue: '1.0', reason: '用户写下的中文原因', comment: '' }]
  detail.serviceHistory = [{ id: 'S-1', at: '2026-09-07', actor: 'Engineer', serviceDate: '2026-09-07', serviceType: 'Remote Support', result: '用户的服务结果', openIssues: '无', nextAction: '', actionOwner: '', due: '', comment: '', warrantyStart: '', warrantyEnd: '', serviceContract: '', pmCycle: '' }]
  const original = structuredClone(detail)
  const wrapper = mount(InstalledToolArchiveView, { props: { items: [detail], selectedId: detail.id, detail } })
  expect(wrapper.text()).toContain('待确认')
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.text()).toContain('To be confirmed')
  expect(wrapper.text()).not.toContain('待确认')
  await wrapper.findAll('.detail-tabs button')[1].trigger('click')
  expect(wrapper.text()).not.toContain('待确认')
  expect(wrapper.text()).toContain('用户写下的中文原因')
  await wrapper.findAll('.detail-tabs button')[2].trigger('click')
  expect(wrapper.text()).not.toContain('待确认')
  expect(wrapper.text()).not.toContain('尚未开始')
  expect(wrapper.text()).toContain('None')
  expect(wrapper.text()).toContain('用户的服务结果')
  expect(detail).toEqual(original)
  wrapper.unmount()
})
