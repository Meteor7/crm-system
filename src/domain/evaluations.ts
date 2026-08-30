import type {
  EvaluationDto,
  EvaluationPreparationBranch,
  EvaluationPreparationStatus,
  EvaluationStatus,
} from '@/types/crm'

const activeFlow: EvaluationStatus[] = ['Requested', 'Scope Confirmed', 'Sample Received', 'Scheduled', 'Testing', 'Internal Review', 'Customer Review']

export type EvaluationGroup = 'Preparation' | 'Test Execution' | 'Internal Review' | 'Customer Review' | 'Closed'

type PreparationEvaluation = Pick<EvaluationDto,
  'status' | 'waferPreparationStatus' | 'testPreparationStatus'
>

export function evaluationPreparationStatus(
  evaluation: PreparationEvaluation,
  branch: EvaluationPreparationBranch,
): EvaluationPreparationStatus {
  const explicit = branch === 'wafer'
    ? evaluation.waferPreparationStatus
    : evaluation.testPreparationStatus
  if (explicit) return explicit
  if (['Scheduled', 'Testing', 'Analysis', 'Internal Review', 'Customer Review', 'Accepted'].includes(evaluation.status)) {
    return 'Completed'
  }
  if (branch === 'wafer' && evaluation.status === 'Sample Received') return 'Completed'
  return 'Pending'
}

export function isEvaluationPreparationComplete(evaluation: PreparationEvaluation): boolean {
  return evaluationPreparationStatus(evaluation, 'wafer') === 'Completed'
    && evaluationPreparationStatus(evaluation, 'test') === 'Completed'
}

export function hasCompletedTestRun(evaluation: {
  runs: ReadonlyArray<Pick<EvaluationDto['runs'][number], 'status'>>
}): boolean {
  return evaluation.runs.some((run) => run.status === 'Completed')
}

export function isIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const dateTime = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(dateTime) && new Date(dateTime).toISOString().slice(0, 10) === value
}

export function evaluationGroup(status: EvaluationStatus): EvaluationGroup {
  if (['Requested', 'Scope Confirmed', 'Sample Received'].includes(status)) return 'Preparation'
  if (status === 'Scheduled') return 'Preparation'
  if (status === 'Testing') return 'Test Execution'
  if (status === 'Analysis' || status === 'Internal Review') return 'Internal Review'
  if (status === 'Customer Review') return 'Customer Review'
  return 'Closed'
}

export function evaluationStatusOptions(current: EvaluationStatus): EvaluationStatus[] {
  if (current === 'Accepted' || current === 'Rejected') return [current]
  if (current === 'Analysis') return ['Analysis', 'Customer Review', 'Rejected']
  const index = activeFlow.indexOf(current)
  const next: EvaluationStatus = current === 'Customer Review' ? 'Accepted' : activeFlow[index + 1]
  return [current, next, 'Rejected']
}

export function canTransitionEvaluation(current: EvaluationStatus, next: EvaluationStatus) {
  return evaluationStatusOptions(current).includes(next)
}
