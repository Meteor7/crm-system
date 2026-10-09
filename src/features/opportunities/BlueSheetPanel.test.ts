import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api/contracts'
import { useAppStore } from '@/stores/app'
import { setLocale } from '@/i18n'
import type { BlueSheetAssessment, StrategyOpportunityDto } from '@/types/workspaces'
import BlueSheetPanel from './BlueSheetPanel.vue'
import BlueSheetCompetitionEvidence from './BlueSheetCompetitionEvidence.vue'

const response = <T>(data: T) => ({ data, warnings: [], meta: { requestId: 'blue-sheet-test' } })
const suggestion = (opportunity: StrategyOpportunityDto, extra: Partial<BlueSheetAssessment> = {}): BlueSheetAssessment => ({
  state: 'suggested', ruleVersion: 'test-v1', ruleId: 'test-rule', suggestedLevel: 'low_probability', currentLevel: 'committed',
  reason: 'Test-only rule', opportunityModified: opportunity.modified!, fingerprint: 'facts-v1', canApply: true,
  facts: { openRedFlags: 1, highRedFlags: 1, unclassifiedRedFlags: 0, opposedStakeholders: 0, coveredRoles: ['Economic Buyer'], supportingRoles: ['Economic Buyer'] }, ...extra,
})
async function setup() {
  const api = createMockApi({ role: 'Sales', latency: 0, userName: 'Demo Staff 01' })
  const pinia = createPinia(), app = useAppStore(pinia)
  app.bootstrap = (await api.getBootstrap()).data
  const opportunity = (await api.getStrategyOpportunity('OPP-001')).data
  opportunity.modified = '2026-10-05T08:00:00.000000Z'
  opportunity.redFlags = ['Budget not confirmed']
  opportunity.redFlagRecords = [{ id: 'flag-1', text: 'Budget not confirmed', severity: '', status: 'Open', updatedAt: null, updatedBy: null }]
  api.saveBlueSheetFlags = vi.fn(async () => response({ ...opportunity, modified: '2026-10-05T09:00:00.000000Z' }))
  api.getBlueSheetAssessment = vi.fn(async () => response(suggestion(opportunity)))
  api.applyBlueSheetSuggestion = vi.fn(async () => response({ ...opportunity, probabilityLevel: 'low_probability' as const }))
  const wrapper = mount(BlueSheetPanel, { props: { opportunity, apiClient: api }, global: { plugins: [pinia] } })
  return { wrapper, api, opportunity, app, pinia }
}
afterEach(() => setLocale('zh-CN'))

