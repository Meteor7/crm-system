import type {
  DemoProjectTimelineState,
  DemoProjectTimelineStepDto,
  DemoWorkflowDto,
} from '@/types/workspaces'

export type DemoProjectCycleGroup = 'request' | 'test' | 'completed'

const timelineMilestones = [
  { key: 'sales-preparation', label: 'Sales Preparation' },
  { key: 'engineer-review', label: 'Engineer Review' },
  { key: 'manager-approval', label: 'Manager Approval' },
  { key: 'wafer-preparation', label: 'Wafer Preparation' },
  { key: 'test-preparation', label: 'Test Preparation' },
  { key: 'test-execution', label: 'Test Execution' },
  { key: 'internal-review', label: 'Internal Review' },
  { key: 'customer-review', label: 'Customer Review' },
] as const

const currentStepByStage = {
  'Engineer Review': 1,
  'Manager Approval': 2,
  'Test Preparation': 3,
  'Test Execution': 5,
  'Internal Review': 6,
  'Customer Review': 7,
} as const

export function demoProjectCycleGroup(item: DemoWorkflowDto): DemoProjectCycleGroup {
  if (item.archiveCategory === 'Completed') return 'completed'
  if (item.stage === 'Engineer Review' || item.stage === 'Manager Approval') return 'request'
  return 'test'
}

export function isCustomerExpectedRisk(item: DemoWorkflowDto): boolean {
  if (item.archiveCategory === 'Completed') return false
  const days = item.health?.daysToCustomerExpected
  return typeof days === 'number' && days <= 7
}

function dateOrdinal(value: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return null
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) / 86_400_000
}

function shanghaiToday(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

function completedDateOrdinal(item: DemoWorkflowDto): number | null {
  const completedAt = item.projectTimeline?.find((step) => step.key === 'customer-review')?.date
    || item.evaluation?.runs.filter((run) => run.status === 'Completed').at(-1)?.date
    || item.artifacts?.at(-1)?.createdAt
  return completedAt ? dateOrdinal(completedAt) : null
}

export function isRecentCompletedProject(
  item: DemoWorkflowDto,
  today = shanghaiToday(),
): boolean {
  if (item.archiveCategory !== 'Completed') return false
  const completedDay = completedDateOrdinal(item)
  const todayDay = dateOrdinal(today)
  if (completedDay === null || todayDay === null) return false
  const age = todayDay - completedDay
  return age >= 0 && age <= 100
}

export function recentCompletedProjects(
  items: DemoWorkflowDto[],
  today = shanghaiToday(),
): DemoWorkflowDto[] {
  return items
    .filter((item) => isRecentCompletedProject(item, today))
    .sort((left, right) => (completedDateOrdinal(right) ?? 0) - (completedDateOrdinal(left) ?? 0))
}

export function preparationGateState(
  steps: DemoProjectTimelineStepDto[],
): DemoProjectTimelineState {
  if (steps.every((step) => step.state === 'Done')) return 'Done'
  if (steps.some((step) => step.state !== 'Waiting')) return 'Current'
  return 'Waiting'
}

function timelineState(item: DemoWorkflowDto, key: string, index: number): DemoProjectTimelineState {
  if (item.archiveCategory === 'Completed') return 'Done'
  if (item.stage === 'Test Preparation') {
    if (key === 'wafer-preparation') return item.evaluation?.waferPreparationStatus === 'Completed' ? 'Done' : 'Current'
    if (key === 'test-preparation') return item.evaluation?.testPreparationStatus === 'Completed' ? 'Done' : 'Current'
    return index < currentStepByStage['Test Preparation'] ? 'Done' : 'Waiting'
  }
  const current = item.stage ? currentStepByStage[item.stage] : 0
  if (index < current) return 'Done'
  if (index === current) return 'Current'
  return 'Waiting'
}

function withRequiredMilestones(
  timeline: DemoProjectTimelineStepDto[],
): DemoProjectTimelineStepDto[] {
  let normalized = timeline
  if (!normalized.some((step) => step.key === 'wafer-preparation')) {
    const testPreparationIndex = normalized.findIndex((step) => step.key === 'test-preparation')
    if (testPreparationIndex >= 0) {
      const testPreparation = normalized[testPreparationIndex]
      normalized = [
        ...normalized.slice(0, testPreparationIndex),
        {
          ...testPreparation,
          key: 'wafer-preparation',
          label: 'Wafer Preparation',
        },
        ...normalized.slice(testPreparationIndex),
      ]
    }
  }
  if (!normalized.some((step) => step.key === 'internal-review')) {
    const customerReviewIndex = normalized.findIndex((step) => step.key === 'customer-review')
    if (customerReviewIndex >= 0) {
      const customerReview = normalized[customerReviewIndex]
      normalized = [
        ...normalized.slice(0, customerReviewIndex),
        {
          key: 'internal-review',
          label: 'Internal Review',
          state: customerReview.state === 'Current' ? 'Done' : customerReview.state,
        },
        ...normalized.slice(customerReviewIndex),
      ]
    }
  }
  return normalized
}

export function buildDemoProjectTimeline(item: DemoWorkflowDto): DemoProjectTimelineStepDto[] {
  if (item.projectTimeline?.length) return withRequiredMilestones(item.projectTimeline)

  const approvalActors = [
    item.salesOwner,
    item.approvals.find((approval) => approval.label === 'FAE Review')?.actor || item.engineerOwner,
    item.approvals.find((approval) => approval.label === 'Boss Approval')?.actor || '',
    item.evaluation?.waferPreparationCompletedBy || item.engineerOwner,
    item.evaluation?.testPreparationCompletedBy || item.engineerOwner,
    item.evaluation?.owner || item.engineerOwner,
    item.evaluation?.owner || item.engineerOwner,
    '',
  ]
  const runDate = item.evaluation?.runs.find((run) => run.status === 'Completed')?.date
    || item.evaluation?.runs[0]?.date

  return timelineMilestones.map((milestone, index) => ({
    ...milestone,
    state: timelineState(item, milestone.key, index),
    actor: approvalActors[index],
    date: index === 3
      ? item.evaluation?.waferPreparationCompletedAt?.slice(0, 10)
      : index === 4
        ? item.evaluation?.testPreparationCompletedAt?.slice(0, 10)
        : index === 5 || index === 6
      ? runDate
      : index === 7
        ? item.customerExpectedDate
        : undefined,
  }))
}
