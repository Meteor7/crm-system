import { shanghaiDate } from './time'

export type ContractRiskBand = 'expired' | '30d' | '60d' | '90d' | 'normal'

export interface ContractRisk {
  days: number
  band: ContractRiskBand
  label: string
}

export function getContractRisk(endDate: string, today = shanghaiDate()): ContractRisk {
  const end = new Date(`${endDate}T00:00:00+08:00`).getTime()
  const start = new Date(`${today}T00:00:00+08:00`).getTime()
  const days = Math.ceil((end - start) / 86_400_000)
  const band: ContractRiskBand = days < 0 ? 'expired' : days <= 30 ? '30d' : days <= 60 ? '60d' : days <= 90 ? '90d' : 'normal'
  return { days, band, label: days < 0 ? '已到期' : days === 0 ? '今天到期' : band === 'normal' ? '正常' : `${days} 天内` }
}
