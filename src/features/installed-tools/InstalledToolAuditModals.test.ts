import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import InstalledToolEditorModal from './InstalledToolEditorModal.vue'
import InstalledToolServiceModal from './InstalledToolServiceModal.vue'
import InstalledToolVersionModal from './InstalledToolVersionModal.vue'
import InstalledToolTransitionModal from './InstalledToolTransitionModal.vue'

async function detailFixture() {
  return (await createMockApi({ latency: 0 }).getInstalledTool('TOOL-001')).data
}

describe('Installed Tool audited forms', () => {
  it('submits lifecycle evidence as text fields only', async () => {
    const wrapper = mount(InstalledToolTransitionModal, { props: { stage: 'FAT' } })
    const textareas = wrapper.findAll('textarea')
    await wrapper.findAll('input')[1].setValue('Customer signed')
    await textareas[0].setValue('FAT passed')
    await textareas[1].setValue('None')
    await textareas[2].setValue('Completed on site')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    const payload = wrapper.emitted('submit')?.[0]?.[0] as { evidence: string[] }
    expect(payload.evidence).toEqual([])
  })

  it('creates a version command without allowing the client to provide fromValue', async () => {
    const tool = await detailFixture()
    const wrapper = mount(InstalledToolVersionModal, { props: { tool } })
    const inputs = wrapper.findAll('input')
    await inputs[2].setValue('7.0.0')
    await wrapper.findAll('textarea')[0].setValue('Approved release')
    await wrapper.get('[data-modal-submit]').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      changeType: 'Software',
      toValue: '7.0.0',
      reason: 'Approved release',
    })
    expect(wrapper.emitted('submit')?.[0]?.[0]).not.toHaveProperty('fromValue')
  })

  it('requires owner and due date when a service record has a next action', async () => {
    const tool = await detailFixture()
    const actionOwners = [{ id: tool.engineerOwner, name: 'Assigned Engineer', role: 'Engineer' as const }]
    const wrapper = mount(InstalledToolServiceModal, { props: { tool, actionOwners } })
    const textareas = wrapper.findAll('textarea')
    await textareas[0].setValue('Remote issue resolved')
    await textareas[1].setValue('None')
    await wrapper.get('[aria-label="下一步行动"]').setValue('Monitor for seven days')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()

    await wrapper.get('[aria-label="行动负责人"]').setValue(tool.engineerOwner)
    await wrapper.get('[aria-label="截止日期"]').setValue('2026-08-20')
    await wrapper.get('[data-modal-submit]').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      nextAction: 'Monitor for seven days',
      actionOwner: tool.engineerOwner,
      due: '2026-08-20',
    })
  })

  it('keeps status and version fields out of the master-data editor', async () => {
    const tool = await detailFixture()
    const wrapper = mount(InstalledToolEditorModal, {
      props: {
        tool,
        sites: [{ id: tool.siteId, name: tool.site, city: 'Wuhan', type: 'Fab', process: 'Production', status: '量产' }],
        engineers: [{ id: tool.engineerOwner, name: 'Assigned Engineer', role: 'Engineer' }],
        canReassign: true,
      },
    })

    expect(wrapper.text()).not.toContain('Software')
    expect(wrapper.text()).not.toContain('Firmware')
    expect(wrapper.text()).not.toContain('Configuration')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    const payload = wrapper.emitted('submit')?.[0]?.[0]
    expect(payload).not.toHaveProperty('status')
    expect(payload).not.toHaveProperty('software')
    expect(payload).not.toHaveProperty('firmware')
    expect(payload).not.toHaveProperty('configuration')
  })
})
