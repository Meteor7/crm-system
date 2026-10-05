import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api/contracts'
import { createMockApi } from '@/api/mock-adapter'
import type { CrmApi } from '@/api'
import { setLocale } from '@/i18n'
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
    expect(wrapper.get('.demo-toast').text()).toContain('已推进到下一生命周期节点')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('.demo-toast').text()).toContain('advanced to the next lifecycle stage')
    expect(transition).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('lets an Engineer edit a Tool they are responsible for without reading its Account', async () => {
    const api = createMockApi({ role: 'Engineer', latency: 0 })
    const user = (await api.getBootstrap()).data.user.id
    const tool = (await api.listInstalledTools({ page: 1, pageSize: 50 })).data.items.find((item) => item.engineerOwner === user)!
    const account360 = vi.spyOn(api, 'getAccount360')
    // The Sites of the Account come with the Tool; a second one is added between the first read and the editor.
    // The reads made for the editor answer when the test lets them.
    const original = api.getInstalledTool.bind(api)
    let sites = [{ id: tool.siteId, name: 'Fab 1', city: '上海' }]
    const answers: Array<(latest: typeof sites) => void> = []
    vi.spyOn(api, 'getInstalledTool').mockImplementation(async (id) => {
      const result = await original(id)
      if (!wrapper) return { ...result, data: { ...result.data, sites } }
      return new Promise((resolve) => {
        answers.push((latest) => resolve({ ...result, data: { ...result.data, sites: latest, modified: 'fresh-version' } }))
      })
    })
    let wrapper: Awaited<ReturnType<typeof mountPage>>['wrapper'] | undefined
    wrapper = (await mountPage(`/installed-tools?surface=detail&tool=${tool.id}`, api)).wrapper
    sites = [...sites, { id: 'SITE-NEW', name: 'Fab 2', city: '苏州' }]

    // The editor waits for the read, and its button with it. Another dialog opened meanwhile keeps its place
    // when the answer arrives; an answer that arrives once that dialog is closed again opens nothing either.
    // A later click reads again and opens the editor on what it gets.
    const edit = () => wrapper!.get('[data-testid="edit-installed-tool"]')
    const serviceModal = () => wrapper!.findComponent({ name: 'InstalledToolServiceModal' })
    const siteSelect = () => wrapper!.find('select[aria-label="客户厂区"]')
    const stale = [{ id: 'SITE-STALE', name: 'Stale', city: '-' }]
    await edit().trigger('click')
    await flushPromises()
    expect(edit().attributes('disabled')).toBeDefined()
    expect(siteSelect().exists()).toBe(false)
    await wrapper.get('[data-testid="add-installed-tool-service"]').trigger('click')
    expect(serviceModal().exists()).toBe(true)
    expect(answers).toHaveLength(1)
    answers[0]!(stale)
    await flushPromises()
    expect(serviceModal().exists()).toBe(true)
    expect(siteSelect().exists()).toBe(false)
    await serviceModal().vm.$emit('close')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(edit().attributes('disabled')).toBeUndefined()

    await edit().trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="add-installed-tool-service"]').trigger('click')
    await serviceModal().vm.$emit('close')
    await flushPromises()
    expect(answers).toHaveLength(2)
    answers[1]!(stale)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(siteSelect().exists()).toBe(false)
    expect(edit().attributes('disabled')).toBeUndefined()

    await edit().trigger('click')
    await flushPromises()
    expect(answers).toHaveLength(3)
    answers[2]!(sites)
    await flushPromises()

    // The editor offers the Sites of this moment, read with the Tool; the Account 360, which this Engineer may
    // not read, is not asked for. The editor saves against the version read with them.
    expect(account360).not.toHaveBeenCalled()
    const select = wrapper.get<HTMLSelectElement>('select[aria-label="客户厂区"]')
    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual([tool.siteId, 'SITE-NEW'])
    expect(select.element.value).toBe(tool.siteId)
    expect(wrapper.find('.form-error').exists()).toBe(false)
    const update = vi.spyOn(api, 'updateInstalledTool').mockImplementation((id) => original(id))
    await wrapper.findComponent({ name: 'InstalledToolEditorModal' }).vm.$emit('submit', { siteId: tool.siteId })
    await flushPromises()
    expect(update).toHaveBeenCalledTimes(1)
    expect(update.mock.calls[0]![2]).toBe('fresh-version')
  })

  it('drops the answer to the editor read when another Tool is shown meanwhile', async () => {
    const api = createMockApi({ latency: 0 })
    const [first, second] = (await api.listInstalledTools({ page: 1, pageSize: 50 })).data.items
    // Every Tool comes with its own Site. The read for the editor of the first Tool answers when the test lets
    // it; every other read answers at once.
    const original = api.getInstalledTool.bind(api)
    let answer: (() => void) | undefined
    vi.spyOn(api, 'getInstalledTool').mockImplementation(async (id) => {
      const read = await original(id)
      const result = { ...read, data: { ...read.data, sites: [{ id: read.data.siteId, name: `Fab of ${id}`, city: '-' }] } }
      if (!wrapper || answer || id !== first.id) return result
      return new Promise((resolve) => { answer = () => resolve(result) })
    })
    let wrapper: Awaited<ReturnType<typeof mountPage>>['wrapper'] | undefined
    const mounted = await mountPage(`/installed-tools?surface=detail&tool=${first.id}`, api)
    wrapper = mounted.wrapper
    const edit = () => wrapper!.get('[data-testid="edit-installed-tool"]')
    const archive = () => wrapper!.get('[data-installed-tool-archive]').text()

    await edit().trigger('click')
    await flushPromises()
    expect(answer).toBeDefined()
    expect(edit().attributes('disabled')).toBeDefined()
    await mounted.router.push(`/installed-tools?surface=detail&tool=${second.id}`)
    await flushPromises()
    expect(archive()).toContain(second.id)
    // The second Tool's button does not wait for the first Tool's read.
    expect(edit().attributes('disabled')).toBeUndefined()

    // The first Tool's answer arrives: the second Tool stays, no editor opens.
    answer!()
    await flushPromises()
    expect(wrapper.find('select[aria-label="客户厂区"]').exists()).toBe(false)
    expect(archive()).toContain(second.id)

    await edit().trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="客户厂区"]').element.value).toBe(second.siteId)
  })

  it('lets no editor open while a saved Tool is being read again', async () => {
    const api = createMockApi({ latency: 0 })
    const tool = (await api.listInstalledTools({ page: 1, pageSize: 50 })).data.items[0]!
    const detail = api.getInstalledTool.bind(api)
    vi.spyOn(api, 'updateInstalledTool').mockImplementation((id) => detail(id))
    // The list read that follows the save answers when the test lets it.
    const list = api.listInstalledTools.bind(api)
    let holdList = false
    let answerList: (() => void) | undefined
    vi.spyOn(api, 'listInstalledTools').mockImplementation(async (query) => {
      const result = await list(query)
      if (!holdList) return result
      return new Promise((resolve) => { answerList = () => resolve(result) })
    })
    const reads = vi.spyOn(api, 'getInstalledTool')
    const { wrapper } = await mountPage(`/installed-tools?surface=detail&tool=${tool.id}`, api)
    const edit = () => wrapper.get('[data-testid="edit-installed-tool"]')

    await edit().trigger('click')
    await flushPromises()
    holdList = true
    await wrapper.findComponent({ name: 'InstalledToolEditorModal' }).vm.$emit('submit', { siteId: tool.siteId })
    await flushPromises()
    // The save is done and the Tool is being read again: the editor is closed, its button waits, and an edit
    // asked for anyway (the view's event, which a disabled button does not send) reads nothing, so that nothing
    // typed into an editor is thrown away by the reload.
    expect(answerList).toBeDefined()
    expect(wrapper.find('select[aria-label="客户厂区"]').exists()).toBe(false)
    expect(edit().attributes('disabled')).toBeDefined()
    const before = reads.mock.calls.length
    await wrapper.findComponent({ name: 'InstalledToolArchiveView' }).vm.$emit('edit')
    await flushPromises()
    expect(reads.mock.calls.length).toBe(before)
    expect(wrapper.find('select[aria-label="客户厂区"]').exists()).toBe(false)

    answerList!()
    await flushPromises()
    expect(wrapper.find('select[aria-label="客户厂区"]').exists()).toBe(false)
    expect(edit().attributes('disabled')).toBeUndefined()
  })

  it('tells the Engineer when the Tool cannot be read again for the editor, and opens nothing', async () => {
    const api = createMockApi({ role: 'Engineer', latency: 0 })
    const user = (await api.getBootstrap()).data.user.id
    const tool = (await api.listInstalledTools({ page: 1, pageSize: 50 })).data.items.find((item) => item.engineerOwner === user)!
    const { wrapper } = await mountPage(`/installed-tools?surface=detail&tool=${tool.id}`, api)
    vi.spyOn(api, 'getInstalledTool').mockRejectedValue(
      new CrmApiError('INSTALLED_TOOL_SCOPE_DENIED', 'The Installed Tool is outside the current user scope.', 'req_editor_read', false),
    )

    await wrapper.get('[data-testid="edit-installed-tool"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('select[aria-label="客户厂区"]').exists()).toBe(false)
    expect(wrapper.get('[data-editor-error]').text()).not.toBe('')
    expect(wrapper.get('[data-testid="edit-installed-tool"]').attributes('disabled')).toBeUndefined()
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
