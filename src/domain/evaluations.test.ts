import { describe, expect, it } from 'vitest'
import {
  evaluationGroup,
  evaluationPreparationStatus,
  canRetestEvaluation,
  canTerminateEvaluation,
  canTransitionEvaluation,
  evaluationStatusOptions,
  hasCompletedTestRun,
  isEvaluationPreparationComplete,
  isIsoDate,
  isTerminatedDemo,
  terminatedDemoRequestMatcher,
} from './evaluations'

describe('Evaluation workflow', () => {
  it('moves Testing through Internal Review before Customer Review', () => {
    expect(evaluationStatusOptions('Testing')).toEqual(['Testing', 'Internal Review'])
    expect(evaluationStatusOptions('Internal Review')).toEqual(['Internal Review', 'Customer Review'])
    expect(evaluationStatusOptions('Testing')).not.toContain('Requested')
    expect(evaluationStatusOptions('Testing')).not.toContain('Analysis')
    expect(evaluationStatusOptions('Testing')).not.toContain('On Hold')
  })

  it('keeps accepted and rejected evaluations terminal', () => {
    expect(evaluationStatusOptions('Accepted')).toEqual(['Accepted'])
    expect(evaluationStatusOptions('Rejected')).toEqual(['Rejected'])
  })

  it('offers archiving and retest as the only Customer Review exits', () => {
    expect(evaluationStatusOptions('Customer Review')).toEqual(['Customer Review', 'Accepted', 'Testing'])
    expect(canRetestEvaluation('Customer Review')).toBe(true)
  })

  it('no longer offers rejection anywhere in the active flow', () => {
    const active = ['Requested', 'Scope Confirmed', 'Sample Received', 'Scheduled', 'Testing', 'Analysis', 'Internal Review', 'Customer Review'] as const
    for (const status of active) {
      expect(evaluationStatusOptions(status), status).not.toContain('Rejected')
      expect(canTransitionEvaluation(status, 'Rejected'), status).toBe(false)
    }
  })

  it('lets every Demo Test that has not ended be terminated, including early and legacy stages', () => {
    const open = ['Requested', 'Scope Confirmed', 'Sample Received', 'Scheduled', 'Testing', 'Analysis', 'Internal Review', 'Customer Review'] as const
    for (const status of open) expect(canTerminateEvaluation(status), status).toBe(true)
    expect(canTerminateEvaluation('Accepted')).toBe(false)
    expect(canTerminateEvaluation('Rejected')).toBe(false)
  })

  it('treats only a Rejected record with a recorded reason as terminated', () => {
    expect(isTerminatedDemo({ status: 'Rejected', terminationReason: 'Customer paused the project' })).toBe(true)
    // Historical rejections predate termination and keep their original meaning.
    expect(isTerminatedDemo({ status: 'Rejected' })).toBe(false)
    expect(isTerminatedDemo({ status: 'Rejected', terminationReason: '   ' })).toBe(false)
    expect(isTerminatedDemo({ status: 'Rejected', terminationReason: null })).toBe(false)
    expect(isTerminatedDemo({ status: 'Accepted', terminationReason: 'stale' })).toBe(false)
    expect(isTerminatedDemo({ status: 'Testing', terminationReason: 'stale' })).toBe(false)
  })

  it('matches only the Demo Requests whose linked Demo Test was terminated', () => {
    const isTerminatedRequest = terminatedDemoRequestMatcher([
      { id: 'EVAL-TERMINATED', demoRequestId: 'DR-TERMINATED', status: 'Rejected', terminationReason: 'Customer paused the project' },
      { id: 'EVAL-BACK-LINK', demoRequestId: 'DR-BACK-LINK', status: 'Rejected', terminationReason: 'Budget frozen' },
      { id: 'EVAL-RUNNING', demoRequestId: 'DR-RUNNING', status: 'Testing' },
      { id: 'EVAL-HISTORICAL', demoRequestId: 'DR-HISTORICAL', status: 'Rejected' },
    ])
    expect(isTerminatedRequest({ id: 'DR-TERMINATED', evaluationId: 'EVAL-TERMINATED' })).toBe(true)
    expect(isTerminatedRequest({ id: 'DR-BACK-LINK' })).toBe(true)
    expect(isTerminatedRequest({ id: 'DR-RUNNING', evaluationId: 'EVAL-RUNNING' })).toBe(false)
    expect(isTerminatedRequest({ id: 'DR-HISTORICAL', evaluationId: 'EVAL-HISTORICAL' })).toBe(false)
    expect(isTerminatedRequest({ id: 'DR-NO-EVALUATION' })).toBe(false)
    // The request's own link wins over a stale back-reference from another Evaluation.
    expect(isTerminatedRequest({ id: 'DR-TERMINATED', evaluationId: 'EVAL-RUNNING' })).toBe(false)
  })

  it('allows retest only from Customer Review', () => {
    expect(canTransitionEvaluation('Customer Review', 'Testing')).toBe(true)
    for (const status of ['Internal Review', 'Analysis', 'Scheduled', 'Accepted'] as const) {
      expect(canRetestEvaluation(status), status).toBe(false)
    }
    expect(canTransitionEvaluation('Internal Review', 'Testing')).toBe(false)
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

  it('only counts Completed Test Runs from the current round after a retest', () => {
    const roundOne = { status: 'Completed', round: 1 } as const
    expect(hasCompletedTestRun({ runs: [roundOne], testRound: 1 })).toBe(true)
    expect(hasCompletedTestRun({ runs: [roundOne], testRound: 2 })).toBe(false)
    expect(hasCompletedTestRun({ runs: [roundOne, { status: 'Planned', round: 2 }], testRound: 2 })).toBe(false)
    expect(hasCompletedTestRun({ runs: [roundOne, { status: 'Completed', round: 2 }], testRound: 2 })).toBe(true)
    // Records from before rounds existed read as round 1.
    expect(hasCompletedTestRun({ runs: [{ status: 'Completed' }] })).toBe(true)
    expect(hasCompletedTestRun({ runs: [{ status: 'Completed' }], testRound: 2 })).toBe(false)
  })
})
