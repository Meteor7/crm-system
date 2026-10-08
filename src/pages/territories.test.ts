import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import type { ApiResponse } from '@/types/crm'
import type { TerritoryCatalogue } from '@/features/territories/types'
import { setLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'
import TerritoriesPage from './TerritoriesPage.vue'

function catalogue(): TerritoryCatalogue {
  return {
    territories: [
      { name: 'China', parent: null, isGroup: true, enabled: true, sortOrder: 0, modified: '2026-10-01T00:00:00Z' },
      { name: 'East China', parent: 'China', isGroup: false, enabled: true, sortOrder: 1, modified: '2026-10-01T00:00:00Z' },
    ],
    assignments: [{ id: 'assignment', territory: 'East China', salesOwner: 'sales', validFrom: '2026-01-01', validUntil: null, cancelled: false, note: 'Original note', modified: '2026-10-01T01:00:00Z' }],
    unmappedRegions: ['Overseas'], sales: [{ id: 'sales', name: 'Alice' }], today: '2026-10-05',
  }
}

// attach: mount into the document, for focus and computed-style checks.
async function setup(role: 'Manager' | 'Sales' = 'Manager', attach = false) {
  const api = createMockApi({ latency: 0, role })
  const bootstrap = await api.getBootstrap()
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = bootstrap.data
  const data = catalogue()
  const response = { ...bootstrap, data } satisfies ApiResponse<TerritoryCatalogue>
  const get = vi.spyOn(api, 'getTerritoryCatalogue').mockResolvedValue(response)
  const save = vi.spyOn(api, 'saveTerritoryAssignment').mockResolvedValue({ ...bootstrap, data: data.assignments[0]! })
  const saveTerritory = vi.spyOn(api, 'saveTerritory').mockResolvedValue({ ...bootstrap, data: data.territories[1]! })
  const wrapper = mount(TerritoriesPage, { props: { apiClient: api }, global: { plugins: [pinia] }, attachTo: attach ? document.body : undefined })
  await flushPromises()
  return { wrapper, get, save, saveTerritory }
}

describe('Territory administration', () => {
  afterEach(() => setLocale('zh-CN'))

  it('shows current coverage and unmapped names and sends the assignment version when editing', async () => {
    const { wrapper, save } = await setup()
    expect(wrapper.text()).toContain('Alice')
    expect(wrapper.text()).toContain('Overseas')
    const row = wrapper.findAll('tr').find(row => row.text().includes('Original note'))!
    await row.get('button').trigger('click')
    await wrapper.get('[aria-label="Effective through"]').setValue('2026-10-31')
    await wrapper.get('[data-assignment-form]').trigger('submit')
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ territory: 'East China', validUntil: '2026-10-31', salesOwner: 'sales' }), 'assignment', '2026-10-01T01:00:00Z')
    wrapper.unmount()
  })

  it('retains an assignment draft when the server rejects overlapping dates', async () => {
    const { wrapper, save } = await setup()
    save.mockRejectedValueOnce(new Error('Overlapping dates'))
    await wrapper.get('[aria-label="Sales owner"]').setValue('sales')
    await wrapper.get('[aria-label="Assignment note"]').setValue('Do not lose this')
    await wrapper.get('[data-assignment-form]').trigger('submit')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="Assignment note"]').element.value).toBe('Do not lose this')
    expect(wrapper.get('[data-assignment-form] [role="alert"]').text()).toBeTruthy()
    wrapper.unmount()
  })

  it('does not fetch Manager-only data for Sales', async () => {
    const { wrapper, get } = await setup('Sales')
    expect(get).not.toHaveBeenCalled()
    expect(wrapper.find('[data-territory-form]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('says that the current user could not be read, with a retry, in place of refusing a Manager', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const bootstrap = await api.getBootstrap()
    const getBootstrap = vi.spyOn(api, 'getBootstrap').mockRejectedValueOnce(new Error('bootstrap unavailable'))
    const get = vi.spyOn(api, 'getTerritoryCatalogue').mockResolvedValue({ ...bootstrap, data: catalogue() })
    const wrapper = mount(TerritoriesPage, { props: { apiClient: api }, global: { plugins: [createPinia()] } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Available to Managers only')
    expect(wrapper.text()).not.toContain('仅经理可维护')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(get).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="territories-retry"]').trigger('click')
    await flushPromises()
    expect(getBootstrap).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="territories-retry"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Alice')
    wrapper.unmount()
  })

  it('shows a refused save in the alert colour inside its form, not in the muted text of the card', async () => {
    const { wrapper, save, saveTerritory } = await setup('Manager', true)
    saveTerritory.mockRejectedValueOnce(new Error('Name already used'))
    save.mockRejectedValueOnce(new Error('Overlapping dates'))
    await wrapper.get('[aria-label="Territory name"]').setValue('West China')
    await wrapper.get('[data-territory-form]').trigger('submit')
    await flushPromises()
    const territoryAlert = wrapper.get('[data-territory-form] [role="alert"]').element
    expect(getComputedStyle(territoryAlert).color).not.toBe(getComputedStyle(wrapper.get('[data-territory-form] .note').element).color)
    const alertColour = getComputedStyle(territoryAlert).color

    await wrapper.get('[aria-label="Sales owner"]').setValue('sales')
    await wrapper.get('[data-assignment-form]').trigger('submit')
    await flushPromises()
    const assignmentAlert = wrapper.get('[data-assignment-form] [role="alert"]').element
    expect(getComputedStyle(assignmentAlert).color).toBe(alertColour)
    expect(getComputedStyle(assignmentAlert).color).not.toBe(getComputedStyle(wrapper.get('[data-assignment-form] .note').element).color)
    wrapper.unmount()
  })

  it('leaves focus on the language control when the language changes under a shown refusal', async () => {
    const { wrapper, save } = await setup('Manager', true)
    // A refusal without text shows the default message, which exists in both languages.
    save.mockRejectedValueOnce(new Error(''))
    await wrapper.get('[aria-label="Sales owner"]').setValue('sales')
    await wrapper.get('[data-assignment-form]').trigger('submit')
    await flushPromises()
    const shown = wrapper.get('[data-assignment-form] [role="alert"]')
    expect(document.activeElement).toBe(shown.element)
    const chinese = shown.text()

    const languageControl = document.createElement('button')
    document.body.append(languageControl)
    languageControl.focus()
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('[data-assignment-form] [role="alert"]').text()).not.toBe(chinese)
    expect(document.activeElement).toBe(languageControl)
    languageControl.remove()
    wrapper.unmount()
  })
})
