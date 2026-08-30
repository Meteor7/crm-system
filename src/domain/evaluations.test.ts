import { describe, expect, it } from 'vitest'
import {
  evaluationGroup,
  evaluationPreparationStatus,
  evaluationStatusOptions,
  hasCompletedTestRun,
  isEvaluationPreparationComplete,
  isIsoDate,
} from './evaluations'

describe('Evaluation workflow', () => {
  it('moves Testing through Internal Review before Customer Review', () => {
    expect(evaluationStatusOptions('Testing')).toEqual(['Testing', 'Internal Review', 'Rejected'])
    expect(evaluationStatusOptions('Internal Review')).toEqual(['Internal Review', 'Customer Review', 'Rejected'])
    expect(evaluationStatusOptions('Testing')).not.toContain('Requested')
    expect(evaluationStatusOptions('Testing')).not.toContain('Analysis')
    expect(evaluationStatusOptions('Testing')).not.toContain('On Hold')
  })

  it('keeps accepted and rejected evaluations terminal', () => {
    expect(evaluationStatusOptions('Accepted')).toEqual(['Accepted'])
    expect(evaluationStatusOptions('Rejected')).toEqual(['Rejected'])
  })

  it('maps existing statuses into four stable board groups while absorbing legacy Analysis', () => {
    expect(evaluationGroup('Requested')).toBe('Preparation')
    expect(evaluationGroup('Scope Confirmed')).toBe('Preparation')
    expect(evaluationGroup('Sample Received')).toBe('Preparation')
    expect(evaluationGroup('Scheduled')).toBe('Preparation')
    expect(evaluationGroup('Testing')).toBe('Test Execution')
    expect(evaluationGroup('Analysis')).toBe('Internal Review')
    expect(evaluationGroup('Internal Review')).toBe('Internal Review')
    expect(evaluationGroup('Customer Review')).toBe('Customer Review')
    expect(evaluationGroup('Accepted')).toBe('Closed')
    expect(evaluationGroup('Rejected')).toBe('Closed')
  })

  it('recognizes only real ISO calendar dates', () => {
    expect(isIsoDate('2026-09-30')).toBe(true)
    expect(isIsoDate('')).toBe(false)
    expect(isIsoDate('2026-09-31')).toBe(false)
    expect(isIsoDate('2026-13-01')).toBe(false)
  })

  it('keeps Wafer and Test preparation independent until both branches are complete', () => {
    const evaluation = {
      status: 'Requested' as const,
      waferPreparationStatus: 'Completed' as const,
      testPreparationStatus: 'Pending' as const,
    }

    expect(evaluationPreparationStatus(evaluation, 'wafer')).toBe('Completed')
    expect(evaluationPreparationStatus(evaluation, 'test')).toBe('Pending')
    expect(isEvaluationPreparationComplete(evaluation)).toBe(false)
    expect(isEvaluationPreparationComplete({
      ...evaluation,
      testPreparationStatus: 'Completed',
    })).toBe(true)
  })

  it('derives conservative preparation state for legacy records', () => {
    expect(evaluationPreparationStatus({ status: 'Requested' }, 'wafer')).toBe('Pending')
    expect(evaluationPreparationStatus({ status: 'Sample Received' }, 'wafer')).toBe('Completed')
    expect(evaluationPreparationStatus({ status: 'Sample Received' }, 'test')).toBe('Pending')
    expect(isEvaluationPreparationComplete({ status: 'Scheduled' })).toBe(true)
    expect(isEvaluationPreparationComplete({ status: 'Testing' })).toBe(true)
  })

  it('requires an explicitly Completed Test Run for review readiness', () => {
    expect(hasCompletedTestRun({ runs: [] })).toBe(false)
    expect(hasCompletedTestRun({ runs: [{ status: 'Planned' }] })).toBe(false)
    expect(hasCompletedTestRun({ runs: [{ status: 'Planned' }, { status: 'Completed' }] })).toBe(true)
  })
})
