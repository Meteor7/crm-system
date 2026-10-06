export type ScorecardKey = 'productScorecard' | 'dealScorecard'
export interface ScorecardLink { url: string; state: 'ready' | 'missing' | 'invalid' }
export interface OpportunityDocumentLinks {
  modified: string
  links: Record<ScorecardKey, ScorecardLink>
}
export type OpportunityDocumentKind = 'status' | 'demo' | 'rfq' | 'quotation' | 'visit'
export interface OpportunityDocumentItem {
  id: string; title: string; sourceId: string; at: string
  fileId?: string; recordId?: string; status?: string; version?: number
}
export interface OpportunityDocuments extends OpportunityDocumentLinks {
  opportunityId: string; title: string
  groups: { kind: OpportunityDocumentKind; items: OpportunityDocumentItem[] }[]
}
