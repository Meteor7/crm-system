export type BoardField = 'stage' | 'probabilityLevel' | 'sales' | 'region' | 'market' | 'equipment' | 'customerName' | 'stageChangedAt' | 'stageAgeDays' | 'amountCny'
export type BoardOperator = 'in' | 'not_in' | 'contains' | 'before' | 'after' | 'between' | 'gt' | 'gte' | 'lt' | 'lte'
export type BoardColumn = Exclude<BoardField, 'stageAgeDays'> | 'title' | 'amount' | 'nextAction'
export type BoardGroup = 'region' | 'sales' | 'stage' | 'probabilityLevel' | 'equipment' | 'market'
export interface BoardCondition { field: BoardField; operator: BoardOperator; value: string | string[] | number }
export interface BoardScope { sales: string[]; regions: string[]; markets: string[]; equipment: string[] }
export interface BoardSort { field: Exclude<BoardColumn, 'amount'> | 'stageAgeDays'; direction: 'asc' | 'desc' }
export interface BoardDefinition { scope: BoardScope; match: 'all' | 'any'; conditions: BoardCondition[]; sort: BoardSort; groupBy: BoardGroup | null; columns: BoardColumn[] }
export type BoardQuery = Omit<BoardDefinition, 'columns'> & { page: number; pageSize: number }
export interface BoardOption { value: string; label: string }
export interface BoardFilters { sales: BoardOption[]; regions: BoardOption[]; markets: BoardOption[]; equipment: BoardOption[]; stages: BoardOption[]; probabilityLevels: BoardOption[]; regionReady: boolean }
export interface BoardRow {
  id: string; title: string; accountId: string; customerName: string
  region: string | null; salesId: string; salesName: string; stage: string
  stageChangedAt: string | null; stageAgeDays: number | null; stageUnchangedOver21Days: boolean
  probabilityLevel: string | null; equipment: string | null; market: string | null
  /** Not entered yet ('', or a stored 0.00: a known Opportunity amount is always above 0) at qualified_opportunity. */
  amount: string; currency: string; amountCny: string | null
  nextAction: { id: string; title: string; due: string | null } | null
}
export interface BoardTotals { count: number; knownAmountCny: string; missingAmountCount: number }
export interface BoardSummary extends BoardTotals {
  stageUnchangedOver21DaysCount: number; unknownStageAgeCount: number
  byProbability: Array<BoardTotals & { level: string }>
}
export interface BoardResult { items: BoardRow[]; asOf: string; summary: BoardSummary; groups: Array<BoardTotals & { key: string | null; label: string }> }
export interface SavedBoardQuery { id: string; name: string; definition: BoardDefinition; modified: string }
export interface SaveBoardQueryInput { name: string; definition: BoardDefinition }