describe('Blue Sheet', () => {
  it('saves stable flag ids, handling state and the version captured when editing opened', async () => {
    const { wrapper, api, opportunity } = await setup()
    expect(wrapper.text()).toContain('未分类')
    await wrapper.get('[data-blue-flags-edit]').trigger('click')
    await wrapper.findAll('select')[0].setValue('High')
    await wrapper.findAll('select')[1].setValue('Resolved')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.saveBlueSheetFlags).toHaveBeenCalledWith(opportunity.id, { items: [{ id: 'flag-1', text: 'Budget not confirmed', severity: 'High', status: 'Resolved' }] }, opportunity.modified)
    expect(wrapper.emitted('updated')).toHaveLength(1)
    wrapper.unmount()
  })
  it('keeps a conflicted draft and requires an explicit reload', async () => {
    const { wrapper, api, opportunity } = await setup()
    api.saveBlueSheetFlags = vi.fn().mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed', 'conflict'))
    api.getStrategyOpportunity = vi.fn(async () => response({ ...opportunity, modified: 'new-version' }))
    await wrapper.get('[data-blue-flags-edit]').trigger('click')
    await wrapper.get('textarea').setValue('Draft risk')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Draft risk')
    expect(wrapper.get('[data-blue-flags-save]').attributes('disabled')).toBeDefined()
    api.getStrategyOpportunity = vi.fn().mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce(response({ ...opportunity, modified: 'new-version' }))
    await wrapper.get('[data-blue-reload]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-blue-flags-save]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-blue-reload]').trigger('click'); await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(api.saveBlueSheetFlags).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('updated')?.[0]?.[0]).toEqual(expect.objectContaining({ modified: 'new-version' }))
    wrapper.unmount()
  })
  it('offers no edit and no confirmation on an archived Opportunity', async () => {
    const { wrapper, api, opportunity } = await setup()
    // The editor open when the page archives the deal closes with it.
    await wrapper.get('[data-blue-flags-edit]').trigger('click')
    expect(wrapper.find('form').exists()).toBe(true)
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true } })
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.find('[data-blue-flags-edit]').exists()).toBe(false)
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-blue-suggested]').exists()).toBe(true)
    expect(wrapper.find('[data-blue-apply]').exists()).toBe(false)
    expect(wrapper.get('[data-blue-archived]').text()).toContain('商机已归档')
    expect(api.saveBlueSheetFlags).not.toHaveBeenCalled()
    expect(api.applyBlueSheetSuggestion).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('closes the editor the archive finds open with its error, answers its save in flight to no one, and edits again after the restore', async () => {
    const { wrapper, api, opportunity } = await setup()
    // A save refused, its error shown, when the page archives the deal under the editor (a version of its own).
    await wrapper.get('[data-blue-flags-edit]').trigger('click')
    api.saveBlueSheetFlags = vi.fn().mockRejectedValueOnce(new Error('Network unavailable'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T10:00:00.000000Z' } })
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    // Restored and edited again, a save in flight when the page archives the deal once more.
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T11:00:00.000000Z' } })
    await wrapper.get('[data-blue-flags-edit]').trigger('click')
    await wrapper.get('textarea').setValue('Draft risk')
    let answer!: () => void
    api.saveBlueSheetFlags = vi.fn(async () => {
      await new Promise<void>(resolve => { answer = resolve })
      return response({ ...opportunity, modified: '2026-10-05T12:00:00.000000Z' })
    })
    await wrapper.get('form').trigger('submit')
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T13:00:00.000000Z' } })
    expect(wrapper.find('form').exists()).toBe(false)
    answer(); await flushPromises()
    expect(wrapper.emitted('updated')).toBeUndefined()
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T14:00:00.000000Z' } })
    expect(wrapper.find('[data-blue-reload]').exists()).toBe(false)
    expect(wrapper.get('[data-blue-flags-edit]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-blue-flags-edit]').trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Budget not confirmed')
    wrapper.unmount()
  })
  it('shows a suggestion asked for before the archive, and says it is older than the deal once the deal is restored', async () => {
    const { wrapper, api, opportunity } = await setup()
    let answer!: () => void
    api.getBlueSheetAssessment = vi.fn(async () => {
      await new Promise<void>(resolve => { answer = resolve })
      return response(suggestion(opportunity))
    })
    await wrapper.get('[data-blue-assess]').trigger('click')
    // The page archives the deal while the suggestion is asked for (no editor open): it is shown with the archive's
    // note, and the record's change is not announced while nothing can be confirmed.
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T10:00:00.000000Z' } })
    answer(); await flushPromises()
    expect(wrapper.find('[data-blue-suggested]').exists()).toBe(true)
    expect(wrapper.find('[data-blue-archived]').exists()).toBe(true)
    expect(wrapper.find('[data-blue-reload]').exists()).toBe(false)
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T11:00:00.000000Z' } })
    await wrapper.get('[data-blue-reason]').setValue('Budget frozen')
    await wrapper.get('[data-blue-plan]').setValue('Meet the buyer')
    expect(wrapper.find('[data-blue-reload]').exists()).toBe(true)
    expect(wrapper.get('[data-blue-apply]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('keeps a suggestion shown when the deal is archived, and takes its confirmation answered then as done without handing the deal back', async () => {
    const { wrapper, api, opportunity } = await setup()
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    await wrapper.get('[data-blue-reason]').setValue('Budget frozen')
    await wrapper.get('[data-blue-plan]').setValue('Meet the buyer')
    let answer!: () => void
    api.applyBlueSheetSuggestion = vi.fn(async () => {
      await new Promise<void>(resolve => { answer = resolve })
      return response({ ...opportunity, probabilityLevel: 'low_probability' as const, modified: '2026-10-05T09:30:00.000000Z' })
    })
    await wrapper.get('[data-blue-apply]').trigger('click')
    // The page archives the deal while the confirmation is in flight: the suggestion stays, with the archive's note.
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T10:00:00.000000Z' } })
    expect(wrapper.find('[data-blue-suggested]').exists()).toBe(true)
    expect(wrapper.find('[data-blue-archived]').exists()).toBe(true)
    // Its answer, the deal from before the archive, is not handed back; the confirmation took, so the suggestion goes.
    answer(); await flushPromises()
    expect(api.applyBlueSheetSuggestion).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('updated')).toBeUndefined()
    expect(wrapper.find('[data-blue-suggested]').exists()).toBe(false)
    expect(wrapper.get('[data-blue-assess]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('answers a confirmation in flight across an archive and its restore to no one, and shows no failure answered after them', async () => {
    const { wrapper, api, opportunity } = await setup()
    const confirm = async () => {
      await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
      await wrapper.get('[data-blue-reason]').setValue('Budget frozen')
      await wrapper.get('[data-blue-plan]').setValue('Meet the buyer')
      await wrapper.get('[data-blue-apply]').trigger('click')
    }
    let answer!: () => void
    api.applyBlueSheetSuggestion = vi.fn(async () => {
      await new Promise<void>(resolve => { answer = resolve })
      return response({ ...opportunity, probabilityLevel: 'low_probability' as const, modified: '2026-10-05T09:30:00.000000Z' })
    })
    await confirm()
    // Archived, then restored, while the confirmation is in flight: its answer is the deal from before both.
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T10:00:00.000000Z' } })
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T11:00:00.000000Z' } })
    answer(); await flushPromises()
    expect(wrapper.emitted('updated')).toBeUndefined()
    expect(wrapper.find('[data-blue-suggested]').exists()).toBe(false)
    expect(wrapper.find('[data-blue-reload]').exists()).toBe(false)
    // A confirmation refused once an archive took the deal, answered after the restore: its sentence is not shown.
    const restored = { ...opportunity, modified: '2026-10-05T11:00:00.000000Z' }
    api.getBlueSheetAssessment = vi.fn(async () => response(suggestion(restored)))
    let refuse!: () => void
    api.applyBlueSheetSuggestion = vi.fn(async () => {
      await new Promise<void>(resolve => { refuse = resolve })
      throw new CrmApiError('INVALID_TRANSITION', 'This Opportunity is archived.', 'archived')
    })
    await confirm()
    await wrapper.setProps({ opportunity: { ...restored, archived: true, modified: '2026-10-05T12:00:00.000000Z' } })
    await wrapper.setProps({ opportunity: { ...restored, archived: false, modified: '2026-10-05T13:00:00.000000Z' } })
    refuse(); await flushPromises()
    expect(api.applyBlueSheetSuggestion).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('[role="alert"]').filter(alert => !alert.find('[data-blue-reload]').exists())).toHaveLength(0)
    wrapper.unmount()
  })
  it('shows no failure of a reload answered after the page archived and restored the deal', async () => {
    const { wrapper, api, opportunity } = await setup()
    api.saveBlueSheetFlags = vi.fn().mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed', 'conflict'))
    await wrapper.get('[data-blue-flags-edit]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    await wrapper.findAll('footer button').find(button => button.text() === '取消')!.trigger('click')
    let fail!: () => void
    api.getStrategyOpportunity = vi.fn(async () => {
      await new Promise<void>(resolve => { fail = resolve })
      throw new Error('Network unavailable')
    })
    await wrapper.get('[data-blue-reload]').trigger('click')
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T10:00:00.000000Z' } })
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T11:00:00.000000Z' } })
    fail(); await flushPromises()
    expect(api.getStrategyOpportunity).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('[data-blue-flags-edit]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('announces a suggestion read while the deal was archived as older once it is restored, without saying who confirms', async () => {
    const { wrapper, api, opportunity } = await setup()
    const archived = { ...opportunity, archived: true, modified: '2026-10-05T10:00:00.000000Z' }
    await wrapper.setProps({ opportunity: archived })
    api.getBlueSheetAssessment = vi.fn(async () => response(suggestion(archived, { canApply: false })))
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-blue-archived]').exists()).toBe(true)
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T11:00:00.000000Z' } })
    expect(wrapper.find('[data-blue-reload]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('仅商机负责人可确认新档位')
    wrapper.unmount()
  })
  it('clears an error and a stale mark the archive finds outside the editor, and answers a reload in flight to no one', async () => {
    const { wrapper, api, opportunity } = await setup()
    api.saveBlueSheetFlags = vi.fn().mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed', 'conflict'))
    const conflictThenCancel = async () => {
      await wrapper.get('[data-blue-flags-edit]').trigger('click')
      await wrapper.get('form').trigger('submit'); await flushPromises()
      await wrapper.findAll('footer button').find(button => button.text() === '取消')!.trigger('click')
      expect(wrapper.find('form').exists()).toBe(false)
      expect(wrapper.find('[data-blue-reload]').exists()).toBe(true)
    }
    // A save refused as changed, its editor cancelled: the error and the stale mark stay outside it until the archive.
    await conflictThenCancel()
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T10:00:00.000000Z' } })
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T11:00:00.000000Z' } })
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    // Again, with a reload in flight when the page archives and restores the deal: its answer, the deal from before
    // both, is not handed back.
    await conflictThenCancel()
    let answer!: () => void
    api.getStrategyOpportunity = vi.fn(async () => {
      await new Promise<void>(resolve => { answer = resolve })
      return response({ ...opportunity, modified: '2026-10-05T11:30:00.000000Z' })
    })
    await wrapper.get('[data-blue-reload]').trigger('click')
    await wrapper.setProps({ opportunity: { ...opportunity, archived: true, modified: '2026-10-05T12:00:00.000000Z' } })
    await wrapper.setProps({ opportunity: { ...opportunity, archived: false, modified: '2026-10-05T13:00:00.000000Z' } })
    answer(); await flushPromises()
    expect(wrapper.emitted('updated')).toBeUndefined()
    expect(wrapper.get('[data-blue-flags-edit]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('tells a reader of a deal in use who may not confirm why, not the archive', async () => {
    const { wrapper, api, opportunity } = await setup()
    api.getBlueSheetAssessment = vi.fn(async () => response(suggestion(opportunity, { canApply: false })))
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-blue-apply]').exists()).toBe(false)
    expect(wrapper.find('[data-blue-archived]').exists()).toBe(false)
    expect(wrapper.text()).toContain('仅商机负责人可确认新档位')
    wrapper.unmount()
  })
  it('shows an unconfigured rule set without producing or applying a level', async () => {
    const { wrapper, api, opportunity } = await setup()
    api.getBlueSheetAssessment = vi.fn(async () => response(suggestion(opportunity, { state: 'unconfigured', suggestedLevel: null, ruleVersion: null, ruleId: null, reason: null })))
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-blue-unconfigured]').text()).toContain('暂不推荐档位')
    expect(wrapper.find('[data-blue-apply]').exists()).toBe(false)
    expect(api.applyBlueSheetSuggestion).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('requires explicit confirmation and downgrade details with the assessed fingerprint', async () => {
    const { wrapper, api, opportunity } = await setup()
    setLocale('en-US')
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    expect(api.applyBlueSheetSuggestion).not.toHaveBeenCalled()
    expect(wrapper.get('[data-blue-apply]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-blue-reason]').setValue('Budget withdrawn')
    await wrapper.get('[data-blue-plan]').setValue('Meet buyer')
    await wrapper.get('[data-blue-apply]').trigger('click'); await flushPromises()
    expect(api.applyBlueSheetSuggestion).toHaveBeenCalledWith(opportunity.id, { fingerprint: 'facts-v1', probabilityReason: 'Budget withdrawn', probabilityActionPlan: 'Meet buyer' }, opportunity.modified)
    wrapper.unmount()
  })
  it('refuses a suggestion after an externally refreshed parent version', async () => {
    const { wrapper, api, opportunity } = await setup()
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    await wrapper.setProps({ opportunity: { ...opportunity, modified: 'new-version' } })
    await wrapper.get('[data-blue-reason]').setValue('Reason')
    await wrapper.get('[data-blue-plan]').setValue('Plan')
    expect(wrapper.get('[data-blue-apply]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-blue-apply]').trigger('click')
    expect(api.applyBlueSheetSuggestion).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('hands back a confirmation answered after the deal changed meanwhile, and keeps the notice to reload', async () => {
    const { wrapper, api, opportunity } = await setup()
    await wrapper.get('[data-blue-assess]').trigger('click'); await flushPromises()
    await wrapper.get('[data-blue-reason]').setValue('Budget frozen')
    await wrapper.get('[data-blue-plan]').setValue('Meet the buyer')
    const confirmed = { ...opportunity, probabilityLevel: 'low_probability' as const, modified: '2026-10-05T09:30:00.000000Z' }
    let answer!: () => void
    api.applyBlueSheetSuggestion = vi.fn(async () => {
      await new Promise<void>(resolve => { answer = resolve })
      return response(confirmed)
    })
    await wrapper.get('[data-blue-apply]').trigger('click')
    // Another change reaches the page while the confirmation is in flight, no archive: the deal it answers with may be
    // older than the page's, so the notice to reload stays once the suggestion goes.
    await wrapper.setProps({ opportunity: { ...opportunity, modified: '2026-10-05T10:00:00.000000Z' } })
    answer(); await flushPromises()
    expect(wrapper.emitted('updated')).toEqual([[confirmed]])
    expect(wrapper.find('[data-blue-suggested]').exists()).toBe(false)
    expect(wrapper.find('[data-blue-reload]').exists()).toBe(true)
    wrapper.unmount()
  })
  it('discards a delayed response after the identity changes', async () => {
    const { wrapper, api, opportunity, app } = await setup()
    let finish!: (value: ReturnType<typeof response<BlueSheetAssessment>>) => void
    api.getBlueSheetAssessment = vi.fn(() => new Promise<ReturnType<typeof response<BlueSheetAssessment>>>(resolve => { finish = resolve }))
    await wrapper.get('[data-blue-assess]').trigger('click')
    app.identityRevision++; await flushPromises()
    finish(response(suggestion(opportunity))); await flushPromises()
    expect(wrapper.find('[data-blue-suggested]').exists()).toBe(false)
    expect(wrapper.emitted('updated')).toBeUndefined()
    wrapper.unmount()
  })
  it('loads current competition as plain-text evidence and cites only on request', async () => {
    const { wrapper: flags, api, opportunity, pinia } = await setup()
    flags.unmount()
    api.getStrategyOpportunity = vi.fn(async () => response({ ...opportunity, competitors: [{ name: '<img src=x>', strengths: 'Price', response: 'Compare total cost' }] }))
    const wrapper = mount(BlueSheetCompetitionEvidence, { props: { opportunityId: opportunity.id, apiClient: api }, global: { plugins: [pinia] } })
    expect(api.getStrategyOpportunity).not.toHaveBeenCalled()
    await wrapper.get('[data-blue-competition-load]').trigger('click'); await flushPromises()
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.emitted('cite')).toBeUndefined()
    await wrapper.get('[data-blue-competition-cite]').trigger('click')
    expect(wrapper.emitted('cite')?.[0]?.[0]).toContain('非已确认丢单原因')
    expect(wrapper.emitted('cite')?.[0]?.[0]).toContain(opportunity.modified)
    wrapper.unmount()
  })
  it('preserves legacy competition notes as plain-text evidence with an explicit citation', async () => {
    const { wrapper: flags, api, opportunity, pinia } = await setup()
    flags.unmount(); setLocale('en-US')
    const competition = 'KLA · final shortlist\n<img src=x> Sales observation'
    api.getStrategyOpportunity = vi.fn(async () => response({ ...opportunity, competitors: [], competition }))
    const wrapper = mount(BlueSheetCompetitionEvidence, { props: { opportunityId: opportunity.id, apiClient: api }, global: { plugins: [pinia] } })
    await wrapper.get('[data-blue-competition-load]').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('No competition information recorded.')
    expect(wrapper.get('[data-blue-competition-notes]').text()).toContain(competition)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.emitted('cite')).toBeUndefined()
    await wrapper.get('[data-blue-competition-cite-notes]').trigger('click')
    expect(wrapper.emitted('cite')?.[0]?.[0]).toContain('not a confirmed loss cause')
    expect(wrapper.emitted('cite')?.[0]?.[0]).toContain(`${opportunity.id} · ${opportunity.modified}`)
    expect(wrapper.emitted('cite')?.[0]?.[0]).toContain(competition)
    wrapper.unmount()
  })
  it('clears competition notes on identity change and ignores the old delayed reload', async () => {
    const { wrapper: flags, api, opportunity, pinia, app } = await setup()
    flags.unmount()
    api.getStrategyOpportunity = vi.fn(async () => response({ ...opportunity, competitors: [], competition: 'Private notes' }))
    const wrapper = mount(BlueSheetCompetitionEvidence, { props: { opportunityId: opportunity.id, apiClient: api }, global: { plugins: [pinia] } })
    await wrapper.get('[data-blue-competition-load]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Private notes')
    let finish!: (value: ReturnType<typeof response<StrategyOpportunityDto>>) => void
    api.getStrategyOpportunity = vi.fn(() => new Promise<ReturnType<typeof response<StrategyOpportunityDto>>>(resolve => { finish = resolve }))
    await wrapper.get('[data-blue-competition-load]').trigger('click')
    expect(wrapper.text()).not.toContain('Private notes')
    app.identityRevision++; await flushPromises()
    finish(response({ ...opportunity, competitors: [], competition: 'Old delayed notes' })); await flushPromises()
    expect(wrapper.text()).not.toContain('Old delayed notes')
    expect(wrapper.find('[data-blue-competition-cite-notes]').exists()).toBe(false)
    wrapper.unmount()
  })
})
