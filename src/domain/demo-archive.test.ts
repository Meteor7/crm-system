import { describe, expect, it } from 'vitest'
import type { DemoWorkflowDto } from '@/types/workspaces'
import {
  groupDemoArchives,
  isConcreteEngineerOwner,
} from './demo-archive'

function workflow(
  id: string,
  account: string,
  equipment: string,
  progressAt: string,
): DemoWorkflowDto {
  return {
    id,
    account,
    equipment,
    tracking: { lastProgressAt: progressAt },
  } as DemoWorkflowDto
}

describe('Demo archive classification', () => {
  it('groups completed Demos by customer and orders each group by latest progress', () => {
    const groups = groupDemoArchives([
      workflow('DR-001', '客户 A', 'AX-9000', '2026-07-20T09:00:00+08:00'),
      workflow('DR-002', '客户 B', 'AX-9000', '2026-07-22T09:00:00+08:00'),
      workflow('DR-003', '客户 A', 'VI-620', '2026-07-25T09:00:00+08:00'),
    ], 'customer')

    expect(groups.map(({ label, count }) => ({ label, count }))).toEqual([
      { label: '客户 A', count: 2 },
      { label: '客户 B', count: 1 },
    ])
    expect(groups[0].items.map((item) => item.id)).toEqual(['DR-003', 'DR-001'])
  })

  it('groups completed Demos by their assigned or requested equipment', () => {
    const groups = groupDemoArchives([
      workflow('DR-001', '客户 A', 'AX-9000', '2026-07-20T09:00:00+08:00'),
      workflow('DR-002', '客户 B', 'AX-9000', '2026-07-22T09:00:00+08:00'),
      workflow('DR-003', '客户 A', '', '2026-07-25T09:00:00+08:00'),
    ], 'equipment')

    expect(groups.map(({ label, count }) => ({ label, count }))).toEqual([
      { label: 'AX-9000', count: 2 },
      { label: '未指定设备', count: 1 },
    ])
  })

  it('accepts only a concrete engineer as the unique owner', () => {
    expect(isConcreteEngineerOwner('')).toBe(false)
    expect(isConcreteEngineerOwner('FAE Team')).toBe(false)
    expect(isConcreteEngineerOwner('未分配')).toBe(false)
    expect(isConcreteEngineerOwner('FAE Mia')).toBe(true)
  })
})
