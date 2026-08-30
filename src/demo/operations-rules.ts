import type { ProcedureRun, ServiceAppointment } from './operations-data'

function toMinutes(value: string) {
  const [hours, minutes] = value.split(':').map(Number)
  return hours * 60 + minutes
}

export function hasScheduleConflict(left: ServiceAppointment, right: ServiceAppointment) {
  if (left.id === right.id || left.day !== right.day || left.engineer !== right.engineer) return false
  return toMinutes(left.start) < toMinutes(right.end) && toMinutes(right.start) < toMinutes(left.end)
}

export function appointmentHasConflict(target: ServiceAppointment, rows: ServiceAppointment[]) {
  return rows.some((row) => hasScheduleConflict(target, row))
}

export function getProcedureBlockers(run: ProcedureRun) {
  return run.checklist
    .filter((item) => item.mandatory && item.status !== 'Passed')
    .map((item) => item.title)
}
