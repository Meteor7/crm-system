import type { EvaluationDto, TestRunDto } from '@/types/crm'

export type TestRunAction = 'reschedule' | 'complete' | 'cancel'

export function canManageTestRun(evaluation: EvaluationDto, run: TestRunDto): boolean {
  return ['Scheduled', 'Testing'].includes(evaluation.status)
    && run.status === 'Planned'
    && (run.round ?? 1) === (evaluation.testRound ?? 1)
}
