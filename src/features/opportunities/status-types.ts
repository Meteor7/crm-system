export interface OpportunityStatusFile {
  id: string
  fileName: string
  mimeType: string
  size: number
}

export interface OpportunityStatusRecord {
  id: string
  text: string
  files: OpportunityStatusFile[]
  updatedAt: string
  updatedBy: string
  modified: string
}

export interface SaveOpportunityStatusInput {
  text: string
  retainedFileIds: string[]
  recordId?: string
  expectedModified?: string
}
