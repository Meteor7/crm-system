import { mount } from '@vue/test-utils'
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
    expect(masterData).toContain('Engineer Owner')
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