import { describe, expect, it } from 'vitest'
import { procedureRuns, serviceAppointments } from './operations-data'
import { getProcedureBlockers, hasScheduleConflict } from './operations-rules'

describe('first demo operation rules', () => {
  it('detects overlapping appointments for the same engineer and day', () => {
    expect(hasScheduleConflict(serviceAppointments[1], serviceAppointments[2])).toBe(true)
    expect(hasScheduleConflict(serviceAppointments[0], serviceAppointments[1])).toBe(false)
  })

  it('keeps procedure execution blocked while mandatory evidence is pending', () => {
    expect(getProcedureBlockers(procedureRuns[0])).toEqual([
      '客户 MOC Approval',
      'Mandatory Backup 与 Checksum',
    ])
    expect(getProcedureBlockers({
      ...procedureRuns[0],
      checklist: procedureRuns[0].checklist.map((item) => ({ ...item, status: 'Passed' as const })),
    })).toEqual([])
  })
})
