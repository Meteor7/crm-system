import type { DemoHealthDto, DemoLifecycleStage, DemoRequestStatus, EvaluationStatus } from '@/types/crm'

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/
const DAY_MS = 86_400_000

function shanghaiDateKey(value: string) {
  if (DATE_ONLY.test(value)) return value
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return null
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const read = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value
  return `${read('year')}-${read('month')}-${read('day')}`
}

function dayNumber(value: string) {
  const key = shanghaiDateKey(value)
  if (!key || !DATE_ONLY.test(key)) return null
  const [year, month, day] = key.split('-').map(Number)
  const timestamp = Date.UTC(year, month - 1, day)
  return new Date(timestamp).toISOString().slice(0, 10) === key ? timestamp / DAY_MS : null
}

export function mapDemoLifecycleStage(
  requestStatus: DemoRequestStatus,
  evaluationStatus?: EvaluationStatus,
): DemoLifecycleStage | null {
  if (requestStatus === 'Draft' || requestStatus === 'Cancelled') return null
  if (requestStatus === 'Engineer Review' || requestStatus === 'Engineer Returned') return 'Engineer Review'
  if (requestStatus === 'Manager Approval' || requestStatus === 'Manager Rejected') return 'Manager Approval'
  if (!evaluationStatus) return requestStatus === 'Converted' ? 'Test Preparation' : null
  if (evaluationStatus === 'Accepted' || evaluationStatus === 'Rejected') return null
  if (['Requested', 'Scope Confirmed', 'Sample Received', 'Scheduled'].includes(evaluationStatus)) return 'Test Preparation'
  if (evaluationStatus === 'Testing') return 'Test Execution'
  if (evaluationStatus === 'Analysis' || evaluationStatus === 'Internal Review') return 'Internal Review'
  return evaluationStatus === 'Customer Review' ? 'Customer Review' : null
}

export function deriveDemoHealth(input: {
  lastProgressAt: string
  customerExpectedDate: string
  testRunDeadline: string
  today: string
}): DemoHealthDto {
  const today = dayNumber(input.today) ?? 0
  const lastProgress = dayNumber(input.lastProgressAt)
  const expected = dayNumber(input.customerExpectedDate)
  const deadline = dayNumber(input.testRunDeadline)
  const daysSinceProgress = lastProgress == null ? 0 : Math.max(0, today - lastProgress)
  const daysToCustomerExpected = expected == null ? null : expected - today

  if (daysToCustomerExpected != null && daysToCustomerExpected <= 7) {
    const reason = daysToCustomerExpected < 0
      ? `客户预期已逾期 ${Math.abs(daysToCustomerExpected)} 天`
      : daysToCustomerExpected === 0
        ? '客户预期为今天'
        : `距客户预期仅 ${daysToCustomerExpected} 天`
    return { level: 'critical', reason, daysSinceProgress, daysToCustomerExpected }
  }

  if (deadline != null && deadline < today) {
    return {
      level: 'critical',
      reason: `Test Run DDL 已逾期 ${today - deadline} 天`,
      daysSinceProgress,
      daysToCustomerExpected,
    }
  }

  if (daysSinceProgress >= 5) {
    return {
      level: 'stalled',
      reason: `已连续 ${daysSinceProgress} 天无有效进展`,
      daysSinceProgress,
      daysToCustomerExpected,
    }
  }

  return {
    level: 'healthy',
    reason: daysSinceProgress === 0
      ? '今天有进展'
      : daysSinceProgress <= 2
        ? `${daysSinceProgress} 天内有进展`
        : '正常推进',
    daysSinceProgress,
    daysToCustomerExpected,
  }
}
