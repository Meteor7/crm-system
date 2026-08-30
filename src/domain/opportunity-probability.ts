import { STRATEGY_OPPORTUNITY_STAGES, type StrategyOpportunityStage } from '@/types/workspaces'

export const OPPORTUNITY_STAGES = STRATEGY_OPPORTUNITY_STAGES

const STAGE_PROBABILITIES: Record<StrategyOpportunityStage, number> = {
  '需求发现': 15,
  'Wafer Demo确认': 55,
  '预算审批': 70,
  '设备规格确认': 75,
  '报价': 80,
  '采购流程': 90,
  Won: 100,
  Lost: 0,
}

export function getOpportunityStageBaseProbability(stage: StrategyOpportunityStage) {
  return STAGE_PROBABILITIES[stage]
}

export function calculateOpportunityProbability(stage: StrategyOpportunityStage, purchaseIntent: number) {
  const base = getOpportunityStageBaseProbability(stage)
  if (stage === 'Won') return 100
  if (stage === 'Lost') return 0
  const intent = Number(purchaseIntent) || 0
  return Math.max(0, Math.min(100, Math.round(base * 0.6 + intent * 0.4)))
}

export function opportunityProbabilityExplanation(stage: StrategyOpportunityStage, purchaseIntent: number) {
  return `阶段基础概率 ${getOpportunityStageBaseProbability(stage)}% × 60% + 购买意愿 ${Number(purchaseIntent) || 0} × 40%`
}
