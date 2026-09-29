import { describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import type { CreateStrategyOpportunityInput } from '@/types/workspaces'
import { EQUIPMENT_PRESETS, equipmentOptions, equipmentText, matchingEquipment } from './equipment'

const input = (toolType: string, title: string): CreateStrategyOpportunityInput => ({
  accountId: 'ACC-001', siteId: 'SITE-001', title, owner: 'person002@crm.example.invalid', qualificationConfirmed: true,
  probabilityLevel: 'pipeline', amount: '1000.00', amountCny: '1000.00', intentScore: 60, poDate: '2026-12-31',
  toolType, saleType: 'New Equipment', subRegion: 'East China', currency: 'CNY',
})

describe('equipment catalog rules', () => {
  it('stores other spellings of a preset or an existing custom type as the existing spelling', () => {
    const options = equipmentOptions(['Probe 9'])
    expect(options).toEqual([...EQUIPMENT_PRESETS, 'Probe 9'])
    expect(matchingEquipment('NANSI', options)).toBe('Nansi')
    expect(matchingEquipment('nan-si', options)).toBe('Nansi')
    expect(matchingEquipment('probe9', options)).toBe('Probe 9')
    expect(matchingEquipment('Kibo 4895C', options)).toBe('')
    expect([equipmentText('  Probe   10 '), equipmentText(''), equipmentText('A<B>'), equipmentText('x'.repeat(141))]).toEqual(['Probe 10', '', '', ''])
    // Full-width letters, zero-width spaces and punctuation-only input, as the server treats them.
    expect(matchingEquipment(equipmentText('ＮＡＮＳＩ'), options)).toBe('Nansi')
    expect(matchingEquipment(equipmentText('Nan\u200bsi'), options)).toBe('Nansi')
    expect(matchingEquipment(equipmentText('Drakéns'), options)).toBe('Drakens')
    expect(matchingEquipment('Probe—9', options)).toBe('Probe 9')
    expect(['...', '/', '-', '\u200b', '!!!', '？？？'].map(equipmentText)).toEqual(['', '', '', '', '', ''])
  })

  it('keeps the demo adapter in step with the server catalog', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager', userName: '演示员工24' })
    expect((await api.listEquipmentTypes()).data.slice(0, 5)).toEqual([...EQUIPMENT_PRESETS])
    expect((await api.createStrategyOpportunity(input('nansi', 'Equipment preset'))).data.toolType).toBe('Nansi')
    const custom = (await api.createStrategyOpportunity(input('Probe  11', 'Equipment custom'))).data
    expect(custom.toolType).toBe('Probe 11')
    expect((await api.listEquipmentTypes()).data).toContain('Probe 11')
    await expect(api.createStrategyOpportunity(input('  ', 'Equipment missing'))).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(api.updateStrategyOpportunity(custom.id, { toolType: 42 as unknown as string }, custom.modified)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('adds a custom type only when the save succeeds', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager', userName: '演示员工24' })
    await expect(api.createStrategyOpportunity({ ...input('Probe Orphan', 'Equipment orphan'), siteId: 'NO-SUCH-SITE' })).rejects.toBeTruthy()
    expect((await api.listEquipmentTypes()).data).not.toContain('Probe Orphan')
  })
})
