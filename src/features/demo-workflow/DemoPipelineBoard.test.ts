import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import type { DemoLifecycleStage } from '@/types/crm'
import DemoPipelineBoard from './DemoPipelineBoard.vue'

describe('DemoPipelineBoard density', () => {
  it('keeps 42 active demos in six independently scrollable lifecycle columns', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-28' })
    const source = (await api.listDemoWorkflows()).data.items.find((item) => item.archiveCategory === 'In Progress')!
    const stages: DemoLifecycleStage[] = [
      'Engineer Review',
      'Manager Approval',
      'Test Preparation',
      'Test Execution',
      'Internal Review',
      'Customer Review',
    ]
    const items = Array.from({ length: 42 }, (_, index) => ({
      ...source,
      id: `DR-DENSITY-${String(index + 1).padStart(2, '0')}`,
      title: `Density verification ${index + 1}`,
      stage: stages[index % stages.length],
    }))

    const wrapper = mount(DemoPipelineBoard, {
      props: {
        items,
        search: '',
        health: 'all',
        salesOwner: 'all',
        engineerOwner: 'all',
      },
    })

    expect(wrapper.findAll('.pipeline-card')).toHaveLength(42)
    expect(wrapper.findComponent({ name: 'PipelineBoard' }).exists()).toBe(true)
    expect(wrapper.findAll('[data-demo-stage-scroll]')).toHaveLength(6)
    expect(wrapper.findAll('[data-demo-stage-scroll]').every((column) => column.findAll('.pipeline-card').length === 7)).toBe(true)
  })
})
