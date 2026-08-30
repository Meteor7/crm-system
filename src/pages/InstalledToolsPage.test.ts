import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api/contracts'
import { createMockApi } from '@/api/mock-adapter'
import type { CrmApi } from '@/api'
import { createAppRouter } from '@/app/router'
import InstalledToolsPage from './InstalledToolsPage.vue'

async function mountPage(path = '/installed-tools', apiClient: CrmApi = createMockApi({ latency: 0 })) {
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(InstalledToolsPage, {
    props: { apiClient },
    global: { plugins: [createPinia(), router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('InstalledToolsPage three-surface workspace', () => {
  it('defaults to the lifecycle board and switches three views exclusively', async () => {
    const { wrapper, router } = await mountPage()

    expect(wrapper.findAll('[data-installed-tool-surface]').map((button) => button.text()))
      .toEqual(['项目周期看板', '生命周期看板', '设备档案'])
    expect(wrapper.find('[data-installed-tool-pipeline]').exists()).toBe(true)
    expect(wrapper.find('[data-installed-tool-project-board]').exists()).toBe(false)
    expect(wrapper.find('[data-installed-tool-archive]').exists()).toBe(false)
    expect(router.currentRoute.value.query.surface).toBe('lifecycle')

    await wrapper.get('[data-installed-tool-surface="project"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.surface).toBe('project')
    expect(wrapper.find('[data-installed-tool-project-board]').exists()).toBe(true)
    expect(wrapper.find('[data-installed-tool-pipeline]').exists()).toBe(false)
    expect(wrapper.find('[data-installed-tool-archive]').exists()).toBe(false)

    await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.surface).toBe('detail')
    expect(wrapper.find('[data-installed-tool-archive]').exists()).toBe(true)
    expect(wrapper.find('[data-installed-tool-project-board]').exists()).toBe(false)
    expect(wrapper.find('[data-installed-tool-pipeline]').exists()).toBe(false)
  })

  it('opens the matching archive from a lifecycle card', async () => {
    const { wrapper, router } = await mountPage()
    const card = wrapper.get('[data-installed-tool-id]')
    const id = card.attributes('data-installed-tool-id')

    await card.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toMatchObject({ surface: 'detail', tool: id })
    expect(wrapper.get('[data-installed-tool-archive]').text()).toContain(id)
  })

  it('opens the matching archive from a project-cycle row', async () => {
    const { wrapper, router } = await mountPage('/installed-tools?surface=project')
    const row = wrapper.get('[data-installed-tool-project-row]')
    const id = row.attributes('data-installed-tool-project-id')

    await row.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toMatchObject({ surface: 'detail', tool: id })
    expect(wrapper.get('[data-installed-tool-archive]').text()).toContain(id)
  })

  it('restores the selected archive from the route and updates it from the ledger', async () => {
    const { wrapper, router } = await mountPage('/installed-tools?surface=detail&tool=TOOL-003')

    expect(wrapper.get('[data-installed-tool-archive]').text()).toContain('TOOL-003')
    await wrapper.get('[data-installed-tool-archive-id="TOOL-002"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toMatchObject({ surface: 'detail', tool: 'TOOL-002' })
    expect(wrapper.get('[data-installed-tool-archive]').text()).toContain('TOOL-002')
  })

  it('loads an exact deep-linked tool even when it is outside the current list page', async () => {
    const api = createMockApi({ latency: 0 })
    const target = (await api.getInstalledTool('TOOL-003')).data
    const firstPage = (await api.listInstalledTools({ page: 1, pageSize: 1 })).data.items
    vi.spyOn(api, 'listInstalledTools').mockResolvedValue({
      data: { items: firstPage },
      meta: { requestId: 'req-installed-page-1', total: 201, page: 1, pageSize: 50 },
      warnings: [],
    })
    const getInstalledTool = vi.spyOn(api, 'getInstalledTool').mockResolvedValue({
      data: target,
      meta: { requestId: 'req-installed-exact' },
      warnings: [],
    })

    const { wrapper, router } = await mountPage('/installed-tools?surface=detail&tool=TOOL-003', api)

    expect(getInstalledTool).toHaveBeenCalledWith('TOOL-003')
    expect(router.currentRoute.value.query.tool).toBe('TOOL-003')
    expect(wrapper.get('[data-testid="installed-tool-hero"]').text()).toContain('TOOL-003')
    expect(wrapper.get('[data-installed-tool-archive-id="TOOL-003"]').text()).toContain('TOOL-003')
  })

  it('normalizes invalid surface and tool parameters without stale detail', async () => {
    const { wrapper, router } = await mountPage('/installed-tools?surface=unknown&tool=missing')

    expect(wrapper.find('[data-installed-tool-pipeline]').exists()).toBe(true)
    expect(wrapper.find('[data-installed-tool-archive]').exists()).toBe(false)
    expect(router.currentRoute.value.query.surface).toBe('lifecycle')
    expect(router.currentRoute.value.query.tool).not.toBe('missing')
  })
  it('persists shared filters in the route when switching surfaces', async () => {
    const { wrapper, router } = await mountPage()
    const accountFilter = wrapper.get('select[aria-label="客户筛选"]')
    const accountId = accountFilter.findAll('option')[1].attributes('value')!

    await accountFilter.setValue(accountId)
    await vi.waitFor(() => expect(router.currentRoute.value.query.accountId).toBe(accountId))

    await wrapper.get('[data-installed-tool-surface="project"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.accountId).toBe(accountId)
    expect(wrapper.findAll('[data-installed-tool-project-row]').length).toBeGreaterThan(0)
  })

  it('submits lifecycle transitions with the current server version and reloads the detail', async () => {
    const api = createMockApi({ latency: 0 })
    const transition = vi.spyOn(api, 'transitionInstalledTool')
    const { wrapper } = await mountPage('/installed-tools?surface=detail&tool=TOOL-003', api)

    await wrapper.get('[data-testid="advance-installed-tool"]').trigger('click')
    const modal = wrapper.get('[role="dialog"]')
    await modal.get('input[placeholder="签字人或确认方式"]').setValue('客户已确认')
    const textareas = modal.findAll('textarea')
    await textareas[0].setValue('安装验收通过')
    await textareas[1].setValue('无')
    await textareas[2].setValue('现场安装完成')
    await modal.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(transition).toHaveBeenCalledTimes(1)
    expect(transition.mock.calls[0][0]).toBe('TOOL-003')
    expect(transition.mock.calls[0][1]).toMatchObject({
      result: '安装验收通过',
      customerSignoff: '客户已确认',
      evidence: [],
    })
    expect(transition.mock.calls[0][2]).toEqual(expect.any(String))
    expect(wrapper.get('[data-installed-tool-archive]').text()).toContain('SAT')
  })

  it('shows the request id when installed-tool detail access is denied', async () => {
    const api = createMockApi({ latency: 0 })
    vi.spyOn(api, 'getInstalledTool').mockRejectedValue(
      new CrmApiError('PERMISSION_DENIED', 'The current user is not permitted to perform this operation.', 'req_installed_tool_denied', false),
    )
    const { wrapper } = await mountPage('/installed-tools?surface=detail&tool=TOOL-001', api)

    expect(wrapper.get('[data-installed-tool-archive]').text()).toContain('req_installed_tool_denied')
    expect(wrapper.find('[data-testid="edit-installed-tool"]').exists()).toBe(false)
  })
})
